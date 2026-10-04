import pandas as pd
import threading
from collector.international_news_extract import start_collector, stop_collector
from app.db.database import SessionLocal
from app.db.models import NewsArticle

# Run extraction in background (non-blocking)
def start_news_collector():
    t = threading.Thread(target=start_collector)
    t.daemon = True
    t.start()

def stop_news_collector():
    stop_collector()

def get_latest_news(limit=50, offset=0):
    db = SessionLocal()
    try:
        articles = (
            db.query(NewsArticle)
            .order_by(NewsArticle.fetched_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "fetched_at": a.fetched_at,
                "source": a.source,
                "category": a.category,
                "impact": a.impact,
                "title": a.title,
                "url": a.url,
                "breaking_flag": a.breaking_flag,
                "content": a.content,
                "image_url": a.image_url,
                "video_url": a.video_url,
                "video_platform": a.video_platform
            }
            for a in articles
        ]
    finally:
        db.close()
