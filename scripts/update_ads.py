#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雷达日报 · 广告配置助手
─────────────────────────
只在 site.json 的 ads 段里改配置，**不改动任何模板/前端代码**；
改完只重建 radar-api/config.json（站点级配置），无需重新打整个静态站。
用法示例：
  # 接入 AdSense 自动广告（粘贴你的发布商 ID，零代码生效）
  python scripts/update_ads.py --adsense-client ca-pub-1234567890

  # 启用某个广告位并写入自定义 HTML
  python scripts/update_ads.py --slot top-banner --enable \
      --content "<div style='...'>📢 你的广告</div>"

  # 关闭某个广告位
  python scripts/update_ads.py --slot sidebar --disable

  # 关闭所有广告（含 AdSense）
  python scripts/update_ads.py --off

改完记得把 dist/ 重新部署到 EdgeOne（对 AI 说「部署 radar-dashboard 到 EdgeOne」即可）。
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SITE_JSON = BASE_DIR / "data" / "config" / "site.json"


def load_site():
    if not SITE_JSON.exists():
        print(f"❌ 找不到 {SITE_JSON}")
        sys.exit(1)
    return json.loads(SITE_JSON.read_text(encoding="utf-8"))


def save_site(cfg):
    SITE_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_config_json():
    """只重建 radar-api/config.json（站点级配置，不含日报数据）"""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from app import app
        data = app.test_client().get("/api/config").get_json()
    except Exception as e:
        print(f"⚠️ 无法用 Flask 重建 config.json（{e}）；将直接回写 site.json 内容作为兜底。")
        cfg = load_site()
        data = cfg.get("ads") and cfg or cfg
    targets = [
        BASE_DIR / "dist" / "radar-api" / "config.json",
        BASE_DIR / "radar-api" / "config.json",
    ]
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"✅ 已重建 config.json：{len(targets)} 处")


def main():
    p = argparse.ArgumentParser(description="雷达日报广告配置助手")
    p.add_argument("--adsense-client", default=None, help="AdSense 发布商 ID，如 ca-pub-xxxx（留空则关闭自动广告）")
    p.add_argument("--slot", default=None, help="广告位 id，如 top-banner / sidebar / inline-after-header")
    p.add_argument("--enable", action="store_true", help="启用指定广告位")
    p.add_argument("--disable", action="store_true", help="关闭指定广告位")
    p.add_argument("--content", default=None, help="自定义广告位 HTML 内容")
    p.add_argument("--off", action="store_true", help="关闭全部广告（含 AdSense）")
    p.add_argument("--on", action="store_true", help="开启广告总开关")
    args = p.parse_args()

    cfg = load_site()
    ads = cfg.setdefault("ads", {})
    changed = False

    if args.off:
        ads["enabled"] = False
        ads["adsenseClient"] = ""
        for s in ads.get("slots", []):
            s["enabled"] = False
        changed = True
        print("🚫 已关闭全部广告（含 AdSense）")
    if args.on:
        ads["enabled"] = True
        changed = True
        print("✅ 已开启广告总开关")

    if args.adsense_client is not None:
        ads["adsenseClient"] = args.adsense_client.strip()
        ads["enabled"] = True
        changed = True
        if ads["adsenseClient"]:
            print(f"🔗 已设置 AdSense 发布商：{ads['adsenseClient']}（自动广告将在下次部署后生效）")
        else:
            print("🔗 已清空 AdSense 发布商（自动广告关闭）")

    if args.slot:
        slot = next((s for s in ads.get("slots", []) if s.get("id") == args.slot), None)
        if not slot:
            print(f"❌ 未找到广告位：{args.slot}（可用：{', '.join(s.get('id') for s in ads.get('slots', []))}）")
            sys.exit(1)
        if args.enable:
            slot["enabled"] = True
            ads["enabled"] = True
            changed = True
        if args.disable:
            slot["enabled"] = False
            changed = True
        if args.content is not None:
            slot["content"] = args.content
            slot["type"] = "html"
            slot["enabled"] = True
            ads["enabled"] = True
            changed = True
        print(f"🎯 广告位 {args.slot}：enabled={slot.get('enabled')}")

    if not changed:
        print("ℹ️ 未做任何改动。可用参数见脚本头部注释。")
        print(f"   当前：enabled={ads.get('enabled')}, adsenseClient={ads.get('adsenseClient') or '(空)'}")
        return

    save_site(cfg)
    rebuild_config_json()
    print("📌 下一步：把 dist/ 重新部署到 EdgeOne（对 AI 说「部署 radar-dashboard 到 EdgeOne」）。")


if __name__ == "__main__":
    main()
