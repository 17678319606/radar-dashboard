#!/usr/bin/env python3
"""对 radar-dashboard 小程序机会页截图（供 README 使用）"""
import asyncio, glob, sys
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:5080/#/miniapp"
OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/screenshot-miniapp.png"
VIEWPORT_W = int(sys.argv[2]) if len(sys.argv) > 2 else 1280

# 找 playwright 缓存的 chromium（兼容多个版本路径）
import os
home = os.path.expanduser("~")
candidates = sorted(glob.glob(
    f"{home}/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
))
headless_candidates = sorted(glob.glob(
    f"{home}/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac*/chrome-headless-shell"
))
executable = candidates[-1] if candidates else None
if executable is None and headless_candidates:
    executable = headless_candidates[-1]

async def main():
    async with async_playwright() as p:
        kw = {"executable_path": executable} if executable else {}
        browser = await p.chromium.launch(**kw)
        page = await browser.new_page(viewport={"width": VIEWPORT_W, "height": 900},
                                      device_scale_factor=2)
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        # 等卡片渲染完成
        await page.wait_for_selector(".mp-card", timeout=8000)
        await page.wait_for_timeout(500)
        await page.screenshot(path=OUT, full_page=True)
        await browser.close()
        print(f"OK: {OUT}")

asyncio.run(main())
