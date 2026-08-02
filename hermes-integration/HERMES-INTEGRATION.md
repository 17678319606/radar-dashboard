# 🤖 Hermes Agent 集成指南

雷达日报分享版可以独立运行（`bash install.sh` + `bash start.sh`），**不需要 Hermes**。

但如果你已经安装了 [Hermes Agent](https://hermes-agent.nousresearch.com)，可以让它帮你**全自动管理**：每天定时采集 → AI 生成日报 → 推送到 Telegram，全程无人值守。

---

## 方式一：让 Hermes 自动配置（推荐）

把整个包解压后，在 Hermes 对话里说：

```
我拿到了雷达日报分享版，解压在 ~/radar-dashboard-dist/
帮我配置成每天自动运行：
1. 把 scripts/daily_signals.py 放到 ~/.hermes/scripts/
2. 导入 hn-daily-radar skill（在 hermes-integration/ 里）
3. 配置 cron 每天 08:45 自动采集+生成日报
4. 告诉我怎么填 .env 的 Key
```

Hermes 会自动完成配置。之后每天它会：
1. 08:45 自动运行采集脚本（19 个信息源）
2. AI 生成 8 模块日报（含小程序机会）
3. 保存到 `data/reports/`（Dashboard 自动展示）
4. 推送到你的 Telegram

## 方式二：手动配置（想自己控制）

### 1. 注册采集脚本

```bash
mkdir -p ~/.hermes/scripts
cp radar-dashboard-dist/scripts/daily_signals.py ~/.hermes/scripts/
```

### 2. 导入 skill

```bash
# 把 hermes-integration/hn-daily-radar-SKILL.md 的内容导入为 skill
# 在 Hermes 里执行：skill_manage(action='create', name='hn-daily-radar', content=<文件内容>)
```

### 3. 配置 cron

在 Hermes 里创建 cron 任务（示例参数）：

```
job name: hn-daily-radar
schedule: 45 8 * * *          # 每天 08:45 (UTC+8)
script:   daily_signals.py    # 采集脚本
prompt:   参考 hn-daily-radar skill 的日报生成指令
deliver:  origin              # 或指定 Telegram 群
```

### 4. 配置 Key

**Hermes 用户通常什么都不用配**：如果你的 `~/.hermes/.env` 已有 `DEEPSEEK_API_KEY`（Hermes 主模型用的就是它），采集脚本会自动读取，无需重复配置。

按需补充其他 Key（编辑 `~/.hermes/.env` 或对话里告诉 Hermes）：

```
DEEPSEEK_API_KEY=你的Key      # 英文自动翻译中文（推荐，Hermes 已配则跳过）
TRUSTMRR_API_KEY=你的Key      # 已验证收入创业公司数据（推荐）
PH_TOKEN=你的Token            # 可选
REDDIT_CLIENT_ID=...          # 可不配（易风控，见下）
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
```

> ⚠️ **Reddit 建议不配**：Reddit 对数据中心 IP 风控严格，容易 403/封 IP，配置后也未必稳定。不配不影响其他 18 个源，等真遇到需要再说。

**Key 申请步骤见 `../CONFIG-GUIDE.md`**（手把手教学：DeepSeek / trustmrr / Product Hunt / Reddit 每个都写了去哪申请、怎么填，并标注了优先级）。也可以直接对 Hermes 说「帮我申请 DeepSeek API Key 需要做什么」，它会给你指引。

## ⚠️ 安全提醒

- 采集脚本只从**环境变量 / .env 文件**读取 Key，**没有硬编码任何 Key**（已扫描确认）
- 不要把 `.env` 文件发给别人
- Key 泄露后去对应平台重置即可
