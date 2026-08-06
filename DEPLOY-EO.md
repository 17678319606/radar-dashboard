# 🚀 部署到腾讯云 EdgeOne Pages（EO Makers）

本项目原本是 **Flask 后端 + 本地 JSON 文件**，只能跑在本机。
这里把它改造成了**纯静态站**，可以直接托管在 EdgeOne Pages（也适用于任意静态托管）。

---

## 为什么能静态化

`app.py` 里的 API 全是「读 JSON → 返回 JSON」，没有数据库、没有服务端计算。
所以构建时用 Flask 的 `test_client` 把每个接口的响应**预渲染成静态 .json 文件**，
前端把 `fetch('/api/xxx')` 换成 `fetch('radar-api/xxx.json')`，页面表现完全一致。

| 能力 | 本地 Flask | EO 静态版 |
|------|-----------|-----------|
| 日报时间线 / 小程序机会 / 信号流 / 信息源 / 统计 | ✅ | ✅ |
| 收藏（★） | 写 `data/favorites.json` | 存浏览器 localStorage（换设备不同步） |
| 数据更新 | 跑采集脚本即时生效 | 需重新构建 + 重新部署 |

前端 hash 路由（`#/miniapp`）天然静态友好，不需要任何 rewrite 规则。

---

## 日常就跑这一条

```bash
bash update.sh        # 采集信号 → DeepSeek 生成日报 → 构建 dist/
```

拆开也行：

```bash
./venv/bin/python scripts/daily_signals.py            # 1. 采集 19 个源
./venv/bin/python scripts/gen_report.py --force       # 2. 生成今日 AI 日报（需 DeepSeek Key）
./venv/bin/python scripts/build_static.py             # 3. 构建静态站 → dist/
python3 -m http.server 8000 --directory dist          # 本地预览静态版
```

然后把 `dist/` 部署到 EdgeOne Pages（对话里说「把 radar-dashboard/dist 部署到 EdgeOne Pages」即可）。

---

## 改动清单（都向后兼容，本地 Flask 照常能跑）

| 文件 | 改动 |
|------|------|
| `scripts/build_static.py` | **新增**，静态站构建器 |
| `scripts/gen_report.py` | **新增**，用 DeepSeek API 直接生成日报（原版只能手动复制给 AI 或装 Hermes） |
| `update.sh` | **新增**，采集 + 生成日报 + 构建一键脚本 |
| `templates/index.html` | 新增静态模式适配层：`window.__STATIC_MODE__` 为真时读静态 JSON、收藏走 localStorage。**不注入时行为与原版完全一致** |
| `scripts/daily_signals.py` | 修 Key 读取 bug（见下） |

### 顺手修的两个 Key 读取 bug

原版有两个坑，按 README 填 `.env` 其实**一个 Key 都不会生效**：

1. `_get_deepseek_key()` 读的是 `scripts/.env`，而 `install.sh` 把 `.env` 生成在**项目根目录**；
2. `TRUSTMRR_API_KEY` / `PH_TOKEN` / `REDDIT_*` 只读 `os.environ`，**完全不读 .env 文件**。

现在在脚本启动时统一加载 `.env` 到环境变量，查找顺序：

```
项目根 .env  →  scripts/.env  →  ~/.hermes/.env  →  ~/.env
```

已存在的环境变量优先，不会被覆盖。

---

## 🤖 用 DeepSeek 自动生成日报

```bash
./venv/bin/python scripts/gen_report.py --dry-run        # 先看提示词和预估成本，不花钱
./venv/bin/python scripts/gen_report.py                  # 生成今天的日报
./venv/bin/python scripts/gen_report.py --date 2026-08-06 --force
./venv/bin/python scripts/gen_report.py --focus website  # 换方向
```

`--focus` 三个方向：

| 值 | 侧重 |
|----|------|
| `miniapp` | **默认**。微信小程序机会最高优先级，海外信号会做国内本地化映射 |
| `website` | 网站 / Web 应用（SaaS、工具站）方向 |
| `overseas` | 出海产品方向，重点看 MRR、定价、获客 |

单次成本：200 条信号约 1 万 tokens，**≈ ¥0.02-0.05 一次**。

---

## ⚠️ 关于访问链接

EO Makers 部署后给的预览链接形如：

```
https://<项目>.edgeone.cool?eo_token=xxx&eo_time=xxx
```

- **必须带完整的 `?eo_token=...&eo_time=...`**，去掉参数直接访问返回 **401**
- 该 token **约 3 小时后过期**，过期后重新部署会拿到新链接

想要一个长期、无 token 的地址，去 [EdgeOne 控制台](https://console.cloud.tencent.com/edgeone/pages) 找到 `radar-dashboard` 项目：
关闭预览访问保护，或绑定自己的域名。

---

## 🧑‍💻 新增数据源：1c7 中国独立开发者项目列表

信息源 `indie-dev` 来自 [github.com/1c7/chinese-independent-developer](https://github.com/1c7/chinese-independent-developer)（按「添加日期」分组的国内独立开发者项目列表）。

- **实现方式**：`scripts/daily_signals.py` 的 `fetch_indie_dev()` 抓取 README，解析顶部「最新添加日」小节，做**逐日新增检测**，写入 `data/indie_dev.json`
- **不依赖 DeepSeek Key**：纯解析入库，所以即使没配 LLM Key，这个板块也始终有内容
- **前端入口**：导航栏「🧑‍💻 独立开发者日报」（路由 `#/indie-dev`），展示最新批次日期、本次新增产品数、开发者 + 产品 + 状态
- **同时并入 LLM 日报**：`gen_report.py` 的 `indieDev` 模块会从这些每日新增里挑 1-3 个最值得关注的写进 AI 日报

---

## ⏰ 每日自动更新（已配好自动化）

已创建两个 WorkBuddy 自动化，每天自动跑「采集 → 生成日报 → 构建 → 部署 EdgeOne」：

| 自动化 | 时间 | ID |
|--------|------|-----|
| 雷达日报-每日06点更新 | 每天 06:00 | `automation-1786027906290` |
| 雷达日报-每日19点更新 | 每天 19:00 | `automation-1786027915010` |

每次运行会：
1. `bash update.sh`（采集约 20 源 + 有 Key 才生成 LLM 日报 + 构建 dist）
2. 部署到 EdgeOne Pages（原地更新同一项目 `radar-dashboard`，链接不变）
3. 把带 token 的线上链接汇总给你

> ⚠️ **LLM 日报能否自动生成，取决于 `.env` 里有没有 `DEEPSEEK_API_KEY`**。没配 Key 时，信号流和独立开发者板块照常每天更新，只是没有 AI 叙事日报。
> 配 Key：编辑 `radar-dashboard/.env`，加一行 `DEEPSEEK_API_KEY=sk-你的key`

---

## 💰 成本测算

| 项目 | 费用 | 说明 |
|------|------|------|
| 采集信号 | ¥0 | 直接抓公开源，不调 LLM |
| 生成 AI 日报（每次） | ≈ ¥0.017 | 实测 8274 tokens / 次（DeepSeek，约 200 条信号） |
| 每天 2 次（6 点 + 19 点） | **≈ ¥0.034 / 天** | |
| **每月（60 次）** | **≈ ¥1.0** | 仅 LLM 调用花钱 |
| EdgeOne Pages 静态托管 | ¥0 | 免费额度足够 |
| GitHub Actions 定时任务 | ¥0 | 公开仓库免费额度充足（每月 60 次远远用不完） |

**结论**：每天两次自动更新，纯 LLM 成本约 **¥1/月**，托管和调度都不额外花钱，**不再依赖 WorkBuddy**。

---

## 📲 推送形式建议

1. **稳定链接（最推荐）**：在 EdgeOne 控制台关闭 `radar-dashboard` 项目的「预览保护」或绑定自定义域名 → 拿到一个永久、不带 token 的链接，加到手机桌面（PWA 式书签），每天两次数据自动刷新，一戳即看。
2. **GitHub Action 完成通知（可选）**：在 `.github/workflows/daily.yml` 里加一步（如调用邮箱/Webhook）即可在每次更新后推送提醒；默认只静默更新数据，不打扰你。

> 邮件推送非必需，当前方案不强制接邮件。

---

## 数据更新节奏建议

- **外壳（HTML/JS）部署一次，永不再动**；数据由 GitHub Actions 每天 06:00 / 19:00 自动采集并提交到仓库，前端运行时从 GitHub raw 拉取最新数据。
- 只是自己本机看 → 本地 `bash start.sh` 更方便，数据即时生效，收藏也存本地文件。
- 线上版适合「随时随地用手机翻」：链接稳定、内容每天自动变、无需重新部署。

---

## 🔁 方案升级：零重新部署 + 不依赖 WorkBuddy（当前推荐）

原方案每天更新需要 WorkBuddy 触发「重新部署」，有外部依赖。新方案把**数据**与**外壳**彻底解耦：

- **外壳**（HTML/JS/CSS）部署到 EdgeOne **一次**，永不再重新部署；
- **数据**（各 `radar-api/*.json`）托管在 **GitHub raw**（实测唯一带 CORS 头、前端可直接跨域拉取的源；CNB 的 raw 返回的是 HTML 页面且不含 CORS，不可用）；
- **GitHub Actions** 每天 06:00 / 19:00（北京时间）自动跑 `update.sh` 采集 + DeepSeek 生成日报，并把新数据提交回仓库；
- 前端优先拉 GitHub raw（每日自动更新），拉取失败则回退到部署时打包的本地快照。

### 你需要做的一次性配置（约 5 分钟）

1. **建 GitHub 仓库**：在 github.com 新建一个仓库（公开，名字随意，例如 `radar-dashboard`），把本目录代码推上去：
   ```bash
   cd radar-dashboard
   git remote set-url origin https://github.com/<你的用户名>/radar-dashboard.git
   git add -A && git commit -m "init" && git push -u origin main
   ```
   > 默认分支若是 `master`，下面 raw 地址和 Action 里的分支都要改成 `master`。
2. **加 DeepSeek 密匙**：仓库 `Settings → Secrets and variables → Actions → New repository secret`，
   名字填 `DEEPSEEK_API_KEY`，值填 `sk-你的key`。不填也能跑（只是没有 AI 叙事日报，信号/独立开发者板块照常更新）。
3. **开启 Actions**：仓库 `Actions` 页确认 `雷达日报每日自动更新` 工作流已启用（push 后默认启用）。
4. **告诉前端数据地址**（二选一）：
   - **A. 改默认值（需重新部署一次外壳）**：编辑 `templates/index.html` 顶部 `REMOTE_DATA_BASE` 里的 `OWNER` 和仓库名/分支，然后重新部署 EdgeOne。
   - **B. 用 `?data=` 参数（免重新部署）**：访问时在链接后追加
     `?data=https://raw.githubusercontent.com/<你的用户名>/radar-dashboard/main/radar-api/`
     即可切到远程数据源，把这条链接存成手机书签即可。

### 验证数据在更新

- 在仓库 `Actions` 页能看到每次运行的日志；
- 直接访问 `https://raw.githubusercontent.com/<你的用户名>/radar-dashboard/main/radar-api/reports.json` 应返回最新日报；
- 打开线上站点，切换到任意板块，数据即最新。

### 相关文件

- `.github/workflows/daily.yml` — 定时采集 + 提交（**新增**）
- `templates/index.html` — `REMOTE_DATA_BASE` / `?data=` 远程优先逻辑（**新增**）
- `.gitignore` — 忽略 `.env` / `venv`（**新增**）
- `update.sh` / `scripts/*` — 采集与构建（不变）
