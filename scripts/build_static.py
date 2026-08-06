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
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app, REPORTS_DIR  # noqa: E402

RAW_DIR = REPORTS_DIR.parent / 'raw_signals'

# 前端 index.html 会请求的模块名（与 app.py 的 module_map 对应）
MODULE_NAMES = [
    'opportunities', 'money-cases', 'inspirations', 'growth',
    'tools', 'pitfalls', 'signals', 'mini-program', 'wisdom', 'indie-dev',
]

INJECT_SNIPPET = (
    "<script>window.__STATIC_MODE__ = true;</script>\n"
    "<!-- 静态部署模式：API 读预渲染 JSON，收藏存 localStorage -->\n"
)


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
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

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
