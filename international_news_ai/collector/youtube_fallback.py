import requests
import os
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

def search_youtube_video(title: str, source: str) -> str | None:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return None

    query = f"{title} {source} news"

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "order": "relevance",
        "safeSearch": "strict",
        "key": api_key,
    }

    try:
        r = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        items = data.get("items", [])
        if not items:
            return None

        video_id = items[0]["id"]["videoId"]
        return f"https://www.youtube.com/watch?v={video_id}"

    except Exception:
        return None
