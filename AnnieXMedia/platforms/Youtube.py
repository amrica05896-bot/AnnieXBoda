# file: AnnieXMedia/platforms/Youtube.py
# Optimized for Abdullah's 10-Core Fly.io API (2026 Edition)
# Python 3.13+ Lazy Loading Fixed

import asyncio
import re
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from pyrogram import enums, types
from youtubesearchpython.aio import VideosSearch
import config

try:
    import orjson
except ImportError:
    import json as orjson

# إعداد السجلات
log = logging.getLogger("AnnieXMedia.YouTube")

# ==========================================
# ⚡ إعدادات API السيرفر الـ 10 كور الخاص بك
# ==========================================
API_URL = "https://api-tx-stq.fly.dev"

# تعريف المتغيرات بـ None عشان نمنع بايثون 3.13 من الاعتراض
_aio_connector: Optional[aiohttp.TCPConnector] = None
_aio_session: Optional[aiohttp.ClientSession] = None

# ✅ (Lazy Loading) تهيئة الـ Session والـ Connector جوه الـ Loop فقط
async def get_session() -> aiohttp.ClientSession:
    global _aio_session, _aio_connector
    
    if _aio_connector is None or _aio_connector.closed:
        _aio_connector = aiohttp.TCPConnector(limit=100, ssl=False, keepalive_timeout=300)
        
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector)
        
    return _aio_session


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        # السماح بـ 15 طلب متوازي (متروك بـ None للتهيئة الآمنة)
        self._api_sema = None

    # ✅ (Lazy Loading) تهيئة السيميفور جوه الـ Loop
    async def get_sema(self) -> asyncio.Semaphore:
        if self._api_sema is None:
            self._api_sema = asyncio.Semaphore(15)
        return self._api_sema

    async def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

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
                    if ent.type == enums.MessageEntityType.URL:
                        return text[ent.offset : ent.offset + ent.length].split("&si")[0]
                    if ent.url:
                        return ent.url.split("&si")[0]
                except:
                    continue
        return None

    def _to_seconds(self, t: Optional[Union[str, int]]) -> int:
        if not t: return 0
        if isinstance(t, int): return t
        try:
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except: return 0

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid = ""
        if videoid and str(videoid) not in ["True", "False"]:
            vid = str(videoid)
        elif link and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
            
        query = vid if vid else link
        try:
            res = await VideosSearch(query, limit=1).next()
            results = res.get("result", [])
            if results:
                data = results[0]
                v_id = data.get("id", vid)
                thumb = (data.get("thumbnails") or [{}])[-1].get("url", "").split("?")[0]
                details = {
                    "title": data.get("title", "Unknown"),
                    "link": f"https://www.youtube.com/watch?v={v_id}",
                    "vidid": v_id,
                    "duration_min": data.get("duration", "0:00"),
                    "thumb": thumb,
                }
                return details, v_id
        except Exception as e:
            log.debug(f"Search error: {e}")
        return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "0:00")
        return data["title"], dur, self._to_seconds(dur), data["thumb"], str(vid)

    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        تتواصل مع الـ API الخاص بك وتجلب الرابط المباشر فوراً.
        """
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            vid = link.split("v=")[1].split("&")[0]
        
        target_url = f"https://www.youtube.com/watch?v={vid}" if vid else link
        file_type = "video" if video else "audio"
        
        session = await get_session()
        sema = await self.get_sema()  # جلب السيميفور بأمان
        
        try:
            async with sema:
                params = {"url": target_url, "type": file_type}
                async with session.get(f"{API_URL}/download", params=params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        direct_url = data.get("direct_url")
                        if direct_url:
                            return direct_url
                    log.error(f"API Error: {resp.status}")
        except Exception as e:
            log.error(f"Download API Failure: {e}")
        return None

    # دالة التبديل السريع (الرابط المباشر)
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        return await self.download(link, None, video=not prefer_audio)

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            res = await VideosSearch(query, limit=limit).next()
            return [{"title": d["title"], "vidid": d["id"], "duration": d["duration"]} for d in res.get("result", [])]
        except: return []

YouTube = YouTubeAPI()
