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
import csv
import os
import time
from datetime import datetime
from threading import Event
import threading
import json
from dotenv import load_dotenv
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor

# =========================
# INIT
# =========================
load_dotenv()
client = OpenAI()

# =========================
# CONFIG
# =========================
CSV_FILE = "international_fast_news3.csv"

CSV_FIELDS = [
    "fetched_at",
    "source",
    "category",
    "impact",
    "title",
    "url",
    "breaking_flag",
    "content",
]

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
MAX_ARTICLE_AGE_SECONDS = 24 * 60 * 60
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
csv_lock = threading.Lock()


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

    except Exception:
        return None, "none", False


# =========================
# UTILITIES
# =========================
def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


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
def load_existing_hashes():
    """
    Load previously ingested article URLs into memory
    to prevent duplicates after restart.
    """
    if not os.path.exists(CSV_FILE):
        return

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url"):
                seen_articles.add(article_hash(row["url"]))
            if row.get("title"):
                seen_articles.add(article_hash(row["title"]))

    print(f"[INIT] Loaded {len(seen_articles)} existing article hashes")
# =========================
# CONTENT EXTRACTION
# =========================
def extract_content(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        text = trafilatura.extract(
            r.text,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        if not text or len(text.split()) < MIN_CONTENT_WORDS:
            return None
        return text
    except:
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
        published_ts = time.mktime(published_struct) if published_struct else None

        articles.append({
            "source": source_name,
            "title": title,
            "url": link,
            "_published_ts": published_ts,
        })

    return articles

def fetch_and_process_source(src):
    cfg = NEWS_SOURCES[src]
    now = time.time()
    if now - last_polled[src] < cfg["interval"]:
        return
    last_polled[src] = now
    print(f"[FETCH] {src}")
    articles = fetch_rss(src, cfg["url"])
    for art in articles:
        process_article(art)

# =========================
# ARTICLE PIPELINE
# =========================
def process_article(a):
    published_ts = a.get("_published_ts")
    if published_ts and time.time() - published_ts > MAX_ARTICLE_AGE_SECONDS:
        print(f"[SKIP] Old article | {a['title'][:60]}")
        return

    title = a.get("title", "").strip()
    if not title:
        return

    category, impact, breaking = analyze_article_llm(title)
    if not category:
        print(f"[SKIP] Old article | {a['title'][:60]}")
        return

    time.sleep(0.4)

    url = resolve_url(a["url"])
    if is_duplicate(url, title):
        print(f"[SKIP] Duplicate | {title[:60]}")
        return

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
    }

    with csv_lock:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)

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
    init_csv()
    load_existing_hashes()

    while not stop_event.is_set():
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(fetch_and_process_source, NEWS_SOURCES.keys())

        time.sleep(GLOBAL_TICK)
