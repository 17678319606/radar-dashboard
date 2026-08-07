#!/bin/bash
# ============================================================
# 进步分子雷达日报 Dashboard — 启动脚本
# 用法: bash start.sh
# ============================================================
cd "$(dirname "$0")"

# 激活虚拟环境
if [ -d "venv" ]; then
  source venv/bin/activate
fi

echo "🚀 进步分子雷达日报 Dashboard 启动中..."
echo "   URL: http://127.0.0.1:5080"
echo "   (Ctrl+C 停止)"

# 启动服务（生产模式 waitress）
python3 -c "from waitress import serve; from app import app; serve(app, host='127.0.0.1', port=5080)"
