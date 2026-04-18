# file: AnnieXMedia/platforms/Youtube.py
# 100% Fully Compatible with AnnieXMedia Call System + Ultra Fast API

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

# Logging Setup
log = logging.getLogger("AnnieXMedia.YouTube")
log.setLevel(logging.INFO)

# ==========================================
# ⚡ إعدادات API السريع جداً
# ==========================================
API_URL = getattr(config, "YOUTUBE_API_URL", "https://shrutibots.site")

# Keep-Alive Connection للحفاظ على السرعة القصوى مع سيرفر 16 كور
_aio_connector = aiohttp.TCPConnector(limit=100, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector)
    return _aio_session

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self._api_sema = asyncio.Semaphore(15)

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def url(self, message) -> Optional[str]:
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
                    t = getattr(ent, "type", None)
                    off = getattr(ent, "offset", None)
                    ln = getattr(ent, "length", None)
                    if t == "url" and off is not None and ln is not None:
                        return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u:
                        return u.split("&si")[0]
                except Exception:
                    continue
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t:
            return 0
        if isinstance(t, int):
            return t
        try:
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts:
                s = s * 60 + p
            return s
        except Exception:
            return 0

    # ---------------------------------------------------------
    # دوال جلب التفاصيل الأساسية المتوافقة مع سورس أنين
    # ---------------------------------------------------------
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
                duration = data.get("duration", "0:00")
                details = {
                    "title": data.get("title", "Unknown"),
                    "link": data.get("link", f"https://www.youtube.com/watch?v={v_id}"),
                    "vidid": v_id,
                    "duration_min": duration,
                    "thumb": thumb,
                }
                return details, v_id
        except Exception as e:
            log.debug(f"Track search error: {e}")
            
        return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "0:00")
        sec = self._to_seconds(dur)
        return data.get("title", "Unknown"), dur, sec, data.get("thumb", ""), str(vid)

    async def title(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("title", "Unknown")

    async def duration(self, link: str, videoid: Union[bool, str, None] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url:
            return None
        try:
            base_dir = "downloads"
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            session = await get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception:
            pass
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            res = await VideosSearch(query, limit=limit).next()
            results = []
            for data in res.get("result", []):
                results.append({
                    "title": data.get("title", "Unknown"),
                    "vidid": data.get("id", ""),
                    "duration": data.get("duration", "0:00")
                })
            return results
        except Exception:
            return []

    async def slider(self, query: str, query_type: int) -> Tuple[str, str, str, str]:
        results = await self.search(query, limit=10)
        if not results:
            raise ValueError("No results found")
        idx = query_type % len(results)
        item = results[idx]
        vid = item["vidid"]
        d, _ = await self.track(vid, videoid=vid)
        return d.get("title", "Unknown"), str(d.get("duration_min", "0:00")), d.get("thumb", ""), vid

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        return [], link

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        return []

    async def video(self, link: str, is_live: bool = False) -> Tuple[int, str]:
        return 0, ""

    # ---------------------------------------------------------
    # 🔥 دالة Direct Link المستخدمة داخل call.py للتبديل بين الأغاني
    # ---------------------------------------------------------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        vid = ""
        if "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        if not vid: return link
        
        file_type = "audio" if prefer_audio else "video"
        session = await get_session()
        try:
            async with self._api_sema:
                async with session.get(f"{API_URL}/download", params={"url": vid, "type": file_type}, timeout=7) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try: data = orjson.loads(text)
                        except: import json; data = json.loads(text)
                        token = data.get("download_token")
                        if token:
                            return f"{API_URL}/stream/{vid}?type={file_type}&token={token}"
        except Exception as e:
            log.error(f"get_direct_link error for {vid}: {e}")
        return link  # Fallback to original link if API fails

    # ---------------------------------------------------------
    # 🔥 دالة Download الأساسية (متوافقة بنسبة 100%)
    # ---------------------------------------------------------
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Union[str, Tuple[Optional[str], bool]]:
        """
        ترجع رابط البث المباشر (String) الذي سيخزن في قاعدة البيانات كـ `file` أو `queued`.
        متوافق مع دالة `call.py` اللي بتعمل fetch للـ file.
        """
        is_video = bool(video or songvideo)
        
        vid = ""
        if videoid and str(videoid) not in ["True", "False"]:
            vid = str(videoid)
        elif link and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        elif link and "youtu.be/" in link:
            try: vid = link.split("youtu.be/")[1].split("?")[0]
            except: pass

        if not vid:
            return None

        file_type = "video" if is_video else "audio"
        session = await get_session()

        try:
            async with self._api_sema:
                # طلب التوكن
                async with session.get(f"{API_URL}/download", params={"url": vid, "type": file_type}, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = orjson.loads(text)
                        except:
                            import json
                            data = json.loads(text)
                        
                        token = data.get("download_token")
                        if token:
                            # السورس مستني مسار ملف أو رابط يقدر يشغله
                            # هنرجعله الرابط ده كـ String مباشر بدل Tuple عشان ميضربش إيرور في الـ DB
                            direct_stream_url = f"{API_URL}/stream/{vid}?type={file_type}&token={token}"
                            return direct_stream_url 
        except Exception as e:
            log.error(f"API Streaming Error for {vid}: {e}")

        # لو فشل، رجع اللينك الأصلي والـ Pytgcalls هيحاول يتعامل معاه
        return link

YouTube = YouTubeAPI()
