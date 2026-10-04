from fastapi import APIRouter
from app.services.collector_service import start_news_collector, stop_news_collector, get_latest_news

router = APIRouter()


# Start collector
@router.post("/start")
def start():
    start_news_collector()
    return {"status": "news extraction started"}

# Stop collector
@router.post("/stop")
def stop():
    stop_news_collector()
    return {"status": "news extraction stopped"}

# Fetch recent news via API
@router.get("/latest")
def latest(limit: int = 50, offset: int = 0):
    return get_latest_news(limit, offset)