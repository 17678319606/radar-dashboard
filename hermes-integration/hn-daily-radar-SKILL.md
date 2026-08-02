---
name: hn-daily-radar
version: "3.2"
description: "独立开发者雷达日报 — 多通道信号采集 (trustmrr + IndieHackers + Reddit + Product Hunt)，7模块日报 + 今日心法"
tags:
  - research
  - daily
  - indie-hackers
  - signals
  - multi-source
---

# 独立开发者雷达日报 v3

## 是什么

每天从 4 个独立开发者核心数据源并行采集最新信号，生成 **7 模块电报日报**，专为出海独立开发者设计。核心价值：**增量追踪 + 多源交叉验证 + 数据驱动方法论提取**。

## 数据源

| 数据源 | 获取方式 | 需要 Key？ | 数据特点 |
|--------|---------|-----------|---------|
| **trustmrr.com** | REST API (`/api/v1/startups`) | ✅ `tmrr_` 前缀免费 Key | MRR、增长、技术栈、国家 |
| **IndieHackers** | Algolia Search API (stories 索引) | ❌ 无需 Key | 创始人故事、收入数据、公司名 |
| **Reddit** | OAuth API（推荐）/ JSON API / pullpush 镜像 | 需要 OAuth（推荐） | 新产品讨论、创业话题 |
| **Product Hunt** | GraphQL API v2 | ✅ 免费 Developer Token | 每日新品列表、描述、投票 |
| **GitHub 总榜** | HTML scraping (`github.com/trending`) | ❌ 无需 Key | 每日热榜仓库、star 增长 |
| **GitHub JS榜** | HTML scraping (`/trending/javascript`) | ❌ 无需 Key | JS/TS 技术栈热榜（小程序参考） |
| **GitHub 中文榜** | HTML scraping (`?spoken_language_code=zh`) | ❌ 无需 Key | 中文社区热门仓库 |
| **V2EX** | JSON API (`/api/topics/show.json`) | ❌ 无需 Key | 国内技术/创业社区（分享创造/程序员节点） |
| **36氪** | RSS (`36kr.com/feed`) | ❌ 无需 Key | 创投、融资、科技公司动态 |
| **少数派** | RSS (`sspai.com/feed`) | ❌ 无需 Key | 效率工具、数字生活、App 推荐 |
| **开源中国** | RSS (`oschina.net/news/rss`) | ❌ 无需 Key | 开源项目发布、技术新闻 |
| **即刻·AI探索站** | RSSHub (`/jike/topic/63579abb6724cc583b9bba9a`) | ❌ 无需 Key | AI 应用/产品一手讨论 |
| **即刻·人工智能讨论组** | RSSHub (`/jike/topic/55fadac08cc2e30e00e2e42a`) | ❌ 无需 Key | AI 技术/内容讨论 |
| **即刻·工程师的日常** | RSSHub (`/jike/topic/577c5a122fa95b1100da059f`) | ❌ 无需 Key | 程序员圈子生态 |

详细 API 参考见 `references/` 目录：
- `references/trustmrr-api.md` — 完整端点、字段、分页、定价模式、**分类市场调研示例**、nullable 字段处理
- `references/indiehackers-algolia.md` — Algolia Search API 逆向方案、可用字段、查询模式
- `references/reddit-json-api.md` — Reddit JSON API 端点、字段、子版块质量评估、24h 过滤
- `references/producthunt-graphql.md` — PH GraphQL 查询模式、字段列表、pitfalls

## 脚本

主脚本：`~/.hermes/scripts/daily_signals.py`

```
并行采集 (ThreadPoolExecutor, max_workers=5, ~12s)
    ↓
增量对比 (per-source seen_ids, ~/.hermes/cron/data/daily_signals_state.json)
    ↓
输出统计行 (TOTAL_NEW=N) + 结构化数据 → 注入 cron prompt context
    ↓\nLLM Agent → 8模块精选 + 今日心法\n    ↓\n保存结构化 JSON → ~/.hermes/cron/data/reports/YYYY-MM-DD.json (新增)\n    ↓\nTelegram 广告群 (不变)\n```

## 日报模板（7+1 模块）

```
📡 独立开发者雷达日报 — 月/日

1️⃣ 今日机会 (2-3个)
信号 → 为什么能做 → 建议 → 变现路径

2️⃣ 今日赚钱案例 (1个)
做什么 | 月收入 | 流量 | 变现 | 能否复制

3️⃣ 今日产品灵感 (1个)
具体产品 idea

4️⃣ 今日增长技巧 (1条)
可执行的具体策略

5️⃣ 今日工具 (可选)
推荐的工具

6️⃣ 今日踩坑 (1个)
值得警惕的教训

7️⃣ 今日数据信号 (2-3条)
趋势观察 + 判断

8️⃣ 微信小程序机会 (2-3条) ★新增
把当天海外信号映射到国内微信小程序机会

🎯 今日心法
从当天数据中反向提炼的可复用方法论
```

## Cron Prompt Template

用于 cron job 的 system prompt。LLM Agent 会阅读脚本输出的数据 + 以下指令生成日报：

```
[SYSTEM]
你是出海独立开发者的每日信号雷达系统。

背景：用户是出海 Web 应用独立开发者，专注于为全球市场构建 Web 工具。
核心关注点：海外用户的痛点和未满足的需求、新产品/工具解决的具体问题、SaaS/B2B/独立开发赛道的新机会、适合单人/小团队做的 Web 应用方向、定价策略、分发策略、用户获取。

上方是脚本从 4 个数据源采集的每日新信号：
- trustmrr.com — 已验证收入的创业公司数据（MRR、增长、技术栈）
- IndieHackers — 独立开发者故事与案例研究
- Reddit (r/SideProject, r/SaaS, r/startups) — 新产品讨论
- Product Hunt — 今日新品

你的任务：阅读所有信号，生成 7 模块 + 今日心法 电报日报。

[今日心法规则 - 重要]
- 不要从固定方法库选题
- 必须从当天数据中逆向提炼一个可复用的方法论
- 必须包含 4 个层次：方法是什么 → 实战场景 → 具体做法（分步骤）→ 用当天数据推演一遍
- 核心是 "从今天的信号里抽丝剥茧，形成可迁移的思考框架"

[模块内容规则]
各模块的内容结构（应对素材不足时可跳过该模块）：
- 1️⃣ 今日机会：每个机会点包含 信号来源 | 为什么现在能做 | 建议怎么做 | 变现路径建议
- 2️⃣ 今日赚钱案例：用什么 | 月收入 | 拿流量方式 | 变现方式 | 能不能复制
- 4️⃣ 今日增长技巧：必须是可执行的具体策略，不是抽象建议
- 7️⃣ 今日数据信号：每条带趋势观察 + 判断
- 8️⃣ 微信小程序机会（最高优先级）：把当天信号「翻译」成国内微信小程序赛道的机会。
  - **数量**：每天 3-5 条（素材丰富时 5 条），不要只写 2 条
  - **多样性**：覆盖不同方向（工具/内容/服务/电商/教育等），避免同质化
  - 每条包含：标题 | 启发（哪条信号）| 建议（做什么）| 关键词 | 用户需求 | 痛点 | 做法（MVP/技术/分发）| 关联信号
  - 背景：用户是个人独立开发者，正在研究微信小程序开发，需要的是「海外/国内已验证模式 → 小程序落地」的具体映射，不是泛泛科普。
- 🎯 今日心法：方法本身（一句话）→ 实战场景 → 具体做法（分步骤）→ 用今天的数据推演

[输出约束]
- ❌ 不列所有信号，只精选 3-5 条最有价值的
- ❌ 不写大段分析
- ✅ 每条精选带独立开发者视角的一句话解读（格式：> 🧠 独立开发者视角：...）
- ✅ 今日心法必须基于当天数据，不能是固定套路
- ✅ 素材不足时可跳过某模块
- ✅ 保持 Telegram 原生 markdown
- ✅ 在输出电报日报前，先用终端工具将结构化数据保存到 ~/.hermes/cron/data/reports/{当前日期}.json
  JSON 格式参考（使用 write_file 或 patch 工具）：
  {
    "date": "YYYY-MM-DD",
    "sources": {"trustmrr": N, "indiehackers": N, "reddit": N, "producthunt": N},
    "tags": ["关键词1", "关键词2"],
    "modules": {
      "opportunities": [{"title":"...","signal":"...","whyNow":"...","suggestion":"...","monetization":"...","perspective":"..."}],
      "moneyCases": [{"title":"...","what":"...","revenue":"...","traffic":"...","monetization":"...","replicable":true/false,"perspective":"..."}],
      "productInspirations": [{"idea":"...","signal":"...","suggestion":"..."}],
      "growthTips": [{"strategy":"...","signal":"...","scenario":"..."}],
      "tools": [{"tool":"...","description":"..."}],
      "pitfalls": [{"lesson":"...","signal":"..."}],
      "dataSignals": [{"observation":"...","judgment":"..."}],
      "miniProgram": [{"inspiration":"...","suggestion":"...","keywords":["..."],"userNeed":"...","painPoint":"...","howToBuild":"...","relatedSignal":"..."}],
      "dailyWisdom": {"method":"...","scenario":"...","steps":[...],"derivation":"..."}
    }
  }
  无内容的模块可以省略或留空数组。之后正常输出电报日报。
```

## 增量追踪

- 每个源独立追踪 `seen_ids`
- 状态文件: `~/.hermes/cron/data/daily_signals_state.json`
- 每源上限 5000 ID，自动裁剪
- 只有 `TOTAL_NEW > 0` 时才会触发日报

## 手动/按需运行（Ad-Hoc）

当用户说"帮我跑一下雷达日报"时的标准流程：

### 步骤

1. **加载本 skill** — `skill_view(name='hn-daily-radar')`
2. **运行采集脚本** — `python3 ~/.hermes/scripts/daily_signals.py`（等待 ~10s）
3. **检查输出** — 看 `TOTAL_NEW` 行。如果 `TOTAL_NEW=0`，告知用户无新信号并停止
4. **如果 `TOTAL_NEW > 0`** — 基于脚本输出的结构化数据，按下方「日报模板」生成 7 模块 + 今日心法
5. **关键处理逻辑**：
   - 脚本输出包含分源统计数据（PRODUCTHUNT_NEW、TRUSTMRR_NEW 等）—— 只从有新信号的源里精选
   - 不要逐条列出所有信号，只精选 3-5 条最有价值的
   - 每条精选加 `> 🧠 独立开发者视角：` 的一句话解读
   - 素材不足的模块直接跳过
   - 今日心法必须从当天数据中逆向提炼，不是固定套路

### 注意事项

- Reddit 403 和 IndieHackers 超时是已知的间歇性故障（见「故障排查」），不影响其他源
- Product Hunt 新品的 vote 数通常为 0（刚上线），不必在意
- 首次运行会看到大量 NEW（所有数据都是新的），后续只输出增量
- 按需运行不会影响 cron 的状态追踪——脚本自动读写同一个 `seen_ids` 文件

## 设置步骤

### 1. 创建 cron job（长期自动化）

```bash
# 使用 cronjob 工具:
# - script: daily_signals.py
# - schedule: 45 8 * * * (08:45 UTC+8)
# - deliver: origin (发送回创建时的对话)
# - enabled_toolsets: ["terminal", "file"]
# - prompt: 见上方 Cron Prompt Template
```

### 2. 配置环境变量

```bash
# trustmrr API Key (必填)
export TRUSTMRR_API_KEY="tmrr_xxx"

# Product Hunt Token (可选，填了才启用 PH 源)
export PH_TOKEN="xxx"
```

### 3. 初始化状态

首次运行会看到大量 NEW（所有数据都是新的），之后只输出增量。

### 4. 启动可视化 Dashboard (可选)

```bash
cd ~/projects/radar-dashboard
python3 app.py --prod
# 访问 http://127.0.0.1:5080
```

Dashboard 特性：日报时间线 / 单日详情 / 跨日模块聚合（机会库、赚钱案例库等）/ 统计趋势。
数据自动从 `~/.hermes/cron/data/reports/` 读取，每次 cron 生成日报时会自动写入 JSON。

## 关键设计原则

1. **并行采集** — ThreadPoolExecutor 4 路同时抓取，总耗时 ≈ 最慢源
2. **零外部依赖** — Algolia 和 Reddit JSON API 均免费免认证
3. **增量驱动** — 不重复推送已见过内容
4. **数据驱动心法** — 今日心法必须从当天数据中逆向提炼，禁止固定套路
5. **模块可跳过** — 当天素材不足时省略对应模块

## 故障排查（Cron 环境）

### 脚本因 Python 依赖崩溃

cron job 运行时的 PATH 和 Python 环境与交互式 shell **不同**。脚本可能因缺少依赖而崩溃：

```
ModuleNotFoundError: No module named 'bs4'
ModuleNotFoundError: No module named 'requests'
```

**排查步骤：**
1. 检查脚本 shebang：`head -5 ~/.hermes/scripts/daily_signals.py` — 确认用的是 `/usr/bin/env python3` 还是硬编码路径
2. 验证该 Python 是否能 import 所有依赖：`python3 -c "from bs4 import BeautifulSoup; import requests; print('ok')"`
3. 如果脚本用的 Python 与 shell 不同（如 conda 环境），在 crontab 中显式设置 `PATH` 和 `PYTHONPATH`，或在 cron job 工具的 `env` 字段中传入 `PATH=/opt/miniconda3/bin:$PATH`
4. 修复后，手动运行一次脚本验证通过再等下次 cron 触发

### 状态文件被污染（脚本部分失败后重跑无新数据）

脚本在采集完成后**立即保存状态文件**。如果脚本在中途崩溃但状态已保存：
- `seen_ids` 已更新，重跑脚本会输出 `TOTAL_NEW=0`，数据不可恢复
- 结果：脚本退出了但日报没生成 → 当天口报丢失

**恢复步骤：**
```bash
# 1. 查看备份是否存在
ls -la ~/.hermes/cron/data/daily_signals_state.json.bak

# 2. 如果有备份，恢复
cp ~/.hermes/cron/data/daily_signals_state.json.bak ~/.hermes/cron/data/daily_signals_state.json

# 3. 如果没有备份，删除状态文件全新采集（会看到大量 NEW）
rm ~/.hermes/cron/data/daily_signals_state.json
python3 ~/.hermes/scripts/daily_signals.py

# 4. 采集成功后保存输出，再手动写日报
```

**预防：** 在手动运行脚本或修改环境后，**先备份状态文件**再执行。

### 脚本成功但 `TOTAL_NEW=0`

- 检查状态文件是否已有大量 `seen_ids`（首次运行后正常）
- 检查各源计数：`python3 ~/.hermes/scripts/daily_signals.py 2>&1 | grep "_NEW="`
- Product Hunt Token 过期也会导致 PH 源返回 0 — 验证 token 是否有效

### Reddit 403 (IP 被封)

Reddit 对数据中心 IP 限制严格，`/r/{sub}/new.json` 直接 403（换 UA 无效）。

**推荐方案：OAuth**（唯一可靠）
1. 打开 https://www.reddit.com/prefs/apps → 创建 app → 选 **script** 类型
2. 记下 `client_id`（app 名称下方短串）和 `secret`
3. 配置环境变量后重跑：
```bash
export REDDIT_CLIENT_ID="你的client_id"
export REDDIT_CLIENT_SECRET="你的secret"
export REDDIT_USERNAME="你的Reddit用户名"
export REDDIT_PASSWORD="你的Reddit密码"
```
4. 脚本自动用 OAuth（oauth.reddit.com）抓取，绕过 IP 封锁。Token 缓存 24h。

**兜底通道**：脚本自动降级尝试 pullpush.io 镜像（注意：pullpush 数据滞后数天，仅作最后兜底）。

## Pitfalls & Gotchas

- trustmrr 的 MRR 字段是 float 且单位是 cents — 显示前必须 `int(round(mrr))`
- IndieHackers 是 Ember SPA，页面无 SSR — **不要尝试 requests+BS4 爬取**，走 Algolia
- Reddit 的 `score` 对于新帖经常为 1（投票模糊化）— 不能只看分数
- Reddit 必须设置独特的 `User-Agent`，且 **不能伪造浏览器 UA**
- **PH GraphQL**: `makers { nodes { name } }` 和 `dailyRank` **都不能用** — User 类型没有 `nodes` 字段，`dailyRank` 未声明。会导致整个 `posts` 返回 null。详见 `references/producthunt-graphql.md`
- PH Token 获取后需重启 cron 或等待下次触发
- 脚本文件在 `~/.hermes/scripts/`（不是 skill 目录内）— cron job 通过 script 参数引用
- **Cron 环境差异**：cron 的 PATH 不包含 conda/nix/brew 路径 — 依赖缺失是 #1 崩溃原因。手动测试通过 ≠ cron 下能通过
- **bs4 依赖仍在**：虽然 IndieHackers 改用 Algolia，但脚本顶部 `from bs4 import BeautifulSoup` 残留，cron 环境缺失 bs4 会直接崩溃
