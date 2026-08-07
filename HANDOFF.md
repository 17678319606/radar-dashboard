# 进步分子雷达日报 · 交接与运维手册（HANDOFF）

> 本文件供「换团队 / 后续迭代」快速上手。项目已在本轮（v11）做全面体检与收口，自动化、SEO、阅读体验、数据安全均达标，可长期无人值守运行。

## 1. 项目简介
- **产品**：进步分子雷达日报 —— 面向独立开发者 / 产品人的每日技术资讯速读站。
- **内容来源**：自动聚合 16+ 公开信息源（GitHub / Hacker News / Lobsters / Reddit 副业 / Product Hunt / 阮一峰周刊 / App Store 中美的日韩台等），由 DeepSeek 生成中文速读日报（10+ 模块）。
- **运行成本**：DeepSeek ≈ ¥0.109/次，每日 2 次 ≈ **¥0.22/天**；无第三方付费依赖。

## 2. 技术架构
- **前端**：单文件 SPA（`templates/index.html`，内联 CSS + 原生 JS，hash 路由）。
- **后端（仅构建期）**：`app.py`（Flask），提供只读 JSON API；`scripts/build_static.py` 用 Flask `test_client` 把 API 预渲染为静态 JSON + **每期日报真实静态 HTML 页**（`dist/daily/{date}.html`），供 SEO 收录。
- **托管**：EdgeOne Pages（静态托管）。前端**远程源优先**（jsDelivr 镜像的仓库 `radar-api/`），本地 `dist/radar-api` 快照仅兜底 → **一次部署、每日自动更新，无需重部署**。
- **自动化**：GitHub Actions（`.github/workflows/daily.yml`），北京时间 06:00 / 19:00 触发。

## 3. 每日自动化流程（无人值守）
```
GitHub Actions (cron)
  → daily_signals.py   采集 16+ 信源原始信号
  → gen_report.py      DeepSeek 生成日报 JSON（无 Key 时自动无-LLM 兜底 + 1 次重试）
  → build_static.py    预渲染 JSON + 静态 HTML + sitemap/rss/og
  → 回推仓库 (git commit radar-api/ data/reports ...)
  → 校验：日报日期 == 今天？推送后 CDN 端到端是否可达？
  → 失败时自动建 GitHub Issue 通知（站内 + 邮件）
前端（用户访问）→ 远程拉取当日最新日报
```

## 4. 数据安全 & 密钥（重要）
- **DeepSeek API Key**：仅存在于 **GitHub Actions 加密 Secret**（`DEEPSEEK_API_KEY`），绝不在前端、也不入库。本地开发读 `.env`（已 gitignore）或 macOS Keychain。
- **Git 推送 PAT**：部署用的 `ghp_...` PAT 仅用于本地 `git push`，**不写入任何仓库文件**。如担忧泄露，可在 GitHub → Settings → Tokens 直接吊销重发，不影响项目运行。
- **无 PII**：站点不采集用户邮箱 / 账号（订阅引导仅外链到 jinbufenzi.com，本站不存）。
- 全仓库已扫描确认无 `ghp_` / `sk-` 明文。

## 5. 如何迭代（最小上手路径）
1. 改代码：`scripts/*.py`、`templates/index.html`、`data/config/site.json`。
2. `git push origin main` → Actions 自动跑批、生成内容、回推、前端次日自动生效。
3. **仅当改了前端外壳/结构**才需重新部署 EdgeOne（`dist/` 重新生成并部署）；纯内容更新不需重部署（远程源优先）。
4. 本地预览：`python3 -m http.server 8000 --directory dist`。

## 6. 密钥轮转步骤
- 登录 GitHub → 仓库 Settings → Secrets and variables → Actions → 编辑 `DEEPSEEK_API_KEY` 为新值 → 下次跑批自动生效。
- 如需换 DeepSeek 模型/基址：改 `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` 两个 Secret 即可。

## 7. 如何验证健康（无需登服务器）
- **CI 状态**：GitHub → Actions → `daily.yml` 应每日 2 次 success；失败会自动开 Issue。
- **内容新鲜**：访问站点，或 `curl https://raw.githubusercontent.com/17678319606/radar-dashboard/main/radar-api/reports.json` 看最新 `date` 是否为今天。
- **SEO 收录**：sitemap `https://<域名>/sitemap.xml` 指向真实 `/daily/{date}.html` 页（非 `#/` 哈希）。

## 8. 已知限制 / 风险（留给未来团队）
- **预览域名**：当前部署在 EdgeOne 预览子域 `radar-dashboard-7zsuaod4.edgeone.cool`，非品牌稳定域名。如需品牌域名，可将 `jinbufenzi.com` 子域 CNAME 到 EdgeOne 并修改 `build_static.py` 的 `SITE_URL`（影响 sitemap/canonical/og）。
- **jsDelivr 缓存**：远程源有短缓存，CI 已做「推送后 60s 可达性」校验降低风险。
- **本地构建需 venv**：`pip install flask requests` 到 `venv/`。
- **单期日报静态页**已生成，但 Google/Bing 收录需时间，非即时。

## 9. 备份基线
- 代码基线已打 tag：**`v11-final`**（本轮收口）。
- 所有数据随仓库 `radar-api/` 提交，天然备份在 GitHub。
- 如需整站快照：导出 `radar-api/` + `data/` 即可。

---
*生成于 v11 收口迭代（2026-08-08）。维护者：产品战略团队 AI 协作。重要决策以产品负责人审定为准。*
