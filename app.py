#!/usr/bin/env python3
"""Radar Dashboard — 独立开发者雷达日报 可视化面板"""

import json
import os
import time
import hashlib
from pathlib import Path
from datetime import datetime, date
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__, static_folder='static', template_folder='templates')

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = Path(os.environ.get('REPORTS_DIR', BASE_DIR / 'data' / 'reports'))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── API ────────────────────────────────────────────────────────────────────

@app.route('/api/reports')
def list_reports():
    """返回所有日报的摘要列表（按日期降序）"""
    try:
        files = sorted(REPORTS_DIR.glob('*.json'), reverse=True)
    except FileNotFoundError:
        return jsonify([])

    reports = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            modules = data.get('modules', {}) or {}
            summary = {
                'date': data.get('date', f.stem),
                'moduleCount': sum(1 for m in modules.values() if m and (
                    (isinstance(m, list) and len(m) > 0) or
                    (isinstance(m, dict) and m.get('method'))
                )),
                'modules': {},
                'sources': data.get('sources', {}),
            }
            if modules.get('opportunities'):
                summary['modules']['opportunities'] = [
                    {'title': o.get('title', '')[:60]} for o in modules['opportunities'][:2]
                ]
            if modules.get('moneyCases'):
                summary['modules']['moneyCases'] = [
                    {'title': m.get('title', m.get('what', ''))[:60]} for m in modules['moneyCases'][:1]
                ]
            if modules.get('dailyWisdom') and modules['dailyWisdom'].get('method'):
                summary['modules']['dailyWisdom'] = modules['dailyWisdom']['method'][:80]
            reports.append(summary)
        except (json.JSONDecodeError, KeyError):
            continue
    return jsonify(reports)


@app.route('/api/reports/<date_str>')
def get_report(date_str):
    """返回指定日期的完整日报"""
    for f in REPORTS_DIR.glob(f'{date_str}*.json'):
        try:
            data = json.loads(f.read_text())
            return jsonify(data)
        except json.JSONDecodeError:
            return jsonify({'error': 'corrupted file'}), 500
    return jsonify({'error': 'not found'}), 404


@app.route('/api/modules/<module_name>')
def get_module(module_name):
    """跨日期聚合指定模块的全部内容"""
    module_map = {
        'opportunities': 'opportunities',
        'money-cases': 'moneyCases',
        'inspirations': 'productInspirations',
        'growth': 'growthTips',
        'tools': 'tools',
        'pitfalls': 'pitfalls',
        'signals': 'dataSignals',
        'mini-program': 'miniProgram',
        'wisdom': 'dailyWisdom',
        'indie-dev': 'indieDev',
    }
    key = module_map.get(module_name)
    if not key:
        return jsonify({'error': 'unknown module'}), 404

    results = []
    try:
        files = sorted(REPORTS_DIR.glob('*.json'), reverse=True)
    except FileNotFoundError:
        return jsonify([])

    for f in files:
        try:
            data = json.loads(f.read_text())
            modules = data.get('modules', {}) or {}
            items = modules.get(key, [])
            if items:
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    if isinstance(item, dict) and item:
                        results.append({
                            'date': data.get('date', f.stem),
                            **item
                        })
        except (json.JSONDecodeError, KeyError):
            continue
    return jsonify(results)


@app.route('/api/indie-dev')
def get_indie_dev():
    """返回独立开发者每日新增（github.com/1c7/chinese-independent-developer）"""
    path = REPORTS_DIR.parent / 'indie_dev.json'
    if not path.exists():
        return jsonify({'date': '', 'newCount': 0, 'items': [],
                        'note': '尚未采集，先跑一次 daily_signals.py'}), 200
    try:
        return jsonify(json.loads(path.read_text(encoding='utf-8')))
    except Exception:
        return jsonify({'error': 'corrupted'}), 500


@app.route('/api/raw-dates')
def list_raw_dates():
    """返回所有原始信号文件的日期（降序）"""
    raw_dir = REPORTS_DIR.parent / 'raw_signals'
    if not raw_dir.exists():
        return jsonify([])
    dates = sorted([f.stem for f in raw_dir.glob('*.json')], reverse=True)
    return jsonify(dates)


# 信息源元信息（用于管理页展示）
SOURCE_META = [
    {"key": "trustmrr", "name": "trustmrr", "emoji": "🟢", "category": "海外", "type": "API", "desc": "已验证收入的创业公司数据（MRR/增长/技术栈）"},
    {"key": "indiehackers", "name": "IndieHackers", "emoji": "🔵", "category": "海外", "type": "API", "desc": "独立开发者故事与案例研究"},
    {"key": "reddit", "name": "Reddit", "emoji": "🟠", "category": "海外", "type": "API", "desc": "新产品讨论（r/SideProject 等）— 需 OAuth 解锁"},
    {"key": "producthunt", "name": "Product Hunt", "emoji": "🟣", "category": "海外", "type": "API", "desc": "每日新品列表（GraphQL API）"},
    {"key": "github", "name": "GitHub 总榜", "emoji": "🐙", "category": "海外", "type": "Scrape", "desc": "GitHub Trending 每日热榜仓库"},
    {"key": "github-js", "name": "GitHub JS榜", "emoji": "🐙", "category": "海外", "type": "Scrape", "desc": "JavaScript/TypeScript 热榜（小程序技术栈参考）"},
    {"key": "github-zh", "name": "GitHub 中文榜", "emoji": "🐙", "category": "海外", "type": "Scrape", "desc": "中文社区热门仓库（spoken_language_code=zh）"},
    {"key": "v2ex", "name": "V2EX", "emoji": "🟤", "category": "国内", "type": "API", "desc": "技术/创业社区（分享创造/分享发现/程序员节点）"},
    {"key": "kr36", "name": "36氪", "emoji": "🔴", "category": "国内", "type": "RSS", "desc": "创投、融资、科技公司动态"},
    {"key": "sspai", "name": "少数派", "emoji": "🟡", "category": "国内", "type": "RSS", "desc": "效率工具、数字生活、App 推荐"},
    {"key": "oschina", "name": "开源中国", "emoji": "🟠", "category": "国内", "type": "RSS", "desc": "开源项目发布、技术新闻"},
    {"key": "jike-ai-explore", "name": "即刻·AI探索站", "emoji": "⚡", "category": "国内", "type": "RSS", "desc": "AI 应用/产品一手讨论（RSSHub）"},
    {"key": "jike-ai-discuss", "name": "即刻·AI讨论组", "emoji": "⚡", "category": "国内", "type": "RSS", "desc": "AI 技术/内容讨论（RSSHub）"},
    {"key": "jike-engineer", "name": "即刻·工程师", "emoji": "⚡", "category": "国内", "type": "RSS", "desc": "工程师日常圈子（RSSHub）"},
    {"key": "appstore-cn", "name": "App Store 中国", "emoji": "📱", "category": "国内", "type": "RSS", "desc": "中国区新上架应用（官方 RSS，看国内新产品方向，自动译中文）"},
    {"key": "appstore-tw", "name": "App Store 台湾", "emoji": "📱", "category": "国内", "type": "RSS", "desc": "台湾区新上架应用（自动译中文）"},
    {"key": "appstore-us", "name": "App Store 美国", "emoji": "📱", "category": "海外", "type": "RSS", "desc": "美国区新上架应用（全球创新前沿，自动译中文）"},
    {"key": "appstore-jp", "name": "App Store 日本", "emoji": "📱", "category": "海外", "type": "RSS", "desc": "日本区新上架应用（亚洲成熟市场，自动译中文）"},
    {"key": "appstore-kr", "name": "App Store 韩国", "emoji": "📱", "category": "海外", "type": "RSS", "desc": "韩国区新上架应用（美妆/社交/游戏创新，自动译中文）"},
]

# 各源采集脚本内对应的 last_seen 状态 key
SOURCE_STATE_KEYS = {m["key"]: m["key"] for m in SOURCE_META}


@app.route('/api/sources')
def get_sources_status():
    """信息源管理：返回所有源的接入状态、可用性、最近采集情况"""
    # 读状态文件
    state = {}
    state_file = REPORTS_DIR.parent / 'daily_signals_state.json'
    try:
        state = json.loads(state_file.read_text())
    except Exception:
        pass
    src_state = state.get('sources', {})

    # 读最近一次 raw_signals 统计
    raw_dir = REPORTS_DIR.parent / 'raw_signals'
    latest_raw = {}
    if raw_dir.exists():
        dates = sorted([f.stem for f in raw_dir.glob('*.json')], reverse=True)
        if dates:
            try:
                latest_raw = json.loads((raw_dir / f'{dates[0]}.json').read_text())
            except Exception:
                pass

    now_ts = int(time.time())
    result = []
    for meta in SOURCE_META:
        key = meta['key']
        s = src_state.get(key, {})
        last_seen = s.get('last_seen_ts')
        seen_count = len(s.get('seen_ids', []))

        # 今日/最近条目数
        today_count = len(latest_raw.get('sources', {}).get(key, []))

        # 状态判定
        if key == 'reddit':
            # Reddit 需要 OAuth 才能稳定工作
            import os
            if not os.environ.get('REDDIT_CLIENT_ID'):
                status = 'config_required'
                status_text = '需配置 OAuth'
                note = 'IP 被封，注册 Reddit App 后配置 REDDIT_CLIENT_ID 解锁'
            elif last_seen and (now_ts - last_seen) < 3 * 86400:
                status = 'ok'
                status_text = '正常'
                note = ''
            else:
                status = 'error'
                status_text = '异常'
                note = '最近采集失败'
        elif last_seen:
            hours_ago = (now_ts - last_seen) / 3600
            if hours_ago < 72:
                status = 'ok'
                status_text = '正常'
                note = f'{hours_ago:.0f} 小时前采集'
            else:
                status = 'stale'
                status_text = '久未采集'
                note = f'{hours_ago/24:.0f} 天前最后采集'
        else:
            status = 'no_data'
            status_text = '未采集'
            note = '尚未运行或新接入'

        result.append({
            **meta,
            'status': status,
            'status_text': status_text,
            'last_seen': last_seen,
            'last_seen_text': time.strftime('%m-%d %H:%M', time.localtime(last_seen)) if last_seen else '—',
            'seen_count': seen_count,
            'today_count': today_count,
            'note': note,
        })

    # 汇总
    summary = {
        'total': len(result),
        'ok': sum(1 for r in result if r['status'] == 'ok'),
        'warn': sum(1 for r in result if r['status'] in ('config_required', 'error', 'stale', 'no_data')),
        'last_run': state.get('last_run', ''),
        'latest_raw_date': list(latest_raw.keys())[0] if latest_raw else '',
    }
    return jsonify({'summary': summary, 'sources': result})


@app.route('/api/raw/<date_str>')
def get_raw_signals(date_str):
    """返回指定日期的原始信号（按平台分组，含 url）"""
    raw_dir = REPORTS_DIR.parent / 'raw_signals'
    path = raw_dir / f'{date_str}.json'
    if not path.exists():
        return jsonify({'error': 'not found'}), 404
    try:
        return jsonify(json.loads(path.read_text()))
    except json.JSONDecodeError:
        return jsonify({'error': 'corrupted file'}), 500


@app.route('/api/stats')
def get_stats():
    """聚合统计"""
    total_reports = 0
    module_counts = {}
    source_totals = {}
    monthly = {}

    try:
        files = sorted(REPORTS_DIR.glob('*.json'))
    except FileNotFoundError:
        return jsonify({'totalReports': 0, 'modules': {}, 'sources': {}, 'monthly': {}})

    for f in files:
        try:
            data = json.loads(f.read_text())
            total_reports += 1
            modules = data.get('modules', {}) or {}
            for mod_name, mod_data in modules.items():
                if mod_data and (
                    (isinstance(mod_data, list) and len(mod_data) > 0) or
                    (isinstance(mod_data, dict) and mod_data.get('method'))
                ):
                    module_counts[mod_name] = module_counts.get(mod_name, 0) + 1

            sources = data.get('sources', {}) or {}
            for k, v in sources.items():
                source_totals[k] = source_totals.get(k, 0) + (v if isinstance(v, (int, float)) else 0)

            dt = data.get('date', '')
            if dt:
                month = dt[:7]
                monthly[month] = monthly.get(month, 0) + 1
        except:
            continue

    return jsonify({
        'totalReports': total_reports,
        'modules': module_counts,
        'sources': source_totals,
        'monthly': dict(sorted(monthly.items())),
    })


@app.route('/api/trends')
def get_trends():
    key_freq = {}
    try:
        files = sorted(REPORTS_DIR.glob('*.json'), reverse=True)
    except FileNotFoundError:
        return jsonify([])

    for f in files:
        try:
            data = json.loads(f.read_text())
            for tag in (data.get('tags', []) or []):
                tag = tag.lstrip('#')
                if tag not in key_freq:
                    key_freq[tag] = []
                key_freq[tag].append(data.get('date', f.stem))
        except:
            continue
    sorted_tags = sorted(key_freq.items(), key=lambda x: -len(x[1]))
    return jsonify([
        {'tag': tag, 'count': len(dates), 'dates': dates}
        for tag, dates in sorted_tags[:30]
    ])


@app.route('/api/config')
def get_site_config():
    """站点配置：备案、广告、赞赏等（可远程热更新，无需重新部署前端）"""
    path = REPORTS_DIR.parent / 'config' / 'site.json'
    default = {
        'site': {'name': '独立开发者雷达日报', 'description': '', 'keywords': '', 'author': ''},
        'compliance': {'icp': '', 'icpUrl': '', 'police': '', 'policeUrl': ''},
        'ads': {'enabled': False, 'slots': []},
        'donation': {'enabled': False, 'title': '', 'desc': '', 'qrUrl': '', 'buttonText': ''},
        'update': {'autoUpdateNote': ''},
    }
    if not path.exists():
        return jsonify(default)
    try:
        return jsonify(json.loads(path.read_text(encoding='utf-8')))
    except Exception:
        return jsonify(default)


# ─── Frontend ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


# ═══ 收藏功能 ══════════════════════════════════════════════════════════════
FAVORITES_FILE = REPORTS_DIR.parent / 'favorites.json'


def _load_favorites():
    if not FAVORITES_FILE.exists():
        return []
    try:
        data = json.loads(FAVORITES_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_favorites(items):
    FAVORITES_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def _fav_id(payload):
    """生成收藏唯一 id：type + url/title 的 hash"""
    key = f"{payload.get('type', '')}|{payload.get('url', '')}|{payload.get('title', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


@app.route('/api/favorites', methods=['GET'])
def list_favorites():
    """获取所有收藏（倒序）"""
    favs = _load_favorites()
    favs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify(favs)


@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """添加收藏。body: {type, title, url, source, date, desc, raw, ...}"""
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400

    fav_id = payload.get('id') or _fav_id(payload)
    favs = _load_favorites()

    # 去重：同 id 不重复添加
    if any(f.get('id') == fav_id for f in favs):
        return jsonify({'ok': True, 'id': fav_id, 'duplicate': True})

    item = {
        'id': fav_id,
        'type': payload.get('type', 'signal'),        # signal / report_item / miniapp
        'title': title,
        'title_cn': payload.get('title_cn', ''),
        'name_cn': payload.get('name_cn', ''),
        'desc_cn': payload.get('desc_cn', ''),
        'url': payload.get('url', ''),
        'source': payload.get('source', ''),          # 平台 key（如 github-zh / appstore-cn）
        'source_label': payload.get('source_label', ''),
        'date': payload.get('date', ''),
        'module': payload.get('module', ''),          # 日报模块 key（如 opportunities）
        'desc': payload.get('desc', ''),
        'raw': payload.get('raw', {}),                # 完整原始数据，收藏后可原样还原
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    favs.append(item)
    _save_favorites(favs)
    return jsonify({'ok': True, 'id': fav_id})


@app.route('/api/favorites/<fav_id>', methods=['DELETE'])
def delete_favorite(fav_id):
    """删除收藏"""
    favs = _load_favorites()
    new_favs = [f for f in favs if f.get('id') != fav_id]
    if len(new_favs) == len(favs):
        return jsonify({'error': 'not found'}), 404
    _save_favorites(new_favs)
    return jsonify({'ok': True})


@app.route('/api/favorites/check/<fav_id>', methods=['GET'])
def check_favorite(fav_id):
    """检查是否已收藏"""
    favs = _load_favorites()
    return jsonify({'exists': any(f.get('id') == fav_id for f in favs)})


if __name__ == '__main__':
    import sys
    reports = len(list(REPORTS_DIR.glob('*.json')))
    print(f"🚀 Radar Dashboard")
    print(f"   Reports: {reports} files")
    print(f"   URL: http://127.0.0.1:5080")
    if '--prod' in sys.argv:
        from waitress import serve
        serve(app, host='127.0.0.1', port=5080)
    else:
        app.run(host='127.0.0.1', port=5080, debug=False)
