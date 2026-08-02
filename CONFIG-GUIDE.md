# 🔑 API Key 申请与配置指南

雷达日报需要连接各个平台获取数据。**大部分不需要 Key 也能跑**，只有几个功能需要 Key 增强。按下面的优先级配置即可。

> 📌 全部 Key 都填在项目根目录的 `.env` 文件里（`bash install.sh` 时自动生成）。
> 格式：`KEY名=你的Key值`，一行一个，**不要加引号，不要有空格**。

---

## ⭐ 优先级 P0：DeepSeek API Key（强烈推荐，2 分钟）

**作用**：把英文信号（App Store 美/日/韩、GitHub、Product Hunt 等）自动翻译成中文。没有它，英文内容显示原文。

**申请步骤**：
1. 打开 https://platform.deepseek.com/ → 注册/登录
2. 左侧菜单 →「API Keys」→「创建 API Key」
3. 复制生成的 Key（形如 `sk-xxxxxxxx...`）
4. 填入 `.env`：
```
DEEPSEEK_API_KEY=sk-你的key
```

**费用**：充值 ¥10 能用很久（每天翻译约 100 条，成本几分钱/天）。不充值也能用，用完了翻译功能暂停，其他正常。

---

## 🟢 优先级 P1：trustmrr Key（可选，2 分钟）

**作用**：接入「已验证收入的创业公司」数据源（MRR、增长、技术栈）。

**申请步骤**：
1. 打开 https://trustmrr.com/ → 注册/登录
2. 登录后进入 Dashboard，找 **API Access** 页面
3. 复制你的 API Key（形如 `tmrr_xxxxxxxx`）
4. 填入 `.env`：
```
TRUSTMRR_API_KEY=tmrr_你的key
```

**说明**：免费额度每日有限，够用。不填 = 少一个数据源，其他正常。

---

## 🟢 优先级 P1：Product Hunt Token（可选，5 分钟）

**作用**：接入「Product Hunt 每日新品」数据源。

**申请步骤**：
1. 打开 https://www.producthunt.com/ → 注册/登录
2. 打开 https://www.producthunt.com/v2/oauth/applications → 「Create an application」
3. 填名称（随便，如 `radar`）、网站、回调地址（填 `http://localhost:5080` 即可）
4. 创建后页面上会显示 **Developer Token**，复制它
5. 填入 `.env`：
```
PH_TOKEN=你的token
```

**说明**：不填 = 少一个数据源，其他正常。

---

## 🟡 优先级 P2：Reddit OAuth（可选，5 分钟）

**作用**：解锁 Reddit 信号（r/SideProject、r/SaaS 等）。**只有当你发现 Reddit 源报错（IP 被封/403）时才需要**。

**申请步骤**：
1. 打开 https://www.reddit.com/ → 注册/登录
2. 打开 https://www.reddit.com/prefs/apps → 点「create another app...」
3. 选择类型 **script**，填名字（如 `radar`）、描述、redirect uri 填 `http://localhost:8080`
4. 创建后页面上：
   - **client_id** = 名字下方那串短码
   - **secret** = 显示的一串密钥
5. 填入 `.env`：
```
REDDIT_CLIENT_ID=你的client_id
REDDIT_CLIENT_SECRET=你的secret
REDDIT_USERNAME=你的Reddit用户名
REDDIT_PASSWORD=你的Reddit密码
```

**说明**：不填 = Reddit 源不可用（其他 18 个源正常）。

---

## 📊 配置优先级总结

| 优先级 | Key | 没有会怎样 | 难度 |
|--------|-----|-----------|------|
| ⭐ P0 | DeepSeek | 英文不翻译 | 2 分钟 |
| 🟢 P1 | trustmrr | 少一个源 | 2 分钟 |
| 🟢 P1 | Product Hunt | 少一个源 | 5 分钟 |
| 🟡 P2 | Reddit OAuth | Reddit 源不可用 | 5 分钟 |

## ✅ 配置后验证

```bash
# 跑一次采集，看各源状态
python3 scripts/daily_signals.py 2>&1 | grep "来源:"
# 应该能看到 trustmrr / Product Hunt / Reddit 等源
```

或者打开 Dashboard →「🔌 信息源管理」页面，看各平台状态灯：
- 🟢 正常 = 配置成功
- 🟡 需配置 = 没填对应 Key
- 🔴 异常 = 有报错

## ⚠️ 安全提醒

- `.env` 文件包含你的 Key，**不要发给任何人、不要上传到 GitHub**
- 如果 Key 泄露，去对应平台删除/重置即可
- 采集脚本只从环境变量 / `.env` 读取 Key，代码里没有硬编码任何 Key
