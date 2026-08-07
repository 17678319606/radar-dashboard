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

    # sitemap.xml：首页 + 每一期日报
    urls = [f"{SITE_URL}/"]
    for f in sorted(REPORTS_DIR.glob('*.json'), reverse=True):
        urls.append(f"{SITE_URL}/#/daily/{f.stem}")
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
            f'      <title>进步分子日报 {date}</title>\n'
            f'      <link>{site_url}/#/daily/{date}</link>\n'
            f'      <guid isPermaLink="false">{site_url}/#/daily/{date}</guid>\n'
            f'      <pubDate>{pub}</pubDate>\n'
            f'      <description>{desc}</description>\n'
            '    </item>'
        )
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        '  <title>进步分子日报</title>',
        f'  <link>{site_url}/</link>',
        '  <description>每日自动采集 20+ 信息源，生成独立开发者 / 副业赚钱机会雷达。</description>',
        '  <language>zh-CN</language>',
        f'  <image><url>{site_url}/donate-qrcode.jpg</url><title>进步分子日报</title><link>{site_url}</link></image>',
    ] + items + ['</channel></rss>']
    (out_dir / 'rss.xml').write_text('\n'.join(xml) + '\n', encoding='utf-8')
    print(f'   SEO: rss.xml（{len(items)} 期）')


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
