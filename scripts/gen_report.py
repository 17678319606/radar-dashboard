#!/usr/bin/env python3
"""
用 DeepSeek API 把当天采集到的原始信号自动生成「雷达日报」JSON。

原版 README 只给了两条路：手动复制给 ChatGPT，或者装 Hermes。
这个脚本填上中间那条：本地一条命令，用你自己的 DeepSeek Key 直接出日报。

用法:
    ./venv/bin/python scripts/gen_report.py                 # 生成今天的日报
    ./venv/bin/python scripts/gen_report.py --date 2026-08-06
    ./venv/bin/python scripts/gen_report.py --dry-run       # 只打印提示词，不调 API（不花钱）
    ./venv/bin/python scripts/gen_report.py --focus overseas  # 换方向

方向（--focus）:
    miniapp   默认。微信小程序机会最高优先级（适合国内独立开发/小程序创业）
    website   网站 / Web 应用方向
    overseas  出海产品方向

Key 读取顺序：环境变量 → 项目根 .env（gitignore，切勿提交）→ scripts/.env →
  ~/.hermes/.env → ~/.env → macOS 钥匙串（radar-dashboard / deepseek 服务名，加密存储）
生产部署走 GitHub Actions 加密 Secret（secrets.DEEPSEEK_API_KEY），密钥绝不进入前端或公开仓库。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = Path(os.environ.get('RADAR_DATA_DIR', BASE_DIR / 'data'))
RAW_DIR = DATA_DIR / 'raw_signals'
REPORTS_DIR = DATA_DIR / 'reports'
INDIE_DEV_FILE = DATA_DIR / 'indie_dev.json'

MAX_INDIE_DEV_ITEMS = 20       # 单期日报最多并入多少个独立开发者产品

API_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1').rstrip('/') + '/chat/completions'
MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash')

MAX_ITEMS_PER_SOURCE = 12      # 每个源最多喂多少条，控制 token 成本
MAX_TITLE_LEN = 120
MAX_DESC_LEN = 160

FOCUS_PROMPTS = {
    'miniapp': (
        "你的读者是**国内独立开发者**，主攻**微信小程序**和**轻量网站**创业项目，"
        "一个人或极小团队，追求「小而美、能快速上线、能收到钱」的项目。\n"
        "因此 `miniProgram`（微信小程序机会）是**最高优先级模块，必须给足 3-5 条**，"
        "每条都要把当天的信号**映射成一个国内微信小程序能落地的具体选题**，"
        "而不是复述原信号。海外信号也要做本地化映射（如「美国区某记账 App 上新」→「国内某人群的极简记账小程序」）。\n"
        "注意：`indieDev` 模块**不要你生成**——它由系统直接从 github.com/1c7/chinese-independent-developer"
        "（「中国独立开发者项目列表」）确定性并入，你只需在 `miniProgram` 里把其中特别契合小程序的选题做本地化映射即可。"
    ),
    'website': (
        "你的读者是**独立开发者**，主攻**网站 / Web 应用**（SaaS、工具站、内容站）。\n"
        "`opportunities`（今日机会）是最高优先级，每条都要落到「一个可以做成网站的具体选题」，"
        "`miniProgram` 模块可以少给或不给。"
    ),
    'overseas': (
        "你的读者是**出海独立开发者**，关注全球市场（海外 Web 应用 / SaaS / 工具）。\n"
        "`opportunities`（今日机会）是最高优先级，重点看 trustmrr / Product Hunt / GitHub / Reddit 等海外信号，"
        "关注可验证的收入模型（MRR）、定价策略和获客渠道，`miniProgram` 模块留空数组。"
    ),
}

JSON_SCHEMA_HINT = """严格输出如下结构的 JSON（不要 markdown 代码块，不要额外解释）：

{
  "date": "YYYY-MM-DD",
  "tags": ["#关键词1", "#关键词2"],
  "modules": {
    "opportunities":      [{"title":"", "why":"", "how":"", "keywords":["",""], "source":""}],
    "moneyCases":         [{"title":"", "what":"", "revenue":"", "how":"", "source":""}],
    "sideHustles":       [{"title":"", "why":"", "how":"", "revenue":"", "source":""}],  // 副业赚钱项目：来自 reddit-sidehustle 等通用副业信号，挑低门槛、普通人能上手、能变现的方向
    "productInspirations":[{"title":"", "idea":"", "source":""}],
    "growthTips":         [{"title":"", "tip":"", "source":""}],
    "tools":              [{"title":"", "what":"", "url":"", "source":""}],
    "pitfalls":           [{"title":"", "pitfall":"", "lesson":"", "source":""}],
    "dataSignals":        [{"title":"", "signal":"", "source":""}],
    "miniProgram":        [{"title":"", "insight":"", "suggestion":"", "keywords":["",""],
                            "userNeed":"", "painPoint":"", "howToBuild":"", "relatedSignal":"", "source":""}],
    "indieDev":           [],  // 此模块由系统自动并入 1c7 中国独立开发者列表，你无需填写
    "dailyWisdom":        {"method":"", "why":""}
  }
}

要求：
- 每个数组模块 1-5 条，宁缺毋滥，只挑当天最有价值的；实在没有就给空数组 []
- 所有内容用中文；英文标题请翻译，专有名词可保留原文
- `source` 填信号来源平台（如 github / appstore-us / v2ex / sspai / reddit-sidehustle）
- `sideHustles`（副业赚钱项目）：低门槛、普通人能上手、能变现的副业方向，可从 reddit-sidehustle 等副业信号里提炼；与 `moneyCases` 不同，它更偏「个人可做的副业」而非「已验证的赚钱案例」
- 不要编造信号里没有的数据（收入、用户数等），没有就不写
- `dailyWisdom.method` 是一条今天就能执行的具体做法，不要鸡汤
"""


def _read_keychain(service, account):
    """macOS Keychain 回退读取（密钥以加密形式存储在登录钥匙串，磁盘非明文）。

    返回密钥字符串或 None。仅在 macOS 且未设置环境变量时调用，CI（Linux）不受影响。
    """
    if sys.platform != 'darwin':
        return None
    try:
        out = subprocess.run(
            ['security', 'find-generic-password', '-s', service, '-a', account, '-w'],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _load_dotenv():
    for env_file in [BASE_DIR / '.env', SCRIPT_DIR / '.env',
                     Path.home() / '.hermes' / '.env', Path.home() / '.env']:
        try:
            if not env_file.exists():
                continue
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and not os.environ.get(k):
                    os.environ[k] = v
        except Exception:
            continue
    # 本地 Mac：若环境变量与 .env 都缺失，尝试从钥匙串读取（加密存储，避免磁盘明文）
    if not os.environ.get('DEEPSEEK_API_KEY'):
        kc = (_read_keychain('radar-dashboard', 'DEEPSEEK_API_KEY')
              or _read_keychain('deepseek', 'DEEPSEEK_API_KEY'))
        if kc:
            os.environ['DEEPSEEK_API_KEY'] = kc


def _clip(s, n):
    s = (s or '').replace('\n', ' ').strip()
    return s[:n]


def build_signal_text(raw):
    """把原始信号压成给模型看的紧凑文本"""
    lines = []
    for source, items in (raw.get('sources') or {}).items():
        if not items:
            continue
        lines.append(f'\n### 来源: {source}（{len(items)} 条）')
        for it in items[:MAX_ITEMS_PER_SOURCE]:
            title = it.get('title_cn') or it.get('name_cn') or it.get('title') or it.get('name') or ''
            desc = it.get('desc_cn') or it.get('desc') or it.get('summary') or it.get('description') or ''
            url = it.get('url', '')
            extra = []
            if it.get('stars'):
                extra.append(f"⭐{it['stars']}")
            if it.get('mrr'):
                extra.append(f"MRR {it['mrr']}")
            if it.get('votes'):
                extra.append(f"👍{it['votes']}")
            tail = ' '.join(extra)
            line = f'- {_clip(title, MAX_TITLE_LEN)}'
            if desc:
                line += f' | {_clip(desc, MAX_DESC_LEN)}'
            if tail:
                line += f' | {tail}'
            if url:
                line += f' | {url}'
            lines.append(line)
    return '\n'.join(lines)


def load_indie_dev():
    """读取 1c7「中国独立开发者项目列表」采集结果，扁平化成日报条目。

    返回 (items, meta)。meta 里带批次日期 / 本批新增数 / 来源，用于前端如实标注，
    避免把「1c7 最近一批」误写成「今天新增」。
    """
    try:
        data = json.loads(INDIE_DEV_FILE.read_text(encoding='utf-8'))
    except Exception:
        return [], {}

    batch_date = data.get('date') or ''
    items = []
    for dev in (data.get('items') or []):
        dev_date = dev.get('date') or batch_date
        fallback_url = dev.get('homepage') or dev.get('github') or ''
        for p in (dev.get('products') or []):
            name = (p.get('name') or '').strip()
            if not name:
                continue
            items.append({
                'developer': (dev.get('developer') or '').strip(),
                'city': (dev.get('city') or '').strip(),
                'product': name,
                'desc': _clip(p.get('desc'), 220),
                'url': (p.get('url') or '').strip() or fallback_url,
                'status': (p.get('status') or '').strip(),
                'batchDate': dev_date,
                'source': 'indie-dev',
            })

    meta = {
        'batchDate': batch_date,
        'newCount': data.get('newCount', 0),
        'totalProducts': data.get('totalProducts', len(items)),
        'source': data.get('source') or 'github.com/1c7/chinese-independent-developer',
    }
    return items[:MAX_INDIE_DEV_ITEMS], meta


def merge_indie_dev(report, date_str):
    """把 1c7 独立开发者内容确定性地并入日报的 indieDev 模块。

    此模块为 1c7 权威来源，模型不再生成（避免编造）。直接以 1c7 数据为准，
    保证每期日报的「独立开发者新品」均为真实存在的项目。
    """
    items, meta = load_indie_dev()
    if not items:
        meta['isToday'] = bool(meta.get('batchDate') == date_str)
        meta['mergedCount'] = 0
        meta['enrichedFields'] = 0
        report['indieDevMeta'] = meta
        report.setdefault('modules', {})['indieDev'] = []
        return 0, meta

    mods = report.setdefault('modules', {})
    # 不以模型产出为底（模型可能编造），直接以 1c7 数据为准
    existing = [it for it in items if isinstance(it, dict)]
    mods['indieDev'] = existing
    meta['isToday'] = bool(meta.get('batchDate') == date_str)
    meta['mergedCount'] = len(existing)
    meta['enrichedFields'] = 0
    report['indieDevMeta'] = meta
    return len(existing), meta


def build_fallback_report(raw, date_str, focus):
    """DeepSeek 不可用时的兜底：直接用原始信号拼出结构化日报，保证站点每日有新鲜内容。

    不做 LLM 润色，质量低于正常日报，但能避免「时间线停更 / 站点空白」。
    """
    sources = (raw.get('sources') or {})

    def _top(keys, n):
        out = []
        for k in keys:
            for it in (sources.get(k) or [])[:n]:
                out.append(it)
        return out[:n]

    def _norm(it):
        title = it.get('title_cn') or it.get('name_cn') or it.get('title') or it.get('name') or '(无标题)'
        desc = it.get('desc_cn') or it.get('desc') or it.get('summary') or it.get('description') or ''
        return title, _clip(desc, 200), it.get('url', ''), it.get('source', '')

    mods = {}
    opp = []
    for it in _top(['github', 'github-js', 'github-zh', 'hackernews', 'lobsters'], 6):
        t, d, u, s = _norm(it)
        opp.append({'title': t, 'why': d, 'how': '', 'keywords': [], 'source': s})
    mods['opportunities'] = opp

    mc = []
    for it in _top(['trustmrr'], 4):
        t, d, u, s = _norm(it)
        mc.append({'title': t, 'what': d, 'revenue': it.get('mrr') or '', 'how': '', 'source': s})
    mods['moneyCases'] = mc

    sh = []
    for it in _top(['reddit-sidehustle'], 5):
        t, d, u, s = _norm(it)
        sh.append({'title': t, 'why': d, 'how': '', 'revenue': '', 'source': s})
    mods['sideHustles'] = sh

    pi = []
    for it in _top(['appstore-cn', 'appstore-us', 'v2ex', 'producthunt'], 5):
        t, d, u, s = _norm(it)
        pi.append({'title': t, 'idea': d, 'source': s})
    mods['productInspirations'] = pi

    gt = []
    for it in _top(['36kr', 'sspai', 'oschina', 'ruanyifeng', 'jike-ai-explore', 'jike-engineer'], 5):
        t, d, u, s = _norm(it)
        gt.append({'title': t, 'tip': d, 'source': s})
    mods['growthTips'] = gt

    tl = []
    for it in _top(['appstore-cn', 'appstore-us'], 4):
        t, d, u, s = _norm(it)
        tl.append({'title': t, 'what': d, 'url': u, 'source': s})
    mods['tools'] = tl

    mods['pitfalls'] = []
    ds = []
    for it in _top(['hackernews', 'lobsters'], 4):
        t, d, u, s = _norm(it)
        ds.append({'title': t, 'signal': d, 'source': s})
    mods['dataSignals'] = ds

    mp = []
    for it in _top(['appstore-cn', 'v2ex'], 4):
        t, d, u, s = _norm(it)
        mp.append({'title': t, 'insight': d, 'suggestion': '', 'keywords': [], 'userNeed': '',
                   'painPoint': '', 'howToBuild': '', 'relatedSignal': '', 'source': s})
    mods['miniProgram'] = mp

    mods['dailyWisdom'] = {
        'method': '今天挑上面一个方向，花 30 分钟写一页纸方案（用户 / 痛点 / 怎么赚钱），不写代码也行。',
        'why': '行动胜过空想，先验证想法是否成立。',
    }

    return {
        'date': date_str,
        'tags': ['#每日信号', '#' + date_str],
        'modules': mods,
        'sources': {k: len(v) for k, v in sources.items()},
        'fallback': True,
    }


def build_prompt(raw, date_str, focus):
    return (
        f"以下是 {date_str} 从约 20 个国内外信息源采集到的原始信号。\n"
        f"{FOCUS_PROMPTS[focus]}\n\n"
        f"请从这些信号里**精选**最有价值的内容，整理成一份「独立开发者雷达日报」。\n\n"
        f"{JSON_SCHEMA_HINT}\n"
        f"===== 原始信号开始 =====\n{build_signal_text(raw)}\n===== 原始信号结束 ====="
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=date.today().isoformat())
    ap.add_argument('--focus', default='miniapp', choices=list(FOCUS_PROMPTS))
    ap.add_argument('--dry-run', action='store_true', help='只打印提示词，不调用 API')
    ap.add_argument('--force', action='store_true', help='覆盖已存在的日报')
    args = ap.parse_args()

    _load_dotenv()

    raw_path = RAW_DIR / f'{args.date}.json'
    if not raw_path.exists():
        avail = sorted(p.stem for p in RAW_DIR.glob('*.json')) if RAW_DIR.exists() else []
        print(f'❌ 没有 {args.date} 的原始信号：{raw_path}')
        print(f'   先跑一次采集：./venv/bin/python scripts/daily_signals.py')
        if avail:
            print(f'   已有日期：{", ".join(avail)}')
        sys.exit(1)

    out_path = REPORTS_DIR / f'{args.date}.json'
    if out_path.exists() and not args.force:
        print(f'⚠️  {out_path} 已存在，加 --force 覆盖')
        sys.exit(1)

    raw = json.loads(raw_path.read_text())
    prompt = build_prompt(raw, args.date, args.focus)
    n_signals = sum(len(v) for v in (raw.get('sources') or {}).values())
    print(f'📅 日期 {args.date} | 方向 {args.focus} | 信号 {n_signals} 条 | 提示词 {len(prompt)} 字符'
          f'（约 {len(prompt)//2} tokens，成本 ≈ ¥{len(prompt)/2/1_000_000*2:.3f}）')

    if args.dry_run:
        print('\n--- 提示词预览（前 1200 字）---')
        print(prompt[:1200])
        print('\n...（--dry-run，未调用 API）')
        return

    report = None
    usage = {}
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not key:
        print('⚠️ 未配置 DEEPSEEK_API_KEY，使用「信号直出」兜底日报（无 LLM 润色，保证每日有内容）')
    else:
        print('🤖 调用 DeepSeek 生成日报中（约 30-90 秒，失败自动兜底）...')
        for attempt in range(2):
            try:
                resp = requests.post(
                    API_URL,
                    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                    json={
                        'model': MODEL,
                        'messages': [
                            {'role': 'system', 'content': '你是资深独立开发者的信号分析师，擅长从海量信息里筛出能落地赚钱的产品机会。只输出 JSON。'},
                            {'role': 'user', 'content': prompt},
                        ],
                        'response_format': {'type': 'json_object'},
                        'temperature': 0.7,
                    },
                    timeout=300,
                )
                if resp.status_code != 200:
                    print(f'⚠️ API HTTP {resp.status_code}（第 {attempt+1} 次）：{resp.text[:200]}')
                    if attempt == 0:
                        time.sleep(5); continue
                    break
                body = resp.json()
                content = body['choices'][0]['message']['content']
                try:
                    report = json.loads(content)
                except json.JSONDecodeError:
                    bad = REPORTS_DIR / f'{args.date}.raw.txt'
                    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                    bad.write_text(content)
                    print(f'⚠️ 模型返回非合法 JSON（第 {attempt+1} 次），原文存 {bad}')
                    if attempt == 0:
                        time.sleep(3); continue
                    break
                usage = body.get('usage', {})
                break
            except Exception as e:
                print(f'⚠️ API 异常 {e}（第 {attempt+1} 次）')
                if attempt == 0:
                    time.sleep(5); continue
                break
        if report is None:
            print('⚠️ DeepSeek 不可用，回退到「信号直出」兜底日报')

    if report is None:
        report = build_fallback_report(raw, args.date, args.focus)

    report['date'] = args.date
    report.setdefault('sources', {k: len(v) for k, v in (raw.get('sources') or {}).items()})

    # 兜底并入 1c7 独立开发者内容（模型漏填也不会丢）
    idd_added, idd_meta = merge_indie_dev(report, args.date)
    if idd_meta:
        print(f'   indieDev: 1c7 批次 {idd_meta.get("batchDate") or "—"}'
              f'（本批新增 {idd_meta.get("newCount", 0)}）→ 并入 {idd_added} 条')

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    mods = report.get('modules', {}) or {}
    print(f'✅ 日报已生成: {out_path}')
    for k, v in mods.items():
        cnt = len(v) if isinstance(v, list) else (1 if v else 0)
        if cnt:
            print(f'   {k:22} {cnt} 条')
    if usage:
        cost = usage.get('prompt_tokens', 0) / 1e6 * 2 + usage.get('completion_tokens', 0) / 1e6 * 8
        print(f'   tokens: {usage.get("total_tokens")} | 本次成本 ≈ ¥{cost:.3f}')
    print('\n   下一步：./venv/bin/python scripts/build_static.py  然后重新部署 dist/')


if __name__ == '__main__':
    main()
