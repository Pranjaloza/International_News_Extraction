from bs4 import BeautifulSoup
import requests
import re

HEADERS = {"User-Agent": "InternationalFastNewsBot/1.0"}

YOUTUBE_REGEX = r"(https?://(www\.)?(youtube\.com|youtu\.be)/[^\s\"'>]+)"

def extract_media(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # ---- IMAGE (Open Graph) ----
        image_url = None
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]

        # ---- VIDEO ----
        html = r.text
        video_url = None
        video_platform = None

        yt_match = re.search(YOUTUBE_REGEX, html)
        if yt_match:
            video_url = yt_match.group(1)
            video_platform = "youtube"

        return image_url, video_url, video_platform

    except Exception as e:
        print("[MEDIA ERROR]", e)
        return None, None, None
