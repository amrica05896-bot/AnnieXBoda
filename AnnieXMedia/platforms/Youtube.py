# Ultra Fast YouTube InnerTube (NO API KEY)
# AnnieXMedia - 2026 FIXED

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
    if not link:
        return ""
    if "youtu.be" in link:
        return link.split("/")[-1].split("?")[0]
    m = re.search(r"v=([a-zA-Z0-9_-]+)", link)
    if m:
        return m.group(1)
    return link


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

    # ✅ FIX: الدالة الناقصة (المهمه)
    async def url(self, message) -> Optional[str]:
        if not message:
            return None

        msgs = [message]
        if getattr(message, "reply_to_message", None):
            msgs.append(message.reply_to_message)

        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])

            for ent in entities:
                try:
                    if getattr(ent, "type", None) == "url":
                        off = getattr(ent, "offset", 0)
                        ln = getattr(ent, "length", 0)
                        return text[off: off + ln]
                    if getattr(ent, "url", None):
                        return ent.url
                except:
                    continue

        return None

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

        # FIX parsing (أفضل بكتير من split)
        contents = str(data)
        vids = re.findall(r'"videoId":"(.*?)"', contents)

        for vid in vids[:limit]:
            results.append({
                "title": "YouTube Video",
                "vidid": vid,
                "thumb": thumbnail(vid)
            })

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
