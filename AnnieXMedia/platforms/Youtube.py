# file: AnnieXMedia/platforms/Youtube.py
# 🚀 PURE API EDITION: 100% Shrutibots API (Zero yt-dlp interference)

import asyncio
import contextlib
import json
import logging
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp

# Logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# --- 🚀 الثوابت والمفاتيح ---
GOOGLE_API_KEY = "AIzaSyCIXHJRql0WncJmXLKITtC7oOP57eJDmzM"
SHRUTI_API_URL = "https://shrutibots.site"

# Pools / caches
AIO_CONN_LIMIT = 64
META_CACHE_TTL = 3600

_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 15) -> Tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid:
        return "https://www.youtube.com/watch?v=" + str(videoid)
    if not link:
        return ""
    link = link.strip()
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_iso_duration(duration_str: str) -> str:
    if not duration_str: return "0:00"
    if duration_str == "P0D": return "Live"
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return "0:00"
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    if hours > 0: return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="

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
                    t = getattr(ent, "type", None)
                    off = getattr(ent, "offset", None)
                    ln = getattr(ent, "length", None)
                    if t == "url" and off is not None and ln is not None:
                        return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u: return u.split("&si")[0]
                except Exception: continue
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            sess = await _ensure_aio_session()
            api_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults={limit}&q={urllib.parse.quote(query)}&type=video&key={GOOGLE_API_KEY}&fields=items(id/videoId,snippet/title)"
            async with sess.get(api_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for item in data.get("items", []):
                        results.append({
                            "title": item.get("snippet", {}).get("title", "Unknown"),
                            "vidid": item.get("id", {}).get("videoId", ""),
                            "duration": "0:00" 
                        })
                    if results: return results
        except Exception: pass
        return []

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid
                _meta_cache.pop(key, None)

        target_vid = None
        match = re.search(r"([0-9A-Za-z_-]{11})", prepared)
        if match: target_vid = match.group(1)

        try:
            sess = await _ensure_aio_session()
            if target_vid:
                url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id={target_vid}&key={GOOGLE_API_KEY}"
                async with sess.get(url, timeout=4) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("items"):
                            item = data["items"][0]
                            details = {
                                "title": item["snippet"]["title"],
                                "link": f"https://youtube.com/watch?v={target_vid}",
                                "vidid": target_vid,
                                "duration_min": _parse_iso_duration(item["contentDetails"]["duration"]),
                                "thumb": item["snippet"]["thumbnails"].get("high", {}).get("url", ""),
                            }
                            async with _meta_cache_lock: _meta_cache[key] = (now, details, target_vid)
                            return details, target_vid
        except Exception: pass

        return {"title": "Unknown", "link": prepared, "vidid": target_vid or "", "duration_min": "0:00", "thumb": ""}, target_vid or ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if not vid: raise ValueError("Video not found")
        dur = data.get("duration_min")
        try:
            parts = [int(p) for p in str(dur).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            sec = s
        except Exception: sec = 0
        return data.get("title", ""), dur, sec, data.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("title", "")

    async def duration(self, link: str, videoid: Union[bool, str, None] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")
    
    # 🚀 الخدعة الكبرى: دالة وهمية لمنع البوت من استدعاء yt-dlp للصيغ!
    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        dummy_formats = [
            {"format_id": "api_audio", "format": "Shrutibots Ultra Fast Audio", "ext": "m4a", "filesize": 5000000},
            {"format_id": "api_video", "format": "Shrutibots Ultra Fast Video", "ext": "mp4", "filesize": 25000000}
        ]
        return dummy_formats, prepared

    # 🚀 استخراج الـ ID بنفس طريقة تيرميكس بالمللي
    def _extract_id_like_termux(self, url_or_id: str) -> str:
        if "googleusercontent.com" in url_or_id:
            vid_temp = url_or_id.split("/")[-1].split("?")[0]
            if len(vid_temp) >= 11:
                return vid_temp[-11:]
        elif "v=" in url_or_id:
            return url_or_id.split("v=")[1].split("&")[0][:11]
        else:
            match = re.search(r"([0-9A-Za-z_-]{11})", url_or_id)
            if match:
                return match.group(1)
        return url_or_id[-11:] if len(url_or_id) >= 11 else url_or_id

    # 🚀 الاعتماد الكلي على API Shrutibots
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        
        vid_id = self._extract_id_like_termux(prepared)
        if not vid_id or len(vid_id) != 11:
            log.error(f"❌ فشل استخراج الـ ID الصحيح من الرابط: {prepared}")
            return None

        key = vid_id + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # الكاش الداخلي للبوت
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now + 3:
                return cached[1]

        media_type = "audio" if prefer_audio else "video"
        
        try:
            sess = await _ensure_aio_session()
            log.info(f"1️⃣ جاري طلب التوكن للفيديو: {vid_id} ...")
            
            async with sess.get(f"{SHRUTI_API_URL}/download", params={"url": vid_id, "type": media_type}, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("download_token")
                    if token:
                        stream_url = f"{SHRUTI_API_URL}/stream/{vid_id}?type={media_type}&token={token}"
                        
                        # طباعة التأكيد في اللوج عشان تشوفه بعينك
                        log.info(f"✅ تم سحب الرابط بنجاح! الرابط جاهز للتشغيل:")
                        log.info(f"🔗 URL: {stream_url[:60]}... (مخفي للطول)")
                        
                        async with _direct_cache_lock:
                            _direct_cache[key] = (now + 18000, stream_url) 
                        return stream_url
                else:
                    log.error(f"❌ الـ API رفض الطلب! الكود: {resp.status}")
        except Exception as e:
            log.error(f"❌ حدث خطأ أثناء الاتصال بالـ API: {e}")
                
        return None

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
    ) -> Tuple[Optional[str], bool]:
        
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        log.info(f"🚀 بدء معالجة التشغيل عبر الـ API...")
        direct = await self.get_direct_link(prepared, prefer_audio=not is_video)

        if direct:
            return direct, True
            
        return None, False

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try: result = [key for key in out.decode().split("\n") if key]
        except Exception: result = []
        return result

# exported instance
YouTube = YouTubeAPI()
