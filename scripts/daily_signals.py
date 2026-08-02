#!/usr/bin/env python3
"""
daily_signals.py — 多渠道独立开发者信号采集器 v3 (重构版)
===========================================================
并行抓取 4 个数据源:
  1. trustmrr.com   (REST API)
  2. IndieHackers   (SSR HTML scraping)
  3. Reddit         (JSON API, r/SideProject + r/SaaS)
  4. Product Hunt   (GraphQL API — 需要 PH_TOKEN 环境变量)

输出格式: 统计行 + 结构化数据 → 供 cron LLM 解读
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ============================================================
# CONFIG
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('RADAR_DATA_DIR', SCRIPT_DIR.parent / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / 'daily_signals_state.json'
LOOKBACK_HOURS = 48
MAX_ITEMS_PER_SOURCE = 50
MAX_PARALLEL = 11

TRUSTMRR_API_KEY = os.environ.get("TRUSTMRR_API_KEY", "")
PH_TOKEN = os.environ.get("PH_TOKEN", "")

# 中文翻译增强（GitHub / trustmrr / Product Hunt 等英文源 → 中文主标题）
# key 从环境变量 DEEPSEEK_API_KEY 或 ~/.hermes/.env 读取
ENHANCE_ZH = os.environ.get("ENHANCE_ZH", "1") == "1"
ZH_SOURCES = ["github", "trustmrr", "producthunt", "appstore-cn", "appstore-tw", "appstore-us", "appstore-jp", "appstore-kr"]  # 需要翻译的英文源

# Reddit OAuth（推荐，绕开 IP 封锁）— 在 https://www.reddit.com/prefs/apps 注册 script app 获取
# 未设置时自动 fallback 到 pullpush.io 镜像
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")
REDDIT_OAUTH_TOKEN_FILE = DATA_DIR / 'reddit_oauth_token.json'

# GitHub Trending（免 Key）— 支持多分类榜
GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
GITHUB_LANGUAGE = os.environ.get("GITHUB_LANGUAGE", "")  # 可选: 如 "python" 只抓该语言
GITHUB_VARIANTS = [
    # (source_key, url, 显示名)
    ("github", "https://github.com/trending?since=daily", "GitHub 总榜"),
    ("github-js", "https://github.com/trending/javascript?since=daily", "GitHub JS榜"),
    ("github-zh", "https://github.com/trending?since=daily&spoken_language_code=zh", "GitHub 中文榜"),
]

# ============================================================
# 国内数据源（免 Key）
# ============================================================
V2EX_LATEST_API = "https://www.v2ex.com/api/topics/latest.json"
V2EX_NODE_API = "https://www.v2ex.com/api/topics/show.json"
V2EX_NODES = ["create", "share", "programmer"]  # 分享创造 / 分享发现 / 程序员

KR36_FEED = "https://36kr.com/feed"              # 创投/科技媒体 RSS
SSPAI_FEED = "https://sspai.com/feed"            # 少数派：效率工具/数字生活 RSS
OSCHINA_FEED = "https://www.oschina.net/news/rss"  # 开源中国：开源项目动态 RSS

# 即刻圈子（通过 RSSHub 公共实例）
JIKA_TOPICS = [
    # (source_key, 圈子名, topic_id)
    ("jike-ai-explore", "AI探索站", "63579abb6724cc583b9bba9a"),
    ("jike-ai-discuss", "人工智能讨论组", "55fadac08cc2e30e00e2e42a"),
    ("jike-engineer", "工程师的日常", "577c5a122fa95b1100da059f"),
]
RSSHUB_BASE = os.environ.get("RSSHUB_BASE", "https://rsshub.umzzz.com")  # 可换其他公共实例

# App Store 新应用（官方 RSS，免 Key）— 关注新上架而非热榜
APPSTORE_REGIONS = [
    # (source_key, 区名, 地区码, 是否需翻译) — 各区英文名应用都很多，统一翻译
    ("appstore-cn", "App Store 中国", "cn", True),
    ("appstore-tw", "App Store 台湾", "tw", True),
    ("appstore-us", "App Store 美国", "us", True),
    ("appstore-jp", "App Store 日本", "jp", True),
    ("appstore-kr", "App Store 韩国", "kr", True),
]
APPSTORE_LIMIT = 20  # 每区取最新 20 条

UA_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# ============================================================
# STATE MANAGEMENT
# ============================================================

def load_state():
    path = Path(STATE_FILE)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 3,
        "last_run": None,
        "sources": {
            "trustmrr":  {"seen_ids": [], "last_seen_ts": None},
            "indiehackers": {"seen_ids": [], "last_seen_ts": None},
            "reddit":    {"seen_ids": [], "last_seen_ts": None},
            "producthunt": {"seen_ids": [], "last_seen_ts": None},
            "github":    {"seen_ids": [], "last_seen_ts": None},
            "github-js": {"seen_ids": [], "last_seen_ts": None},
            "github-zh": {"seen_ids": [], "last_seen_ts": None},
            "v2ex":      {"seen_ids": [], "last_seen_ts": None},
            "kr36":      {"seen_ids": [], "last_seen_ts": None},
            "sspai":     {"seen_ids": [], "last_seen_ts": None},
            "oschina":   {"seen_ids": [], "last_seen_ts": None},
            "jike-ai-explore": {"seen_ids": [], "last_seen_ts": None},
            "jike-ai-discuss": {"seen_ids": [], "last_seen_ts": None},
            "jike-engineer":   {"seen_ids": [], "last_seen_ts": None},
            "appstore-cn": {"seen_ids": [], "last_seen_ts": None},
            "appstore-tw": {"seen_ids": [], "last_seen_ts": None},
            "appstore-us": {"seen_ids": [], "last_seen_ts": None},
            "appstore-jp": {"seen_ids": [], "last_seen_ts": None},
            "appstore-kr": {"seen_ids": [], "last_seen_ts": None},
        }
    }

def save_state(state):
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def trim_seen(seen_ids, max_size=5000):
    if len(seen_ids) > max_size:
        return list(seen_ids[-max_size:])
    return seen_ids


# ============================================================
# HELPER: make_item
# ============================================================

def make_item(source, item_id, title, url, points, timestamp, description="",
              extra_tags=None, extra_fields=None):
    """统一 item 格式"""
    if isinstance(timestamp, (int, float)):
        ts = int(timestamp)
    elif isinstance(timestamp, str):
        try:
            ts = int(datetime.fromisoformat(timestamp).timestamp())
        except:
            ts = int(time.time())
    else:
        ts = int(time.time())

    obj = {
        "id": f"{source}:{item_id}",
        "source": source,
        "title": title.strip(),
        "url": url.strip(),
        "points": points,
        "timestamp": ts,
        "description": description.strip() if description else "",
        "extra_tags": extra_tags or [],
    }
    if extra_fields:
        obj.update(extra_fields)
    return obj


# ============================================================
# SOURCE 1: trustmrr.com (REST API)
# ============================================================

def fetch_trustmrr():
    items = []
    if not TRUSTMRR_API_KEY:
        print("[WARN] TRUSTMRR_API_KEY 未设置，跳过 trustmrr")
        return items

    headers = {"Authorization": f"Bearer {TRUSTMRR_API_KEY}"}
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)

    try:
        # 获取最新上线的 startup 列表
        url = "https://trustmrr.com/api/v1/startups"
        params = {"limit": 50, "sort": "listed-desc"}
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])

        for s in data:
            sid = s.get("slug", "")
            if not sid:
                continue
            name = s.get("name", "")
            description = s.get("description", "") or ""
            # 收入数据
            revenue = s.get("revenue", {})
            mrr = revenue.get("mrr", 0)
            growth = s.get("growth30d", 0)
            profit_margin = s.get("profitMarginLast30Days", 0)
            customers = s.get("customers", 0)
            tech_stack = s.get("techStack", [])
            category = s.get("category", "")
            country = s.get("country", "")

            # points = MRR relevance (MRR越高越值得关注)
            points = max(1, mrr // 100) if mrr else 1

            item = make_item(
                source="trustmrr",
                item_id=sid,
                title=f"{name} — "
                    + (f"${mrr:,}/mo MRR" if mrr else "Pre-revenue")
                    + (f", {growth:+.1f}% 30d" if growth else ""),
                url=f"https://trustmrr.com/startup/{sid}",
                points=points,
                timestamp=s.get("listedAt", int(time.time())),
                description=description[:500],
                extra_tags=[cat for cat in [category, country] if cat],
                extra_fields={
                    "mrr": mrr,
                    "growth_30d": growth,
                    "profit_margin": profit_margin,
                    "customers": customers,
                    "tech_stack": tech_stack,
                    "category": category,
                    "country": country,
                }
            )
            items.append(item)

    except Exception as e:
        print(f"[ERROR] trustmrr: {e}")

    return items


# ============================================================
# SOURCE 2: IndieHackers (Algolia Search API)
# ============================================================

ALGOLIA_APP_ID = "N86T1R3OWZ"
ALGOLIA_API_KEY = "5140dac5e87f47346abbda1a34ee70c3"
ALGOLIA_INDEX = "stories"

def fetch_indiehackers():
    items = []
    lookback_ts = int(time.time() * 1000) - (LOOKBACK_HOURS * 3600 * 1000)  # ms

    try:
        # Algolia 搜索 API — 获取 IndieHackers 故事
        url = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
        headers = {
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
            "Content-Type": "application/json",
        }

        all_hits = []
        page = 0
        while page < 5:  # 最多 5 页 (100+ 条)
            body = {
                "params": f"query=&hitsPerPage=30&page={page}&attributesToRetrieve=*"
            }
            r = requests.post(url, json=body, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            hits = data.get("hits", [])
            if not hits:
                break
            all_hits.extend(hits)
            page += 1

        # 按创建时间逆序
        all_hits.sort(key=lambda h: h.get("createdTimestamp", 0), reverse=True)

        for h in all_hits:
            ts_ms = h.get("createdTimestamp", 0)
            if ts_ms < lookback_ts:
                break  # 因为按时间排序了，后面的更旧

            title = h.get("title", "").strip()
            if not title:
                continue

            post_id = h.get("postId", "") or h.get("objectID", "")
            author = (h.get("authorNames") or ["?"])[0]
            company = (h.get("companyNames") or [""])[0]
            revenue_min = h.get("revenueMin", 0)
            tags = h.get("_tags", []) or h.get("tags", [])

            # 拼接标题增强信息
            extra_info = []
            if revenue_min:
                extra_info.append(f"${revenue_min:,}")
            if company:
                extra_info.append(company)
            title_md = title
            if extra_info:
                title_md = f"{title} — {' · '.join(extra_info)}"

            # 得分: 有收入故事优先
            points = max(1, revenue_min // 1000) if revenue_min else 1

            permalink = f"https://www.indiehackers.com/post/{post_id}"

            items.append(make_item(
                source="indiehackers",
                item_id=post_id,
                title=title_md,
                url=permalink,
                points=points,
                timestamp=ts_ms // 1000,
                description=f"Author: {author}" + (f" | Company: {company}" if company else ""),
                extra_tags=tags,
                extra_fields={
                    "author": author,
                    "company": company,
                    "revenue_min": revenue_min,
                    "tags": tags,
                }
            ))

    except Exception as e:
        print(f"[ERROR] indiehackers: {e}")

    return items


# ============================================================
# SOURCE 3: Reddit (JSON API)
# ============================================================

REDDIT_SUBREDDITS = [
    ("SideProject", 40),
    ("SaaS", 30),
    ("startups", 15),
    ("Entrepreneur", 15),
]

def _reddit_oauth_token():
    """获取 Reddit OAuth access token（带缓存，有效期 24h）"""
    token_file = Path(REDDIT_OAUTH_TOKEN_FILE)
    if token_file.exists():
        try:
            cached = json.loads(token_file.read_text())
            if cached.get("expires_at", 0) > int(time.time()) + 300:
                return cached.get("access_token")
        except (json.JSONDecodeError, OSError):
            pass

    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return None

    try:
        r = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "password",
                  "username": REDDIT_USERNAME,
                  "password": REDDIT_PASSWORD},
            auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
            headers={"User-Agent": "radar-dashboard:1.0 (open source project)"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("access_token")
        if token:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(json.dumps({
                "access_token": token,
                "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
            }))
        return token
    except Exception as e:
        print(f"[ERROR] reddit oauth token: {e}")
        return None


def _parse_reddit_post(p, subreddit, lookback_ts, seen_urls, items, source_prefix):
    """把单个 Reddit post 解析成 item（OAuth 和 JSON API 共用）"""
    pid = str(p.get("id", ""))
    title = (p.get("title") or "").strip()
    if not title or not pid:
        return
    ts = p.get("created_utc", 0)
    if ts < lookback_ts:
        return
    url = (p.get("url") or f"https://www.reddit.com{p.get('permalink', '')}")
    if url in seen_urls:
        return
    seen_urls.add(url)
    items.append(make_item(
        source=f"{source_prefix}/{subreddit}",
        item_id=pid,
        title=title,
        url=url,
        points=p.get("score", 0),
        timestamp=ts,
        description=(p.get("selftext") or "")[:500],
        extra_tags=[subreddit, p.get("domain", "")] if p.get("domain") else [subreddit],
        extra_fields={
            "comments": p.get("num_comments", 0),
            "subreddit": subreddit,
            "domain": p.get("domain", ""),
        }
    ))


def fetch_reddit_oauth():
    """用 Reddit OAuth API 抓取（绕开 IP 封锁）"""
    items = []
    token = _reddit_oauth_token()
    if not token:
        return items

    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)
    seen_urls = set()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "radar-dashboard:1.0 (open source project)",
    }

    for subreddit, limit in REDDIT_SUBREDDITS:
        try:
            url = f"https://oauth.reddit.com/r/{subreddit}/new?limit={limit}"
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            for post in r.json().get("data", {}).get("children", []):
                _parse_reddit_post(post.get("data", {}), subreddit, lookback_ts,
                                   seen_urls, items, "reddit")
        except Exception as e:
            print(f"[ERROR] reddit oauth/{subreddit}: {e}")

    return items


def fetch_reddit_pullpush():
    """用 pullpush.io 镜像抓取（fallback，数据可能滞后数小时）"""
    items = []
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)
    seen_urls = set()

    for subreddit, limit in REDDIT_SUBREDDITS:
        try:
            url = "https://api.pullpush.io/reddit/search/submission/"
            r = requests.get(url, params={
                "subreddit": subreddit,
                "before": int(time.time()),
                "size": limit,
            }, headers={"User-Agent": "radar-dashboard:1.0"}, timeout=15)
            r.raise_for_status()
            for p in r.json().get("data", []):
                _parse_reddit_post(p, subreddit, lookback_ts, seen_urls, items, "reddit")
        except Exception as e:
            print(f"[ERROR] reddit pullpush/{subreddit}: {e}")

    return items


def fetch_reddit():
    """Reddit 主入口：OAuth → pullpush → 原生 API（逐级降级）"""
    # 1. OAuth（配置了凭据时）
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        items = fetch_reddit_oauth()
        if items:
            print("[INFO] reddit: 使用 OAuth 通道")
            return items
        print("[WARN] reddit: OAuth 无数据，降级 pullpush")

    # 2. pullpush 镜像（免费可用）
    items = fetch_reddit_pullpush()
    if items:
        print("[INFO] reddit: 使用 pullpush 镜像")
        return items
    print("[WARN] reddit: pullpush 无数据，尝试原生 API")

    # 3. 原生 JSON API（IP 可能被封）
    items = []
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)
    seen_urls = set()
    for subreddit, limit in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "radar-dashboard:1.0 (open source project)"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            for post in data.get("data", {}).get("children", []):
                _parse_reddit_post(post.get("data", {}), subreddit, lookback_ts,
                                   seen_urls, items, "reddit")
        except Exception as e:
            print(f"[ERROR] reddit/r/{subreddit}: {e}")

    if items:
        print("[INFO] reddit: 使用原生 API")
    else:
        print("[WARN] reddit: 所有通道均失败")
    return items


# ============================================================
# SOURCE 4: Product Hunt (GraphQL API — 需要 PH_TOKEN)
# ============================================================

PH_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"

def fetch_producthunt():
    items = []
    if not PH_TOKEN:
        print("[INFO] PH_TOKEN 未设置，跳过 Product Hunt。")
        print("[INFO] 获取方式: https://api.producthunt.com/v2/oauth/applications → 创建应用 → 获取 Developer Token")
        return items

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    query = """
    {
      posts(postedAfter: "%s", order: RANKING, first: 50) {
        nodes {
          id
          name
          tagline
          description
          votesCount
          commentsCount
          url
          slug
          website
          featuredAt
          topics { nodes { name } }
        }
        totalCount
      }
    }
    """ % today

    try:
        r = requests.post(PH_GRAPHQL_URL, json={"query": query}, headers={
            "Authorization": f"Bearer {PH_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, timeout=15)
        r.raise_for_status()
        data = r.json()

        if "errors" in data:
            print(f"[DEBUG] PH errors: {json.dumps(data['errors'], indent=2)[:500]}", file=sys.stderr)

        posts = data.get("data", {}).get("posts", {}).get("nodes", [])

        for p in posts:
            pid = str(p.get("id", ""))
            name = p.get("name", "")
            tagline = p.get("tagline", "")
            description = p.get("description", "")
            points = p.get("votesCount", 0)
            comments = p.get("commentsCount", 0)
            url = p.get("url", "")
            topics = [t["name"] for t in p.get("topics", {}).get("nodes", [])]

            items.append(make_item(
                source="producthunt",
                item_id=pid,
                title=f"{name}: {tagline}" if tagline else name,
                url=url,
                points=points,
                timestamp=int(time.time()),
                description=(tagline + "\n" + description)[:500] if description else tagline,
                extra_tags=topics,
                extra_fields={
                    "comments": comments,
                    "topics": topics,
                    "website": p.get("website", ""),
                }
            ))

    except Exception as e:
        print(f"[ERROR] producthunt: {e}")

    return items


# ============================================================
# SOURCE 5: GitHub Trending (HTML scraping, 免 Key)
# ============================================================

def fetch_github_trending(source_key="github", url=None):
    """抓取 GitHub Trending 榜单（支持多分类）

    source_key: github / github-js / github-zh
    url: 指定抓取 URL，默认用 GITHUB_VARIANTS 配置
    """
    items = []
    try:
        from bs4 import BeautifulSoup
        if url is None:
            # 从 variants 里找对应的
            for key, u, _ in GITHUB_VARIANTS:
                if key == source_key:
                    url = u
                    break
            if url is None:
                url = GITHUB_TRENDING_URL
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for article in soup.select("article.Box-row"):
            try:
                h2 = article.select_one("h2 a")
                if not h2:
                    continue
                repo_path = h2.get("href", "").strip("/")
                repo_name = repo_path.split("/")[-1] if repo_path else ""
                owner = repo_path.split("/")[0] if "/" in repo_path else ""
                if not repo_path or not repo_name:
                    continue
                full_name = f"{owner}/{repo_name}"

                desc_el = article.select_one("p.col-9")
                desc = (desc_el.get_text(strip=True) if desc_el else "")[:500]

                lang_el = article.select_one('[itemprop="programmingLanguage"]')
                lang = lang_el.get_text(strip=True) if lang_el else ""

                stars_el = article.select_one('a[href$="/stargazers"]')
                stars = 0
                if stars_el:
                    try:
                        stars = int(stars_el.get_text(strip=True).replace(",", ""))
                    except ValueError:
                        stars = 0

                today_el = article.select_one(".d-inline-block.float-sm-right")
                stars_today = 0
                if today_el:
                    m = re.search(r"([\d,]+)\s+stars?\s+today", today_el.get_text())
                    if m:
                        try:
                            stars_today = int(m.group(1).replace(",", ""))
                        except ValueError:
                            stars_today = 0

                desc = re.sub(r"\s+", " ", desc).strip()

                item = make_item(
                    source=source_key,
                    item_id=f"{source_key}:{repo_path}",
                    title=f"{full_name}",
                    url=f"https://github.com/{repo_path}",
                    points=stars_today if stars_today > 0 else stars,
                    timestamp=int(time.time()),
                    description=desc,
                    extra_tags=[lang] if lang else [],
                    extra_fields={
                        "repo": full_name,
                        "language": lang,
                        "stars_total": stars,
                        "stars_today": stars_today,
                        "board": {k: lbl for k, _, lbl in GITHUB_VARIANTS}.get(source_key, source_key),
                    }
                )
                items.append(item)
            except Exception as e:
                print(f"[ERROR] github trending parse: {e}")

        items.sort(key=lambda i: (i.get("extra_fields", {}).get("stars_today", 0),
                                  i.get("extra_fields", {}).get("stars_total", 0)), reverse=True)
        items = items[:30]

    except Exception as e:
        print(f"[ERROR] github trending ({source_key}): {e}")

    return items


def fetch_github_all():
    """抓取所有 GitHub 分类榜，合并返回（source 区分）"""
    all_items = []
    for key, url, _ in GITHUB_VARIANTS:
        items = fetch_github_trending(key, url)
        all_items.extend(items)
        print(f"[INFO] github {key}: {len(items)} items")
    return all_items


# ============================================================
# SOURCE 6: V2EX (国内技术/创业社区, 免 Key)
# ============================================================

def fetch_v2ex():
    """抓取 V2EX 分享创造/分享发现/程序员 节点最新主题"""
    items = []
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)
    seen_ids = set()

    for node in V2EX_NODES:
        try:
            r = requests.get(V2EX_NODE_API, params={"node_name": node},
                             headers={"User-Agent": UA_BROWSER}, timeout=10)
            r.raise_for_status()
            for t in r.json():
                tid = str(t.get("id", ""))
                if not tid or tid in seen_ids:
                    continue
                ts = t.get("created", 0)
                if ts < lookback_ts:
                    continue
                seen_ids.add(tid)
                title = (t.get("title") or "").strip()
                content = (t.get("content") or "")[:500]
                node_name = (t.get("node") or {}).get("title", node)
                items.append(make_item(
                    source="v2ex",
                    item_id=f"{node}:{tid}",
                    title=f"[{node_name}] {title}",
                    url=f"https://www.v2ex.com/t/{tid}",
                    points=t.get("replies", 0),
                    timestamp=ts,
                    description=content,
                    extra_tags=[node, node_name],
                    extra_fields={
                        "node": node_name,
                        "replies": t.get("replies", 0),
                    }
                ))
        except Exception as e:
            print(f"[ERROR] v2ex/{node}: {e}")

    return items


# ============================================================
# SOURCE 7-9: 国内 RSS 源 (36氪 / 少数派 / 开源中国)
# ============================================================

def _parse_rss_feed(url, source, tag_hint, max_items=30):
    """通用 RSS 解析：返回 items 列表"""
    import xml.etree.ElementTree as ET
    items = []
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)

    try:
        r = requests.get(url, headers={"User-Agent": UA_BROWSER}, timeout=12)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        # 兼容 RSS 2.0 (<channel><item>) 和 Atom (<feed><entry>)
        entries = []
        channel = root.find("channel")
        if channel is not None:
            entries = channel.findall("item")
        else:
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")

        for entry in entries[:max_items]:
            # 提取 title / link / pubDate
            title_el = entry.find("title")
            title = (title_el.text or "").strip() if title_el is not None else ""
            title = title.replace("<![CDATA[", "").replace("]]>", "").strip()
            if not title:
                continue

            link_el = entry.find("link")
            link = (link_el.text or "").strip() if link_el is not None else ""
            if not link:
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.get("href", "")

            # 时间解析
            ts = int(time.time())
            date_el = entry.find("pubDate") or entry.find("{http://www.w3.org/2005/Atom}updated")
            if date_el is not None and date_el.text:
                try:
                    from email.utils import parsedate_to_datetime
                    ts = int(parsedate_to_datetime(date_el.text).timestamp())
                except Exception:
                    try:
                        ts = int(datetime.fromisoformat(date_el.text.strip()).timestamp())
                    except Exception:
                        pass

            if ts < lookback_ts:
                continue

            desc_el = entry.find("description") or entry.find("summary")
            desc = ""
            if desc_el is not None and desc_el.text:
                desc = re.sub(r"<[^>]+>", "", desc_el.text)[:400]

            # id: 优先 guid，否则用 link hash
            guid_el = entry.find("guid") or entry.find("id")
            item_id = ""
            if guid_el is not None and guid_el.text:
                item_id = guid_el.text.strip()[:100]
            elif link:
                item_id = f"link:{hash(link) & 0xffffffff}"

            if not item_id:
                continue

            items.append(make_item(
                source=source,
                item_id=item_id,
                title=title,
                url=link,
                points=0,
                timestamp=ts,
                description=desc,
                extra_tags=[tag_hint],
                extra_fields={}
            ))
    except Exception as e:
        print(f"[ERROR] rss {source}: {e}")

    return items


def fetch_kr36():
    """36氪 — 创投/科技动态"""
    return _parse_rss_feed(KR36_FEED, "kr36", "创投")


def fetch_sspai():
    """少数派 — 效率工具/数字生活"""
    return _parse_rss_feed(SSPAI_FEED, "sspai", "工具")


def fetch_oschina():
    """开源中国 — 开源项目动态"""
    return _parse_rss_feed(OSCHINA_FEED, "oschina", "开源")


# ============================================================
# SOURCE 10: 即刻圈子 (RSSHub 公共实例)
# ============================================================

def fetch_jike():
    """抓取即刻多个圈子（AI探索站/人工智能讨论组/工程师的日常）"""
    import xml.etree.ElementTree as ET
    items = []
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)

    for source_key, topic_name, topic_id in JIKA_TOPICS:
        try:
            url = f"{RSSHUB_BASE}/jike/topic/{topic_id}"
            r = requests.get(url, headers={"User-Agent": UA_BROWSER}, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            channel = root.find("channel")
            if channel is None:
                continue

            for entry in channel.findall("item")[:20]:
                title_el = entry.find("title")
                title = (title_el.text or "").strip() if title_el is not None else ""
                if not title:
                    continue

                link_el = entry.find("link")
                link = (link_el.text or "").strip() if link_el is not None else ""

                # 时间解析（RSSHub 输出 RFC822 格式 pubDate）
                ts = int(time.time())
                date_el = entry.find("pubDate")
                if date_el is not None and date_el.text:
                    try:
                        from email.utils import parsedate_to_datetime
                        ts = int(parsedate_to_datetime(date_el.text).timestamp())
                    except Exception:
                        pass
                if ts < lookback_ts:
                    continue

                desc_el = entry.find("description")
                desc = ""
                if desc_el is not None and desc_el.text:
                    desc = re.sub(r"<[^>]+>", "", desc_el.text)[:400]

                # id: link 里的 originalPosts ID 或 hash
                pid = ""
                if link:
                    m = re.search(r"originalPosts/([a-zA-Z0-9]+)", link)
                    pid = m.group(1) if m else f"link:{hash(link) & 0xffffffff}"
                if not pid:
                    continue

                items.append(make_item(
                    source=source_key,
                    item_id=f"{source_key}:{pid}",
                    title=title,
                    url=link,
                    points=0,
                    timestamp=ts,
                    description=desc,
                    extra_tags=[topic_name],
                    extra_fields={
                        "topic": topic_name,
                    }
                ))
        except Exception as e:
            print(f"[ERROR] jike/{topic_name}: {e}")

    return items


# ============================================================
# SOURCE 11: App Store 新应用 (官方 RSS, 免 Key)
# ============================================================

def fetch_appstore():
    """抓取 App Store 各区新上架应用（关注新榜而非热榜）"""
    items = []
    lookback_ts = int(time.time()) - (LOOKBACK_HOURS * 3600)

    for source_key, region_name, region_code, need_translate in APPSTORE_REGIONS:
        try:
            url = f"https://itunes.apple.com/{region_code}/rss/newapplications/limit={APPSTORE_LIMIT}/json"
            r = requests.get(url, headers={"User-Agent": UA_BROWSER}, timeout=15)
            r.raise_for_status()
            entries = r.json().get("feed", {}).get("entry", [])
            entries = entries[:APPSTORE_LIMIT]  # 只保留最新 N 条

            for e in entries:
                name = (e.get("im:name", {}) or {}).get("label", "").strip()
                if not name:
                    continue
                app_id = (e.get("id", {}) or {}).get("attributes", {}).get("im:id", "")
                if not app_id:
                    continue

                artist = (e.get("im:artist", {}) or {}).get("label", "")
                category = (e.get("category", {}) or {}).get("attributes", {}).get("label", "")
                price = (e.get("im:price", {}) or {}).get("label", "")
                link = (e.get("link", {}) or {}).get("attributes", {}).get("href", "")
                icon = ""
                images = e.get("im:image", [])
                if images:
                    icon = images[-1].get("label", "") if isinstance(images[-1], dict) else ""

                # 上架时间
                ts = int(time.time())
                release = (e.get("im:releaseDate", {}) or {}).get("label", "")
                if release:
                    try:
                        from datetime import datetime
                        ts = int(datetime.fromisoformat(release.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        pass

                desc_parts = []
                if category:
                    desc_parts.append(f"分类: {category}")
                if artist:
                    desc_parts.append(f"开发者: {artist}")
                if price:
                    desc_parts.append(f"价格: {price}")

                items.append(make_item(
                    source=source_key,
                    item_id=f"{source_key}:{app_id}",
                    title=name,
                    url=link or f"https://apps.apple.com/{region_code}/app/id{app_id}",
                    points=0,
                    timestamp=ts,
                    description=" | ".join(desc_parts),
                    extra_tags=[region_name, category] if category else [region_name],
                    extra_fields={
                        "region": region_name,
                        "category": category,
                        "artist": artist,
                        "price": price,
                        "icon": icon,
                        "need_translate": need_translate,
                    }
                ))
            print(f"[INFO] appstore {source_key}: {len(entries)} items")
        except Exception as e:
            print(f"[ERROR] appstore/{source_key}: {e}")

    return items


# ============================================================
# 中文翻译增强（英文源 → 中文主标题，供 Dashboard 显示）
# ============================================================

def _get_deepseek_key():
    """从环境变量或本地 .env 读取 DeepSeek API key

    读取优先级：
    1. 环境变量 DEEPSEEK_API_KEY
    2. 脚本目录 .env（项目自带）
    3. ~/.hermes/.env（Hermes 用户已配置的 Key，复用无需重复配置）
    4. 用户主目录 .env
    """
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    try:
        # 优先读脚本目录的 .env，其次 Hermes 配置，最后用户主目录 .env
        for env_file in [SCRIPT_DIR / '.env', Path.home() / '.hermes' / '.env', Path.home() / '.env']:
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("DEEPSEEK_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def enhance_chinese(all_results):
    """对英文源（GitHub/trustmrr/PH）批量翻译，写回 title_cn / name_cn / desc_cn

    返回：新增了中文字段的 items 数量
    """
    if not ENHANCE_ZH:
        return 0
    key = _get_deepseek_key()
    if not key:
        print("[WARN] DEEPSEEK_API_KEY 未配置，跳过中文翻译增强")
        return 0

    total = 0
    for source in ZH_SOURCES:
        if source.startswith("appstore"):
            # appstore 的 items 都在 all_results["appstore"] 下，按 region 过滤（region 在 item 顶层）
            all_items = all_results.get("appstore", [])
            need = source.split("-", 1)[1]  # us/jp/kr
            region_map = {"cn": "中国", "tw": "台湾", "us": "美国", "jp": "日本", "kr": "韩国"}
            region_cn = region_map.get(need, "")
            items = [it for it in all_items if region_cn and region_cn in it.get("region", "")]
        else:
            items = all_results.get(source, [])
        if not items:
            continue
        try:
            # 组装翻译输入
            batch = []
            for it in items:
                desc = (it.get("description") or "")[:200]
                title = it.get("title", "")
                if source == "github":
                    # GitHub: 仓库名 + 描述 → 中文项目名 + 中文一句话说明
                    batch.append({"id": it.get("id", ""), "title": title, "desc": desc,
                                  "type": "github_repo"})
                elif source.startswith("appstore"):
                    # App Store: 应用名 + 分类/开发者 → 中文应用名 + 中文说明
                    batch.append({"id": it.get("id", ""), "title": title, "desc": desc,
                                  "type": "app"})
                else:
                    batch.append({"id": it.get("id", ""), "title": title, "desc": desc,
                                  "type": "product"})

            prompt = f"""你是出海情报雷达的中文翻译助手。把以下 {len(batch)} 条英文条目翻译成简洁的中文。
规则：
- github_repo 类型：给出「项目中文名」（5-15字，概括项目做什么）+ 「一句话中文说明」（20-40字，说明这个项目主要功能/用途）
- app 类型：给出「中文应用名」（翻译应用名称，保留品牌名；如果是拼音/专有名词可保留；如果名称本身已是中文/繁体中文则保持原样）+ 「一句话中文说明」（20-40字，根据分类和描述说明这个应用是做什么的，如果信息不足就写『新上架应用』）
- product 类型：给出「中文标题」（10-30字，翻译标题即可，保留品牌名）+ 「一句话中文说明」（15-40字，说明它解决什么问题，可选）
- 保持产品/项目名称原文（如 OpenAI、Bolt.new 不翻译）
- 只返回 JSON，不要任何其他文字

输入：
{json.dumps(batch, ensure_ascii=False)}

输出 JSON 格式：
{{"<id>": {{"name_cn": "...", "title_cn": "...", "desc_cn": "..."}}}}
"""

            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
                timeout=60,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]

            # 提取 JSON（模型可能带 ```json 包裹）
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            translations = json.loads(content)

            # 写回 items
            for it in items:
                tr = translations.get(it.get("id", ""))
                if not tr:
                    continue
                if tr.get("name_cn"):
                    it["name_cn"] = tr["name_cn"]
                if tr.get("title_cn"):
                    it["title_cn"] = tr["title_cn"]
                if tr.get("desc_cn"):
                    it["desc_cn"] = tr["desc_cn"]
                total += 1
            print(f"[INFO] zh-enhance {source}: {len(translations)} items translated")
        except Exception as e:
            print(f"[ERROR] zh-enhance {source}: {e}")

    return total


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def slug_from_url(url):
    """从 URL 提取 slug/ID"""
    m = re.search(r'/([^/]+?)/?$', url)
    return m.group(1) if m else None

def deep_find(obj, keys):
    """递归在嵌套 dict 中查找 keys 列表中的任一 key"""
    if isinstance(obj, dict):
        for key in keys:
            if key in obj:
                val = obj[key]
                if isinstance(val, list):
                    return val
        for v in obj.values():
            result = deep_find(v, keys)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = deep_find(item, keys)
            if result:
                return result
    return None

def format_time(ts):
    dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%m-%d %H:%M")


# ============================================================
# MAIN
# ============================================================

def main():
    state = load_state()
    sources_state = state.get("sources", {})

    start_time = time.time()

    # === 并行采集 ===
    collectors = {
        "trustmrr": fetch_trustmrr,
        "indiehackers": fetch_indiehackers,
        "reddit": fetch_reddit,
        "producthunt": fetch_producthunt,
        "github": fetch_github_all,
        "v2ex": fetch_v2ex,
        "kr36": fetch_kr36,
        "sspai": fetch_sspai,
        "oschina": fetch_oschina,
        "jike": fetch_jike,
        "appstore": fetch_appstore,
    }

    all_results = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        futures = {executor.submit(fn): name for name, fn in collectors.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                all_results[name] = future.result()
            except Exception as e:
                print(f"[ERROR] {name} 采集异常: {e}")
                all_results[name] = []

    elapsed = time.time() - start_time

    # === 中文翻译增强（英文源 → 中文主标题）===
    try:
        enhanced = enhance_chinese(all_results)
        if enhanced:
            print(f"[INFO] zh-enhance: {enhanced} items enhanced")
    except Exception as e:
        print(f"[ERROR] enhance_chinese: {e}")

    # === 保存原始信号（含 url，供 Dashboard 信号流展示）===
    # 按 item 实际 source 分组（如 github / github-js / github-zh 分开）
    try:
        raw_dir = DATA_DIR / 'raw_signals'
        raw_dir.mkdir(parents=True, exist_ok=True)
        today_str = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        raw_data = {
            "date": today_str,
            "collected_at": datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
            "sources": {},
        }
        # 展开所有 items，按 item["source"] 分组
        flat_items = []
        for items in all_results.values():
            flat_items.extend(items)
        by_real_source = {}
        for i in flat_items:
            src = i.get("source", "unknown")
            by_real_source.setdefault(src, []).append(i)
        for source_name, items in by_real_source.items():
            raw_data["sources"][source_name] = [
                {
                    "id": i.get("id", ""),
                    "title": i.get("title", ""),
                    "title_cn": i.get("title_cn", ""),
                    "name_cn": i.get("name_cn", ""),
                    "desc_cn": i.get("desc_cn", ""),
                    "url": i.get("url", ""),
                    "points": i.get("points", 0),
                    "timestamp": i.get("timestamp", 0),
                    "description": i.get("description", ""),
                    "extra_tags": i.get("extra_tags", []),
                    # 各源动态字段（make_item 平铺到顶层）
                    "category": i.get("category", ""),
                    "artist": i.get("artist", ""),
                    "price": i.get("price", ""),
                    "icon": i.get("icon", ""),
                    "region": i.get("region", ""),
                    "board": i.get("board", ""),
                    "language": i.get("language", ""),
                    "stars_total": i.get("stars_total", 0),
                    "stars_today": i.get("stars_today", 0),
                    "repo": i.get("repo", ""),
                    "node": i.get("node", ""),
                    "topic": i.get("topic", ""),
                }
                for i in items
            ]
        raw_path = raw_dir / f"{today_str}.json"
        raw_path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2))
        print(f"[INFO] raw signals saved: {raw_path}")
    except Exception as e:
        print(f"[ERROR] save raw signals: {e}")

    # === 增量对比（按 item 实际 source 分组）===
    grand_total_new = 0
    per_source = {}

    flat_items = []
    for items in all_results.values():
        flat_items.extend(items)
    by_real_source = {}
    for i in flat_items:
        src = i.get("source", "unknown")
        by_real_source.setdefault(src, []).append(i)

    for source_name, items in by_real_source.items():
        seen_ids = set(sources_state.get(source_name, {}).get("seen_ids", []))
        new_items = [i for i in items if i["id"] not in seen_ids]

        # 更新已见
        all_ids_in_batch = [i["id"] for i in items]
        seen_ids.update(all_ids_in_batch)
        sources_state[source_name] = {
            "seen_ids": trim_seen(list(seen_ids)),
            "last_seen_ts": int(time.time()),
        }

        per_source[source_name] = new_items
        grand_total_new += len(new_items)

    # 保存状态
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["sources"] = sources_state
    save_state(state)

    # === 输出统计行 ===
    print(f"TOTAL_NEW={grand_total_new}")
    for name, items in per_source.items():
        print(f"{name.upper()}_NEW={len(items)}")
    print(f"COLLECTION_TIME={elapsed:.1f}s")
    print(f"COLLECTED_AT={datetime.now(tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
    print("---")

    if grand_total_new == 0:
        print("NO_NEW_ITEMS")
        # 打印各来源统计
        for name, items in all_results.items():
            total_in_batch = len(items)
            print(f"  {name}: {total_in_batch} total, 0 new")
        return

    # === 输出结构化数据 ===
    print(f"📡 独立开发者信号雷达 — {datetime.now(tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}")
    print()
    print(f"采集耗时: {elapsed:.1f}s | 新增信号: {grand_total_new}")
    source_labels = {
        "trustmrr": "trustmrr", "indiehackers": "IndieHackers", "reddit": "Reddit",
        "producthunt": "Product Hunt", "github": "GitHub 总榜", "github-js": "GitHub JS榜",
        "github-zh": "GitHub 中文榜", "v2ex": "V2EX", "kr36": "36氪", "sspai": "少数派",
        "oschina": "开源中国", "jike-ai-explore": "即刻·AI探索站",
        "jike-ai-discuss": "即刻·AI讨论", "jike-engineer": "即刻·工程师",
        "appstore-cn": "App Store 中国", "appstore-tw": "App Store 台湾",
        "appstore-us": "App Store 美国", "appstore-jp": "App Store 日本",
        "appstore-kr": "App Store 韩国",
    }
    parts = []
    for name, items in per_source.items():
        if items:
            parts.append(f"{source_labels.get(name, name)} ({len(items)}新)")
    print(f"来源: {' | '.join(parts)}")
    print()
    print("=" * 60)

    # === 按来源输出数据 ===
    for source_name, items in per_source.items():
        if not items:
            continue

        # 按 points 排序
        sorted_items = sorted(items, key=lambda x: (x.get("mrr", 0) if source_name == "trustmrr" else x["points"]), reverse=True)

        source_label = {
            "trustmrr": "💰 trustmrr — 收入/收购信号",
            "indiehackers": "🏗️ IndieHackers — 故事/案例",
            "reddit": "💬 Reddit — 新产品讨论",
            "producthunt": "🚀 Product Hunt — 今日新品",
            "github": "🐙 GitHub 总榜",
            "github-js": "🐙 GitHub JS榜",
            "github-zh": "🐙 GitHub 中文榜",
            "v2ex": "🟤 V2EX — 国内社区",
            "kr36": "🔴 36氪 — 创投动态",
            "sspai": "🟡 少数派 — 效率工具",
            "oschina": "🟠 开源中国 — 开源动态",
            "jike-ai-explore": "⚡ 即刻·AI探索站",
            "jike-ai-discuss": "⚡ 即刻·人工智能讨论组",
            "jike-engineer": "⚡ 即刻·工程师的日常",
            "appstore-cn": "📱 App Store 中国·新应用",
            "appstore-tw": "📱 App Store 台湾·新应用",
            "appstore-us": "📱 App Store 美国·新应用",
            "appstore-jp": "📱 App Store 日本·新应用",
            "appstore-kr": "📱 App Store 韩国·新应用",
        }.get(source_name, source_name)

        print(f"\n## {source_label} ({len(items)} 条新)")
        print()

        for i, item in enumerate(sorted_items[:15], 1):
            title = item["title"]
            url = item["url"]
            ts = format_time(item["timestamp"])
            points_display = item["points"]

            # 根据不同来源显示不同关键指标
            extra = ""
            if source_name == "trustmrr" and "mrr" in item:
                mrr = item.get("mrr", 0)
                growth = item.get("growth_30d", 0)
                mrr_display = int(round(mrr)) if mrr else 0
                extra = f" | MRR: ${mrr_display:,}" if mrr_display else ""
                if growth:
                    extra += f" | 增长: {growth:+.1f}%"
            elif source_name == "reddit":
                comments = item.get("extra_fields", {}).get("comments", 0)
                sub = item.get("extra_tags", [""])[0]
                extra = f" | r/{sub} | 💬 {comments}"

            print(f"  {i}. [{points_display}▲{extra}]")
            print(f"     {title[:120]}")
            print(f"     {ts} | {url}")
            print()

    # === 趋势关键词 ===
    all_titles = []
    all_tags = []
    for items in per_source.values():
        for item in items:
            all_titles.append(item["title"])
            all_tags.extend(item.get("extra_tags", []))

    words = []
    for t in all_titles:
        words.extend(re.findall(r'\b[A-Za-z]{3,}\b', t.lower()))

    # 过滤常见无意义词
    stop_words = {"the", "this", "that", "with", "from", "have", "been",
                  "what", "when", "where", "which", "their", "they",
                  "your", "about", "into", "over", "than", "then",
                  "also", "just", "more", "some", "very", "will",
                  "would", "could", "should", "does", "done", "using"}

    print("📊 今日趋势关键词")
    print()
    common = Counter(w for w in words if w not in stop_words).most_common(10)
    for word, count in common:
        if count >= 2:
            print(f"  #{word} ({count})")
    print()
    print("---")
    print(f"✅ 数据来源: trustmrr.com + IndieHackers + Reddit + Product Hunt | "
          f"采集耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
