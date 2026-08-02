# 📡 雷达日报 Dashboard（分享版）

独立开发者的信号雷达——每天自动采集 **19 个国内外信息源**（App Store 新应用 / GitHub 热榜 / 即刻圈子 / 36氪 / 少数派 / 开源中国 / V2EX / Product Hunt / trustmrr…），生成可浏览的可视化面板，帮你发现产品机会。

> 🎁 已内置示例数据，安装完打开就能看到完整效果。

---

## ⚡ 快速开始（3 步）

```bash
# 1. 安装（创建环境 + 装依赖 + 生成配置）
bash install.sh

# 2. 启动
bash start.sh

# 3. 打开浏览器
# 访问 http://127.0.0.1:5080
```

## 📊 功能一览

| 页面 | 说明 |
|------|------|
| **日报时间线** | 每日 AI 精选日报（机会/赚钱案例/灵感/心法…） |
| **📱 小程序机会** | 聚合所有小程序选题，关键词筛选 |
| **📡 信号流** | tophub 式热榜：左侧 19 个平台，右侧紧凑榜单 |
| **🔌 信息源管理** | 各平台接入状态 |
| **⭐ 我的收藏** | 收藏单条信息 + 复制发给 AI 分析 |

## 🔄 每日数据采集

```bash
# 手动采集一次（约 20 秒，抓取 19 个平台最新信号）
python3 scripts/daily_signals.py

# 自动采集：加到系统定时任务（每天 08:45）
crontab -e
# 添加一行：
45 8 * * * cd /你的路径/radar-dashboard && /你的路径/radar-dashboard/venv/bin/python scripts/daily_signals.py >> data/collect.log 2>&1
```

采集后：
- 原始信号 → `data/raw_signals/` → 「信号流」页可见
- 每日 AI 日报 → 手动生成（见下）→ 「日报时间线」页可见

## 🤖 生成每日 AI 日报（可选）

「日报时间线」的日报需要 AI 生成。有两种方式：

### 方式 A：用任意 AI 工具（免费，无需额外配置）
1. 先跑采集：`python3 scripts/daily_signals.py`
2. 把终端输出的信号列表**复制**给任何 AI（ChatGPT/Claude/DeepSeek）
3. 让 AI 按下面的格式整理成日报 JSON：
```json
{
  "date": "2026-08-02",
  "modules": {
    "opportunities": [{"title": "机会名", "signal": "信号", "whyNow": "为什么", "suggestion": "建议", "monetization": "变现", "perspective": "视角"}],
    "moneyCases": [{"title": "案例", "what": "做什么", "revenue": "收入", "traffic": "流量", "monetization": "变现", "replicable": true}],
    "productInspirations": [{"idea": "灵感", "signal": "信号"}],
    "growthTips": [{"strategy": "策略", "scenario": "场景"}],
    "dataSignals": [{"observation": "观察", "judgment": "判断"}],
    "miniProgram": [{"title": "小程序机会", "inspiration": "启发", "suggestion": "建议", "keywords": ["关键词"], "userNeed": "需求", "painPoint": "痛点", "howToBuild": "做法", "relatedSignal": "关联"}],
    "dailyWisdom": {"method": "心法", "scenario": "场景", "steps": ["步骤"], "derivation": "推演"}
  }
}
```
4. 把 AI 返回的 JSON 保存为 `data/reports/2026-08-02.json`

### 方式 B：接入 Hermes Agent（完整自动化）
雷达日报原生跑在 [Hermes Agent](https://hermes-agent.nousresearch.com) 上，配置 cron 后每天 08:45 自动采集 → AI 生成日报 → 推送到 Telegram。

**如果朋友有 Hermes**：把 `hermes-integration/HERMES-INTEGRATION.md` 发给 Hermes 对话，让它自动配置（采集脚本注册 + skill 导入 + cron 创建）。详见该文件。

## 🔧 配置说明（.env）

全部可选，不填也能跑。**详细的申请步骤见 [`CONFIG-GUIDE.md`](CONFIG-GUIDE.md)（手把手教学）**。

| Key | 作用 | 获取 | 优先级 |
|-----|------|------|--------|
| `DEEPSEEK_API_KEY` | 英文信号自动翻译中文 | https://platform.deepseek.com/ | ⭐ 推荐 |
| `TRUSTMRR_API_KEY` | 已验证收入创业公司数据 | https://trustmrr.com/ | 🟢 可选 |
| `PH_TOKEN` | Product Hunt 每日新品 | https://www.producthunt.com/v2/oauth/applications | 🟢 可选 |
| `REDDIT_*` | Reddit 信号（IP 被封时需 OAuth） | https://www.reddit.com/prefs/apps | 🟡 可选 |

## 🗂️ 目录结构

```
radar-dashboard/
├── app.py                  # Web 后端
├── templates/index.html    # 前端页面
├── scripts/daily_signals.py # 数据采集脚本（19 源）
├── data/
│   ├── reports/            # 日报 JSON
│   ├── raw_signals/        # 原始信号 JSON
│   └── favorites.json      # 你的收藏
├── requirements.txt
├── install.sh              # 一键安装
├── start.sh                # 启动
└── .env                    # 配置（可选）
```

## ❓ 常见问题

**打开后只有示例数据？**
内置的 `2026-08-02.json`（日报 + 原始信号）是示例数据，安装完就能看效果。你采集/生成的数据会自动追加，按日期区分。

**示例数据会被覆盖吗？**
如果你某天也采集/生成了 2026-08-02 的日报，会覆盖示例（正常，说明你开始有自己的数据了）。

**没有 DeepSeek Key 会怎样？**
App Store 美国/日本/韩国、GitHub、Product Hunt 等英文内容不翻译，显示原文。其他功能正常。

**数据存在哪？**
全部在本机 `data/` 目录，纯 JSON 文本，方便备份迁移。

**想换端口？**
`start.sh` 里把 5080 改成你想要的端口。
