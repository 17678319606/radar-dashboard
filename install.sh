#!/bin/bash
# ============================================================
# 雷达日报 Dashboard — 一键安装脚本
# 用法: bash install.sh
# ============================================================
set -e

echo "🚀 雷达日报 Dashboard 安装中..."
cd "$(dirname "$0")"

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
  echo "❌ 未找到 Python3，请先安装: https://www.python.org/downloads/"
  exit 1
fi
echo "✅ Python3: $(python3 --version)"

# 2. 创建虚拟环境
if [ ! -d "venv" ]; then
  echo "📦 创建虚拟环境..."
  python3 -m venv venv
fi
source venv/bin/activate

# 3. 安装依赖
echo "📥 安装依赖..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✅ 依赖安装完成"

# 4. 创建数据目录
mkdir -p data/reports data/raw_signals

# 5. 配置提示
if [ ! -f ".env" ]; then
  cat > .env << 'EOF'
# ============================================================
# 雷达日报 配置（可选，全部不填也能跑，只是功能少一些）
# ============================================================

# 【强烈推荐】DeepSeek API Key — 用于把英文信号自动翻译成中文
# 获取: https://platform.deepseek.com/
DEEPSEEK_API_KEY=

# 【可选】trustmrr Key — 已验证收入创业公司数据
# 获取: https://trustmrr.com/
TRUSTMRR_API_KEY=

# 【可选】Product Hunt Token — 每日新品
# 获取: https://www.producthunt.com/v2/oauth/applications
PH_TOKEN=

# 【可选】Reddit OAuth — 解锁 Reddit 信号（IP 被封时需要）
# 获取: https://www.reddit.com/prefs/apps 创建 script app
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USERNAME=
REDDIT_PASSWORD=
EOF
  echo "✅ 已生成 .env 配置文件（可选填写 Key）"
fi

echo ""
echo "🎉 安装完成！"
echo ""
echo "  启动:    bash start.sh"
echo "  访问:    http://127.0.0.1:5080"
echo "  采集:    python3 scripts/daily_signals.py"
echo ""
echo "  💡 没有 DeepSeek Key 也能跑，只是英文内容不会自动翻译"
echo "  💡 详细说明见 README.md"
echo "  💡 API Key 申请步骤见 CONFIG-GUIDE.md（手把手教学）"
