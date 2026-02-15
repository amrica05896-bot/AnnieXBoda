# file: AnnieXMedia/platforms/Youtube.py
# Authored By Certified Coders (c) 2026
# Zero-Error Native YouTube Resolver (The Nuclear Edition)
# Fixes: 'Requested format is not available' by removing ALL restrictions.

import asyncio
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# Smart Import for Fast Search (py-yt-search)
try:
    from py_yt import VideosSearch
    PY_YT_AVAILABLE = True
except ImportError:
    PY_YT_AVAILABLE = False

# Logging Configuration
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# Performance settings
MAX_WORKERS = 10
CACHE_TTL = 600

_thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "/app/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if isinstance(videoid, str) and len(videoid) == 11:
        return f"https://www.youtube.com/watch?v={videoid}"
    if not link: 
        return ""
    return link.split("&")[0]

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.pool = _thread_pool
        self.cookie = get_cookie_file()
        
        # Base Options (Simple & Strong)
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'cookiefile': self.cookie,
            # استخدام عميل android بيضمن وجود صيغ صوتية خفيفة دائماً
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['webpage', 'configs']
                }
            }
        }

    # 1. Compatibility
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        return True 

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", "") or getattr(msg, "caption", "") or ""
            entities = (getattr(msg, "entities", []) or []) + (getattr(msg, "caption_entities", []) or [])
            for ent in entities:
                if getattr(ent, "url", None): return ent.url.split("&si")[0]
                if str(getattr(ent, "type", "")) in ["MessageEntityType.URL", "url"]:
                    off, ln = ent.offset, ent.length
                    return text[off:off+ln].split("&si")[0]
        return None

    # 2. Search (Smart Hybrid)
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        if PY_YT_AVAILABLE:
            try:
                search = VideosSearch(query, limit=limit)
                res = await search.next()
                if res and "result" in res:
                    return [{
                        "title": x.get("title"),
                        "vidid": x.get("id"),
                        "duration": x.get("duration"),
                        "thumb": x.get("thumbnails")[0].get("url").split("?")[0] if x.get("thumbnails") else ""
                    } for x in res["result"]]
            except Exception:
                pass

        # Fallback to Native
        opts = self.base_opts.copy()
        opts.update({'extract_flat': True, 'skip_download': True})
        
        loop = asyncio.get_running_loop()
        def _native_search():
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                    return res.get('entries', [])
                except: return []

        entries = await loop.run_in_executor(self.pool, _native_search)
        return [{
            "title": e.get("title"),
            "vidid": e.get("id"),
            "duration": e.get("duration_string")
        } for e in entries]

    # 3. Track (Robust Auto-Search)
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        if not videoid and link and not link.startswith(("http", "www", "rtmp")):
            results = await self.search(link, limit=1)
            if results:
                videoid = results[0]["vidid"]
                link = f"https://www.youtube.com/watch?v={videoid}"
            else:
                return {"title": "Not Found", "link": link, "vidid": "", "duration_min": 0, "thumb": ""}, ""

        prepared = _normalize_link(link, videoid)
        key = "meta:" + prepared
        
        async with _meta_cache_lock:
            if key in _meta_cache:
                return _meta_cache[key][1], _meta_cache[key][2]

        loop = asyncio.get_running_loop()
        def _get_meta():
            opts = self.base_opts.copy()
            opts['noplaylist'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    return ydl.extract_info(prepared, download=False)
                except Exception:
                    return None

        info = await loop.run_in_executor(self.pool, _get_meta)
        
        if info:
            details = {
                "title": info.get("title", "Unknown Track"),
                "link": info.get("webpage_url", prepared),
                "vidid": info.get("id", ""),
                "duration_min": info.get("duration", 0),
                "thumb": info.get("thumbnail", ""),
                "description": info.get("description", "")
            }
            async with _meta_cache_lock: 
                _meta_cache[key] = (time.time(), details, details["vidid"])
            return details, details["vidid"]
        
        return {"title": "Error", "link": prepared, "vidid": "", "duration_min": 0, "thumb": ""}, ""

    # 4. Stream (The Nuclear Fix for 'Requested format is not available')
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        key = f"stream:{prepared}:{prefer_audio}"
        
        async with _direct_cache_lock:
            if key in _direct_cache:
                if _direct_cache[key][0] > time.time() + 10:
                    return _direct_cache[key][1]

        loop = asyncio.get_running_loop()
        def _extract_stream():
            opts = self.base_opts.copy()
            
            # 🛑 التغيير الجذري: إزالة أي قيود على الصيغة
            # bestaudio/best معناها: هات أحسن صوت، لو مفيش هات أحسن فيديو فيه صوت.
            # ده بيضمن إننا منقعش في خطأ Format Not Available أبداً.
            fmt = 'bestaudio/best' if prefer_audio else 'best'
            
            opts.update({
                'format': fmt,
                'noplaylist': True,
                'skip_download': True
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(prepared, download=False)
                    return info.get('url')
                except Exception as e:
                    log.error(f"Stream Error: {e}")
                    return None

        url = await loop.run_in_executor(self.pool, _extract_stream)
        
        if url:
            async with _direct_cache_lock:
                _direct_cache[key] = (time.time() + CACHE_TTL, url)
            return url
        return None

    # 5. Download (Standardized)
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str, None] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        if not videoid and link and not link.startswith(("http", "www", "rtmp")):
             results = await self.search(link, limit=1)
             if results:
                videoid = results[0]["vidid"]
                link = f"https://www.youtube.com/watch?v={videoid}"

        prepared = _normalize_link(link, videoid)
        is_video = bool(video or songvideo)
        
        direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        if direct:
            return direct, True

        loop = asyncio.get_running_loop()
        def _download_native():
            base_dir = "/dev/shm/AnnieDownloads" if os.path.exists("/dev/shm") else "downloads"
            os.makedirs(base_dir, exist_ok=True)
            
            opts = self.base_opts.copy()
            
            # 🛑 صيغة التحميل الموحدة
            fmt = "bestvideo+bestaudio/best" if is_video else "bestaudio/best"
            
            opts.update({
                'format': fmt,
                'outtmpl': f"{base_dir}/%(id)s.%(ext)s",
                'noplaylist': True,
            })

            if not is_video:
                 opts["postprocessors"] = [{
                     "key": "FFmpegExtractAudio",
                     "preferredcodec": "mp3",
                     "preferredquality": "192"
                 }]

            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    
                    if not is_video:
                        base, _ = os.path.splitext(path)
                        mp3_path = base + ".mp3"
                        if os.path.exists(mp3_path): return mp3_path
                        
                    return path
                except Exception:
                    return None

        path = await loop.run_in_executor(self.pool, _download_native)
        return path, False

    # 6. Wrappers
    async def details(self, link, videoid=None):
        d, vid = await self.track(link, videoid)
        return d.get("title", "Unknown"), d.get("duration_min", 0), 0, d.get("thumb", ""), vid

    async def title(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("title", "Unknown")

    async def duration(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min", 0)

    async def thumbnail(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    async def playlist(self, link: str, limit: int, user_id=None, videoid=None) -> List[str]:
        if videoid: link = f"https://www.youtube.com/playlist?list={link}"
        loop = asyncio.get_running_loop()
        def _get_playlist():
            opts = self.base_opts.copy()
            opts.update({'extract_flat': True, 'playlistend': limit})
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    res = ydl.extract_info(link, download=False)
                    return [entry.get('id') for entry in res.get('entries', []) if entry.get('id')]
                except: return []
        return await loop.run_in_executor(self.pool, _get_playlist)

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            path = f"downloads/thumb_{int(time.time())}.jpg"
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f: f.write(await resp.read())
                        return path
        except: pass
        return None

# Instance
YouTube = YouTubeAPI()
