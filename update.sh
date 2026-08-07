#!/bin/bash
# ============================================================
# 进步分子雷达日报 — 一键更新：采集最新信号 → 重新生成静态站
# 用法: bash update.sh
# 跑完后 dist/ 就是最新的静态站，再部署到 EdgeOne Pages 即可
# ============================================================
set -e
cd "$(dirname "$0")"

PY="./venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "📡 [1/3] 采集最新信号（约 20 个源，约 30-60 秒）..."
$PY scripts/daily_signals.py 2>&1 | tail -5

echo ""
echo "🤖 [2/3] 用 DeepSeek 生成今日日报（没配 Key 会自动跳过）..."
# 统一用「上海时区」的今天作为报告日期，避免 GitHub runner(UTC) 与校验步骤(上海)的时区错位
TODAY=$(TZ=Asia/Shanghai date +%Y-%m-%d)
$PY scripts/gen_report.py --date "$TODAY" --force 2>&1 | tail -14 || true

echo ""
echo "🏗  [3/3] 生成静态站..."
$PY scripts/build_static.py

echo ""
echo "✅ 完成。接下来二选一："
echo "   • 本地看：bash start.sh          → http://127.0.0.1:5080"
echo "   • 发到线上：对 AI 说「把 radar-dashboard/dist 部署到 EdgeOne Pages」"
