# file: AnnieXMedia/platforms/Youtube.py
# Optimized for Abdullah's 10-Core Server (Internal Turbo Extraction 2026)
# Fully Compatible with Docker & Node.js Runtime

import asyncio
import re
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import yt_dlp
from pyrogram import enums
from youtubesearchpython.aio import VideosSearch
import config

# إعداد السجلات
log = logging.getLogger("AnnieXMedia.YouTube")

# مسار الكوكيز الخاص بك لتخطي القيود
COOKIES_PATH = "AnnieXMedia/assets/cookies.txt"

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        # السماح بـ 15 عملية استخراج متوازية لقوة الـ 10 كور
        self._api_sema = None

    async def get_sema(self) -> asyncio.Semaphore:
        if self._api_sema is None:
            self._api_sema = asyncio.Semaphore(15)
        return self._api_sema

    async def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    async def url(self, message) -> Optional[str]:
        if not message: return None
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
                except: continue
        return None

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
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
                return {
                    "title": data.get("title", "Unknown"),
                    "link": f"https://www.youtube.com/watch?v={v_id}",
                    "vidid": v_id,
                    "duration_min": data.get("duration", "0:00"),
                    "thumb": thumb,
                }, v_id
        except Exception as e: log.debug(f"Search error: {e}")
        return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "0:00")
        parts = [int(p) for p in str(dur).split(":")]
        secs = 0
        for p in parts: secs = secs * 60 + p
        return data["title"], dur, secs, data["thumb"], str(vid)

    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        🚀 محرك الاستخراج الداخلي المطور (Turbo Mode)
        يستخدم Node.js لفك التشفير وتنسيق 140 للسرعة القصوى.
        """
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            vid = link.split("v=")[1].split("&")[0]
        
        target_url = f"https://www.youtube.com/watch?v={vid}" if vid else link
        
        # ⚡ إعدادات الاستخراج (نفس منطق الـ Go API)
        ydl_opts = {
            "format": "best[ext=mp4]/best" if video else "140", # 140 = m4a (أسرع شيء للبث)
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            # 🚀 استغلال الدوكر: استخدام Node.js لفك التشفير
            "javascript_executor": "node",
        }

        if os.path.isfile(COOKIES_PATH):
            ydl_opts["cookiefile"] = COOKIES_PATH

        sema = await self.get_sema()
        loop = asyncio.get_running_loop()

        def _extract():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)
                    return info.get("url")
            except Exception as ex:
                log.error(f"Turbo extraction error: {ex}")
                return None

        try:
            async with sema:
                # تشغيل الاستخراج في Thread Pool لمنع تجميد البوت
                direct_url = await loop.run_in_executor(None, _extract)
                return direct_url
        except Exception as e:
            log.error(f"Internal Engine Failure: {e}")
        return None

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        return await self.download(link, None, video=not prefer_audio)

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            res = await VideosSearch(query, limit=limit).next()
            return [{"title": d["title"], "vidid": d["id"], "duration": d["duration"]} for d in res.get("result", [])]
        except: return []

YouTube = YouTubeAPI()
