"""
International Fastest News Extraction AI Agent
LLM-driven | Category + Breaking Intelligence
"""

# =========================
# IMPORTS
# =========================
import feedparser
import requests
import trafilatura
import hashlib
import calendar
import os
import time
from datetime import datetime
from threading import Event
import threading
import json
from dotenv import load_dotenv
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
from app.db.database import SessionLocal
from app.db.models import NewsArticle
from collector.media_extractor import extract_media
from collector.youtube_fallback import search_youtube_video


# =========================
# INIT
# =========================
load_dotenv()
client = OpenAI()

# =========================
# CONFIG
# =========================

IMPACT_DOMAINS = {
    "stock_market",
    "currency_forex",
    "commodities",
    "supply_chain",
    "travel_aviation",
    "immigration_policy",
    "national_security",
    "diplomacy",
    "energy",
    "sports_industry",
    "public_health",
    "technology",
    "none"
}

ALLOWED_CATEGORIES = {"immigration", "trade", "tariff", "sports"}

MIN_CONTENT_WORDS = 40
GLOBAL_TICK = 5
MAX_ARTICLE_AGE_SECONDS = 2 * 60 * 60
HEADERS = {"User-Agent": "InternationalFastNewsBot/1.0"}

# =========================
# NEWS SOURCES
# =========================
NEWS_SOURCES = {
    "The Guardian": {"url": "https://www.theguardian.com/world/rss", "interval": 30},
    "Al Jazeera": {"url": "https://www.aljazeera.com/xml/rss/all.xml", "interval": 30},
    "UN News": {"url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "interval": 30},
    "BBC World": {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "interval": 30},
    "DW World": {"url": "https://rss.dw.com/rdf/rss-en-world", "interval": 30},
    "France24": {"url": "https://www.france24.com/en/rss", "interval": 30},
}

# =========================
# RUNTIME STATE
# =========================
stop_event = Event()
seen_articles = set()
last_polled = {s: 0 for s in NEWS_SOURCES}
collector_thread = None


# =========================
# LLM — MERGED ANALYZER
# =========================
def analyze_article_llm(title):
    prompt = f"""
You are a senior international breaking-news intelligence editor working in a real-time newsroom.

Your job is to make FAST, PRECISE, FIRST-ORDER judgments based ONLY on the headline.

You must determine:

1) PRIMARY CATEGORY (choose exactly ONE):
- immigration -> (migration, refugees, asylum, visas, borders, deportation, diaspora,migrant, deport, detention, citizenship, [policy, law, court, government,permit- all for confirmation])
- trade -> (global trade, commerce, supply chains, exports/imports, economic relations,deals,industry, market,business,retail, economy,[gdp,growth,inflation,investment-all for confirmation])
- tariff -> (customs duties, trade taxes, sanctions-related tariffs, levies,sanction,duty, duties, embargo,trade restriction,[imposed, announced,retailation -all for confirmation])
- sports -> (matches, players, teams, tournaments,afcon,world cup,fifa, vs, league, goal)

2) PRIMARY IMMEDIATE IMPACT
This means: what is affected FIRST in the real world ,not long-term or speculative effects..

Choose exactly ONE:
- stock_market → equities, investor sentiment, listed companies
- currency_forex → exchange rates, FX markets
- commodities → oil, gas, metals, agriculture
- supply_chain → logistics, manufacturing, trade flows
- travel_aviation → airlines, airports, tourism, transport disruption
- immigration_policy → visas, asylum systems, border enforcement
- national_security → terrorism, war, attacks, military, internal security
- diplomacy → international relations, negotiations, state-to-state actions
- energy → power, fuel supply, energy infrastructure
- sports_industry → leagues, tournaments, clubs, athletes
- public_health → disease outbreaks, health emergencies
- technology → tech platforms, cyber incidents, regulation
- none → only if no clear immediate impact

3) BREAKING NEWS FLAG
Set breaking = true ONLY if:
- The event is newly occurring or newly announced
- It is time-sensitive and urgent
- It would trigger immediate newsroom alerts
- It is NOT analysis, opinion, background, or rhetoric

Set breaking = false IF:
- Analysis, explainer, opinion, background, feature
- It explains past events
- Political rhetoric or repeated statements
- It describes ongoing conditions without a trigger
- Human-interest or descriptive framing

IMPORTANT RULES:
- Be conservative, not sensational
- Prefer concrete real-world impact over speculation
- Violence, explosions, attacks → national_security
- Trade policy, sanctions, tariffs → stock_market or supply_chain
- Sports matches or tournament results → sports_industry
- If unsure, choose the safest realistic option

Headline:
\"\"\"{title}\"\"\"

Respond ONLY in strict JSON:
{{
  "category": "<value>",
  "impact": "<value>",
  "breaking": true or false
}}
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=60,
        )

        data = json.loads(r.choices[0].message.content)

        category = data.get("category")
        impact = data.get("impact")
        breaking = bool(data.get("breaking", False))

        if category not in ALLOWED_CATEGORIES:
            category = None
        if impact not in IMPACT_DOMAINS:
            impact = "none"

        return category, impact, breaking

    except Exception as e:
        print(f"[LLM ERROR] {type(e).__name__}: {str(e)[:150]} -> using keyword fallback")
        return classify_by_keywords(title)


# Used only when the LLM call fails (bad key, no credits, network)
FALLBACK_KEYWORDS = {
    "immigration": ["immigra", "migrant", "migration", "asylum", "refugee", "deport", "visa",
                    "border", "ice agent", "citizenship", "residency"],
    "tariff": ["tariff", "duties", "customs duty", "import tax", "levy"],
    "trade": ["trade", "export", "import", "supply chain", "commerce", "wto", "sanction",
              "economy", "gdp", "inflation", "market", "oil", "diesel"],
    "sports": ["football", "cricket", "olympic", "nations league", "fifa", "uefa", "tennis",
               "match", "tournament", "asian games", "boxer", "mlb", "nba", "world cup"],
}
BREAKING_KEYWORDS = ["breaking", "live:", "killed", "dead", "attack", "explosion", "urgent"]


def classify_by_keywords(title):
    t = title.lower()
    for category, words in FALLBACK_KEYWORDS.items():
        if any(w in t for w in words):
            return category, "none", any(w in t for w in BREAKING_KEYWORDS)
    return None, "none", False


# =========================
# UTILITIES
# =========================
def article_hash(text):
    return hashlib.sha256(text.lower().encode()).hexdigest()


def is_duplicate(url, title):
    h1, h2 = article_hash(url), article_hash(title)
    if h1 in seen_articles or h2 in seen_articles:
        return True
    seen_articles.update([h1, h2])
    return False


# =========================
# URL RESOLUTION
# =========================
def resolve_url(url):
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=10)
        if r.status_code < 400 and r.url:
            return r.url
    except:
        pass

    try:
        r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return r.url
    except:
        return url


# =========================
# LOAD EXISTING HASHES
# =========================
def load_existing_hashes_from_db():
    """
    Load previously ingested article URLs and titles from DB
    into memory to prevent duplicates after restart.
    """
    db = SessionLocal()
    try:
        rows = db.query(NewsArticle.url, NewsArticle.title).all()
        for url, title in rows:
            if url:
                seen_articles.add(article_hash(url))
            if title:
                seen_articles.add(article_hash(title))
        print(f"[INIT] Loaded {len(seen_articles)} article hashes from DB")
    except Exception as e:
        print("[INIT ERROR] Failed loading hashes from DB:", e)
    finally:
        db.close()

# =========================
# CONTENT EXTRACTION
# =========================
def extract_content(url):
    if stop_event.is_set():
        return None 
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        
         # 1️⃣ Primary extractor
        text = trafilatura.extract(
            r.text,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        # 2️⃣ Fallback: try URL fetch
        if not text:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, favor_recall=True)

        # 3️⃣ Final validation
        if not text:
            print(f"[EXTRACT FAIL] No text | {url}")
            return None

        words = text.split()
        if len(words) < 30:  # LOWER threshold
            print(f"[EXTRACT SHORT] {len(words)} words | {url}")
            return None

        return text.strip()

    except Exception as e:
        print(f"[EXTRACT ERROR] {url} | {e}")
        return None


# =========================
# RSS FETCH
# =========================
def fetch_rss(source_name, url):
    feed = feedparser.parse(url)
    articles = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()

        if not title or not link:
            continue

        published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        # feedparser structs are UTC; mktime would treat them as local time (IST = +5.5h skew)
        published_ts = calendar.timegm(published_struct) if published_struct else None

        articles.append({
            "source": source_name,
            "title": title,
            "url": link,
            "_published_ts": published_ts,
        })

    return articles

def fetch_and_process_source(src):
    if stop_event.is_set(): return

    cfg = NEWS_SOURCES[src]
    now = time.time()
    if now - last_polled[src] < cfg["interval"]:
        return
    
    last_polled[src] = now
    print(f"[FETCH] {src}")

    articles = fetch_rss(src, cfg["url"])
    for art in articles:
        if stop_event.is_set():
            return  
        process_article(art)

def save_article(row):
    db = SessionLocal()
    try:
        article = NewsArticle(
            fetched_at=row["fetched_at"],
            source=row["source"],
            category=row["category"],
            impact=row["impact"],
            title=row["title"],
            url=row["url"],
            breaking_flag=bool(row["breaking_flag"]),
            content=row["content"],
            image_url=row["image_url"],
            video_url=row["video_url"],
            video_platform=row["video_platform"]
        )
        db.add(article)
        db.commit()
    except Exception as e:
        db.rollback()
        print("[DB ERROR]", e)
    finally:
        db.close()

# =========================
# ARTICLE PIPELINE
# ========================= 
def process_article(a):
    if stop_event.is_set():
        return 
    published_ts = a.get("_published_ts")
    if published_ts and time.time() - published_ts > MAX_ARTICLE_AGE_SECONDS:
        print(f"[SKIP] Old article | {a['title'][:60]}")
        return

    title = a.get("title", "").strip()
    if not title:
        return

    category, impact, breaking = analyze_article_llm(title)
    if not category:
        print(f"[SKIP] Not in tracked categories | {a['title'][:60]}")
        return

    time.sleep(0.4)

    url = resolve_url(a["url"])
    if is_duplicate(url, title):
        print(f"[SKIP] Duplicate | {title[:60]}")
        return
    
    image_url, video_url, video_platform = extract_media(url)
    
    # ---- YOUTUBE FALLBACK ----
    
    yt_video = search_youtube_video(title, a["source"])
    video_url = yt_video
    video_platform = "youtube" if yt_video else None
    print(f"[YOUTUBE FALLBACK] {title[:60]}")

    content = extract_content(url)
    if content:
        content = content[:8000]

    if not content:
        print(f"[SKIP] No content | {title[:60]}")
        return

    row = {
        "fetched_at": datetime.now().isoformat(),
        "source": a["source"],
        "category": category,
        "impact": impact,
        "title": title,
        "url": url,
        "breaking_flag": int(breaking),
        "content": content,
        "image_url": image_url,
        "video_url": video_url,
        "video_platform": video_platform,
    }

    save_article(row)

    print(f"[OK] {a['source']} | {category.upper()} | {impact.upper()} | {'BREAKING' if breaking else 'NORMAL'}")


# =========================
# THREAD CONTROL
# =========================
def start_collector():
    global collector_thread
    if collector_thread and collector_thread.is_alive():
        print("[INFO] Collector already running")
        return

    stop_event.clear()
    collector_thread = threading.Thread(target=run, daemon=True)
    collector_thread.start()
    print("[START] Collector thread launched")


def stop_collector():
    """
    Stop ingestion thread gracefully.
    """
    if stop_event.is_set():
        print("[INFO] Collector already stopped")
        return

    stop_event.set()
    print("[STOP] Collector stop signal sent")


# =========================
# MAIN LOOP
# =========================
def run():
    print("[START] International Fast News Agent running...")
    load_existing_hashes_from_db()

    while not stop_event.is_set():

        # ---- STOP check before batch ----
        if stop_event.is_set():
            print("[STOP] Collector interrupted before fetch cycle")
            break

        # Thread pool processes multiple sources
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(fetch_and_process_source, src) for src in NEWS_SOURCES.keys()]

            # Live monitoring — allows mid-execution stopping
            for f in futures:
                if stop_event.is_set():
                    print("[STOP] Cancelling pending tasks...")
                    return
                try:
                    f.result(timeout=5)
                except Exception as e:
                    print(f"[ERROR FUTURE] {e}")

        # ---- Granular sleep to stop instantly ----
        for _ in range(GLOBAL_TICK * 10):  # 5s = 50 x 0.1s checks
            if stop_event.is_set():
                print("[STOP] Collector exited gracefully during wait")
                return
            time.sleep(0.1)

    print("[STOP] Fully stopped collector")
