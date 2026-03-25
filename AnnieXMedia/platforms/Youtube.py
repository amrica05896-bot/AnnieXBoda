# Ultra Fast YouTube InnerTube (NO API KEY)
# AnnieXMedia - 2026 Version

import asyncio
import aiohttp
import time
import re
from typing import Dict, List, Tuple, Optional, Any

# =========================
# CONFIG
# =========================

INNERTUBE_CONTEXT = {
    "context": {
        "client": {
            "clientName": "ANDROID",
            "clientVersion": "19.09.37"
        }
    }
}

SEARCH_URL = "https://www.youtube.com/youtubei/v1/search"
PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"

HEADERS = {
    "User-Agent": "com.google.android.youtube/",
    "Content-Type": "application/json"
}

# =========================
# GLOBALS
# =========================

_session = None
_cache = {}
_cache_time = 300

# =========================
# HELPERS
# =========================

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


def get_video_id(link: str) -> str:
    if "youtu.be" in link:
        return link.split("/")[-1]
    m = re.search(r"v=([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else link


def thumbnail(vid):
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def pick_stream(data: Dict, audio=True) -> Optional[str]:
    formats = data.get("streamingData", {}).get("adaptiveFormats", [])

    best = None
    best_br = 0

    for f in formats:
        mime = f.get("mimeType", "")
        if audio and "audio" not in mime:
            continue
        if not audio and "video" not in mime:
            continue

        url = f.get("url")
        if not url:
            continue

        br = f.get("bitrate", 0)
        if br > best_br:
            best_br = br
            best = url

    return best


# =========================
# MAIN CLASS
# =========================

class YouTubeAPI:

    async def request(self, url: str, data: dict):
        session = await get_session()
        async with session.post(url, json=data, headers=HEADERS) as r:
            return await r.json()

    # =========================
    # SEARCH
    # =========================
    async def search(self, query: str, limit=5):
        if query in _cache:
            t, res = _cache[query]
            if time.time() - t < _cache_time:
                return res

        data = await self.request(SEARCH_URL, {
            **INNERTUBE_CONTEXT,
            "query": query
        })

        results = []

        for item in str(data).split("videoId"):
            if len(results) >= limit:
                break

            try:
                vid = item.split('"')[2]
                results.append({
                    "title": "YouTube Video",
                    "vidid": vid,
                    "thumb": thumbnail(vid)
                })
            except:
                pass

        _cache[query] = (time.time(), results)
        return results

    # =========================
    # TRACK INFO
    # =========================
    async def track(self, link: str):
        vid = get_video_id(link)

        data = await self.request(PLAYER_URL, {
            **INNERTUBE_CONTEXT,
            "videoId": vid
        })

        title = data.get("videoDetails", {}).get("title", "Unknown")
        duration = data.get("videoDetails", {}).get("lengthSeconds", 0)

        return {
            "title": title,
            "vidid": vid,
            "duration": int(duration),
            "thumb": thumbnail(vid)
        }

    # =========================
    # DIRECT LINK
    # =========================
    async def stream(self, link: str, audio=True):
        vid = get_video_id(link)

        data = await self.request(PLAYER_URL, {
            **INNERTUBE_CONTEXT,
            "videoId": vid
        })

        return pick_stream(data, audio)

    # =========================
    # PLAY
    # =========================
    async def video(self, link: str):
        url = await self.stream(link, audio=True)
        return (1, url) if url else (0, "")

    # =========================
    # PLAYLIST (basic)
    # =========================
    async def playlist(self, link: str, limit=10):
        return []


YouTube = YouTubeAPI()
