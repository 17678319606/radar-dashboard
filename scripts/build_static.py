#!/usr/bin/env python3
"""
把雷达日报 Dashboard 构建成纯静态站点，用于腾讯云 EdgeOne Pages 等静态托管。

原理：后端 app.py 的 API 全是「只读 JSON」，没有数据库。
所以构建时用 Flask 的 test_client 把每个 API 的响应预渲染成静态 .json 文件，
前端 index.html 注入 window.__STATIC_MODE__ = true 后，
把 /api/xxx 的请求改成读 api/xxx.json，页面表现与本地跑 Flask 完全一致。

差异：收藏功能（原来写 data/favorites.json）在静态模式下改存浏览器 localStorage。

用法:
    venv/bin/python scripts/build_static.py            # 输出到 dist/
    venv/bin/python scripts/build_static.py --out out  # 自定义输出目录
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app, REPORTS_DIR  # noqa: E402

RAW_DIR = REPORTS_DIR.parent / 'raw_signals'

# 前端 index.html 会请求的模块名（与 app.py 的 module_map 对应）
MODULE_NAMES = [
    'opportunities', 'money-cases', 'inspirations', 'growth',
    'tools', 'pitfalls', 'signals', 'mini-program', 'wisdom', 'indie-dev',
    'side-hustles',
]

INJECT_SNIPPET = (
    "<script>window.__STATIC_MODE__ = true;</script>\n"
    f"<script>window.__BUILD_TS__ = {int(__import__('time').time())};</script>\n"
    "<!-- 静态部署模式：API 读预渲染 JSON，收藏存 localStorage -->\n"
)


SITE_URL = 'https://radar-dashboard-7zsuaod4.edgeone.cool'


def _generate_seo_assets(out_dir: Path):
    """生成 robots.txt 与 sitemap.xml（含每日日报 URL），便于搜索引擎收录"""
    # robots.txt
    robots = BASE_DIR / 'robots.txt'
    if robots.exists():
        shutil.copy(robots, out_dir / 'robots.txt')
    else:
        (out_dir / 'robots.txt').write_text(
            f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding='utf-8')

    # sitemap.xml：首页 + 每一期日报（真实静态 HTML 页，可被搜索引擎收录）
    urls = [f"{SITE_URL}/"]
    for f in sorted(REPORTS_DIR.glob('*.json'), reverse=True):
        urls.append(f"{SITE_URL}/daily/{f.stem}.html")
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml.append(f"  <url><loc>{u}</loc></url>")
    xml.append('</urlset>')
    (out_dir / 'sitemap.xml').write_text('\n'.join(xml) + '\n', encoding='utf-8')
    print(f'   SEO: robots.txt + sitemap.xml（{len(urls)} 个 URL）')


def _generate_rss(out_dir: Path, site_url: str):
    """生成 RSS 2.0 feed（最近 20 期日报），便于订阅与搜索引擎收录"""
    items = []
    for f in sorted(REPORTS_DIR.glob('*.json'), reverse=True)[:20]:
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        date = data.get('date', f.stem)
        mods = (data.get('modules') or {})
        cnt = sum(len(v) for v in mods.values() if isinstance(v, list))
        try:
            pub = datetime.strptime(date, '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0800')
        except Exception:
            pub = ''
        desc = f'本期含 {cnt} 条精选信号（机会 / 副业 / 小程序 / 工具等）'
        items.append(
            '    <item>\n'
        f'      <title>进步分子雷达日报 {date}</title>\n'
        f'      <link>{site_url}/daily/{date}.html</link>\n'
        f'      <guid isPermaLink="true">{site_url}/daily/{date}.html</guid>\n'
            f'      <pubDate>{pub}</pubDate>\n'
            f'      <description>{desc}</description>\n'
            '    </item>'
        )
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        '  <title>进步分子雷达日报</title>',
        f'  <link>{site_url}/</link>',
        '  <description>每日自动采集 20+ 信息源，生成独立开发者 / 副业赚钱机会雷达。</description>',
        '  <language>zh-CN</language>',
        f'  <image><url>{site_url}/donate-qrcode.jpg</url><title>进步分子雷达日报</title><link>{site_url}</link></image>',
    ] + items + ['</channel></rss>']
    (out_dir / 'rss.xml').write_text('\n'.join(xml) + '\n', encoding='utf-8')
    print(f'   SEO: rss.xml（{len(items)} 期）')


# ───────────────────── 静态 HTML 预渲染（SEO 收录关键） ─────────────────────
MODULE_LABELS = {
    'opportunities': ('📌', '今日机会'),
    'moneyCases': ('💰', '今日赚钱案例'),
    'sideHustles': ('🚀', '副业赚钱项目'),
    'productInspirations': ('💡', '今日产品灵感'),
    'growthTips': ('📈', '今日增长技巧'),
    'tools': ('🔧', '今日工具'),
    'pitfalls': ('⚠️', '今日踩坑'),
    'dataSignals': ('📊', '今日数据信号'),
    'miniProgram': ('📱', '微信小程序机会'),
    'indieDev': ('🧑\u200d💻', '独立开发者新品'),
    'dailyWisdom': ('🧠', '今日心法'),
}


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _item_title(item):
    return (item.get('title') or item.get('product') or item.get('what')
            or item.get('idea') or item.get('suggestion') or item.get('strategy')
            or item.get('tool') or item.get('lesson') or item.get('observation')
            or item.get('name_cn') or item.get('title_cn') or '(未命名)')


def _item_url(item):
    return item.get('url') or item.get('sourceUrl') or item.get('source_url') or ''


def _item_desc(item):
    return (item.get('summary') or item.get('desc') or item.get('desc_cn')
            or item.get('content') or item.get('signal') or item.get('suggestion')
            or item.get('what') or item.get('idea') or '')


def _item_source(item):
    return item.get('source') or item.get('source_label') or ''


DAILY_HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>进步分子雷达日报 {date}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:title" content="进步分子雷达日报 {date}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site_url}/daily/{date}.html">
<meta property="og:image" content="{site_url}/og-cover.svg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site_url}/og-cover.svg">
<link rel="canonical" href="{site_url}/daily/{date}.html">
<script type="application/ld+json">{article_ld}</script>
<style>
:root{{--bg:#0b0d12;--surface:#13161e;--card:#1a1e2a;--border:#2a2f45;--text:#e6e8ee;--sub:#9aa3b2}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font:15px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;padding:0 16px}}
.wrap{{max-width:760px;margin:0 auto;padding:32px 0 64px}}
header a{{color:var(--sub);text-decoration:none;font-size:.85rem}}
h1{{font-size:1.6rem;margin:14px 0 4px}}
.date{{color:var(--sub);font-size:.9rem;margin-bottom:24px}}
.mod{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin:14px 0}}
.mod h2{{font-size:1.05rem;display:flex;align-items:center;gap:8px;margin-bottom:12px}}
.mod h2 .n{{margin-left:auto;background:var(--surface);color:var(--sub);font-size:.75rem;padding:2px 8px;border-radius:999px}}
.mod ul{{list-style:none}}
.mod li{{padding:10px 0;border-top:1px solid var(--border)}}
.mod li:first-child{{border-top:none}}
.mod .t{{display:block;font-weight:600;color:var(--text)}}
.mod .d{{display:block;color:var(--sub);font-size:.9rem;margin-top:4px}}
.mod .m{{display:flex;gap:12px;margin-top:6px;font-size:.8rem}}
.mod .src{{color:var(--sub)}}
.mod .lnk{{color:#6ea8fe;text-decoration:none}}
.empty{{color:var(--sub)}}
footer{{margin-top:40px;color:var(--sub);font-size:.8rem;text-align:center}}
</style>
</head>
<body>
<div class="wrap">
<header><a href="{site_url}/">← 返回 进步分子雷达日报 首页</a></header>
<h1>进步分子雷达日报</h1>
<div class="date">{date} · 每日 06:00 / 19:00（北京时间）自动更新</div>
{sections}
<footer>本站内容由 AI 辅助聚合公开信息源生成，仅供参考。© 进步分子雷达日报</footer>
</div>
</body>
</html>
"""

OG_COVER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#0b0d12"/>
<text x="80" y="300" fill="#e6e8ee" font-family="-apple-system,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif" font-size="76" font-weight="700">进步分子雷达日报</text>
<text x="80" y="380" fill="#9aa3b2" font-family="-apple-system,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif" font-size="34">每日自动采集 16+ 信息源 · 独立开发者 / 副业赚钱机会雷达</text>
<text x="80" y="560" fill="#6ea8fe" font-family="-apple-system,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif" font-size="28">每日 06:00 / 19:00 自动更新</text>
</svg>
"""


def _generate_og_cover(out_dir, site_url):
    """生成 OG 分享封面（SVG，零依赖），供 og:image / twitter:image 引用"""
    (out_dir / 'og-cover.svg').write_text(OG_COVER_SVG, encoding='utf-8')


def _generate_daily_html(out_dir, report_path, site_url):
    """把每期日报预渲染为真实静态 HTML 页，便于搜索引擎收录正文（SEO 关键）"""
    try:
        data = json.loads(report_path.read_text(encoding='utf-8'))
    except Exception:
        return
    date = data.get('date', report_path.stem)
    mods = data.get('modules') or {}
    wisdom = mods.get('dailyWisdom') or []
    if isinstance(wisdom, list) and wisdom:
        desc = str(_item_desc(wisdom[0]))[:120]
    else:
        desc = '每日自动采集 16+ 信息源，生成独立开发者 / 副业赚钱机会雷达。'
    desc = _esc(desc)
    sections = []
    for key, (emoji, label) in MODULE_LABELS.items():
        items = mods.get(key)
        if not isinstance(items, list) or not items:
            continue
        lis = []
        for it in items:
            if not isinstance(it, dict):
                continue
            t = _item_title(it)
            u = _item_url(it)
            d = _item_desc(it)
            s = _item_source(it)
            inner = f'<span class="t">{_esc(t)}</span>'
            if d:
                inner += f'<span class="d">{_esc(str(d)[:200])}</span>'
            meta = []
            if s:
                meta.append(f'<span class="src">{_esc(str(s))}</span>')
            if u:
                meta.append(f'<a class="lnk" href="{_esc(u)}" target="_blank" rel="noopener">↗ 来源</a>')
            if meta:
                inner += '<span class="m">' + ' · '.join(meta) + '</span>'
            lis.append(f'<li>{inner}</li>')
        if lis:
            sections.append(
                f'<section class="mod"><h2>{emoji} {_esc(label)}'
                f'<span class="n">{len(lis)}</span></h2><ul>{"".join(lis)}</ul></section>'
            )
    sections_html = '\n'.join(sections) if sections else '<p class="empty">本期暂无内容。</p>'
    article_ld = {
        '@context': 'https://schema.org', '@type': 'Article',
        'headline': f'进步分子雷达日报 {date}',
        'datePublished': f'{date}T00:00:00+08:00',
        'dateModified': f'{date}T00:00:00+08:00',
        'author': {'@type': 'Organization', 'name': '进步分子雷达日报'},
        'publisher': {'@type': 'Organization', 'name': '进步分子雷达日报'},
        'description': desc,
        'mainEntityOfPage': f'{site_url}/daily/{date}.html',
    }
    html = DAILY_HTML_TMPL.format(
        site_url=site_url, date=date, desc=desc,
        sections=sections_html, article_ld=json.dumps(article_ld, ensure_ascii=False),
    )
    daily_dir = out_dir / 'daily'
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / f'{date}.html').write_text(html, encoding='utf-8')


def collect_routes():
    """列出需要预渲染的 API 路由"""
    routes = [
        '/api/reports',
        '/api/raw-dates',
        '/api/sources',
        '/api/stats',
        '/api/trends',
        '/api/indie-dev',
        '/api/config',
    ]
    for f in sorted(REPORTS_DIR.glob('*.json')):
        routes.append(f'/api/reports/{f.stem}')
    for name in MODULE_NAMES:
        routes.append(f'/api/modules/{name}')
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.glob('*.json')):
            routes.append(f'/api/raw/{f.stem}')
    return routes


def build(out_dir: Path):
    # 增量构建：仅覆盖同名产物，不整体清空 dist/，
    # 避免本地重跑 update.sh 时触发批量删除安全拦截而中断
    out_dir.mkdir(parents=True, exist_ok=True)

    client = app.test_client()
    ok, failed = 0, []

    for route in collect_routes():
        resp = client.get(route)
        if resp.status_code != 200:
            failed.append((route, resp.status_code))
            continue
        # /api/reports -> dist/radar-api/reports.json
        # （目录名不用 api/，避免与静态托管平台的函数路由约定冲突）
        target = out_dir / (route.replace('/api/', 'radar-api/', 1) + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(resp.data.decode('utf-8'))
        target.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        ok += 1

    # 前端页面：注入静态模式开关
    html = (BASE_DIR / 'templates' / 'index.html').read_text(encoding='utf-8')
    if '</head>' in html:
        html = html.replace('</head>', INJECT_SNIPPET + '</head>', 1)
    else:
        html = INJECT_SNIPPET + html
    (out_dir / 'index.html').write_text(html, encoding='utf-8')

    # 静态资源（若有）
    static_src = BASE_DIR / 'static'
    if static_src.exists():
        shutil.copytree(static_src, out_dir / 'static', dirs_exist_ok=True)

    # 赞赏二维码等同域静态资源（避免依赖 raw.githubusercontent，国内常不可达且未打进 dist → 404）
    docs_dir = BASE_DIR / 'docs'
    for img in ('donate-qrcode.jpg', 'wechat-qrcode.png'):
        src = docs_dir / img
        if src.exists():
            shutil.copy(src, out_dir / img)

    # SEO：根目录静态文件（robots / sitemap / rss / public）
    _generate_seo_assets(out_dir)
    _generate_rss(out_dir, SITE_URL)
    # 预渲染每期日报为真实静态 HTML（SEO 收录关键）+ OG 分享封面
    _generate_og_cover(out_dir, SITE_URL)
    for f in sorted(REPORTS_DIR.glob('*.json'), reverse=True):
        _generate_daily_html(out_dir, f, SITE_URL)

    size = sum(f.stat().st_size for f in out_dir.rglob('*') if f.is_file())
    print(f'✅ 静态站点已生成: {out_dir}')
    print(f'   API 文件: {ok} 个    总大小: {size / 1024:.1f} KB')
    if failed:
        print(f'   ⚠️ 跳过 {len(failed)} 个路由: {failed}')
    print('   本地预览: python3 -m http.server 8000 --directory ' + str(out_dir))
    return ok, failed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='dist', help='输出目录，默认 dist')
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = BASE_DIR / out
    build(out)
