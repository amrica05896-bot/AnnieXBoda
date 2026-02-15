# file: AnnieXMedia/platforms/Youtube.py
# Authored By Certified Coders (c) 2026
# Zero-Error Native YouTube Resolve
# Features: Native Downloader (No Aria2), Full API Compatibility, Hybrid Search

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

# Fast JSON Parser
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes): return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

# Configuration
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

MAX_YTDLP_THREADS = 12
MAX_CONCURRENT_EXTRACTS = 6
YTDLP_SOCKET_TIMEOUT = 15  # Increased for Native stability
CACHE_DEFAULT_TTL = 600

_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

_aio_connector = aiohttp.TCPConnector(limit=100, ssl=False)
_aio_session: Optional[aiohttp.ClientSession] = None

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

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 15) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        return b"", b"timeout"
    except Exception:
        return b"", b"error"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if isinstance(videoid, str) and len(videoid) == 11:
        return "https://www.youtube.com/watch?v=" + videoid
    if not link: return ""
    link = link.strip()
    if "youtube.com" in link or "youtu.be" in link:
         # Internal ID format handling
         return link.split("&")[0]
    return link

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params: return int(params["expire"][0])
    except: pass
    return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()

    # 1. ✅ Core Verification (Prevents AttributeError 'exists')
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid: return True
        if not link: return False
        # Simple check for youtube domains or internal IDs
        return any(x in link for x in ["youtube.com", "youtu.be", "googleusercontent.com/youtube.com"])

    # 2. ✅ URL Extraction Logic
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

    # 3. ✅ Hybrid Search (py_yt -> yt-dlp)
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        # A. Fast Path (py_yt)
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
            except Exception as e:
                log.warning(f"Fast search failed: {e}")

        # B. Fallback Path (yt-dlp native)
        cmd = ["yt-dlp", "--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, _ = await _exec_proc(*cmd, timeout=12)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    d = _loads_bytes(line.encode())
                    results.append({"title": d.get("title"), "vidid": d.get("id"), "duration": d.get("duration_string")})
                except: pass
        return results

    # 4. ✅ Metadata Tracking
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "meta:" + prepared
        
        async with _meta_cache_lock:
            if key in _meta_cache:
                return _meta_cache[key][1], _meta_cache[key][2]

        # Try Fast Metadata
        if PY_YT_AVAILABLE and not videoid and "http" in prepared:
            try:
                s = VideosSearch(prepared, limit=1)
                r = await s.next()
                if r and r.get("result"):
                    d = r["result"][0]
                    details = {
                        "title": d.get("title"), 
                        "link": d.get("link"),
                        "vidid": d.get("id"), 
                        "duration_min": d.get("duration"),
                        "thumb": d.get("thumbnails")[0].get("url").split("?")[0]
                    }
                    async with _meta_cache_lock: _meta_cache[key] = (time.time(), details, d["id"])
                    return details, d["id"]
            except: pass

        # Native yt-dlp Metadata
        cmd = ["yt-dlp", "--dump-json", prepared, "--no-warnings"]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, _ = await _exec_proc(*cmd)
        if out:
            try:
                d = _loads_bytes(out)
                details = {
                    "title": d.get("title"), 
                    "link": d.get("webpage_url"),
                    "vidid": d.get("id"), 
                    "duration_min": d.get("duration"),
                    "thumb": d.get("thumbnail")
                }
                async with _meta_cache_lock: _meta_cache[key] = (time.time(), details, d["id"])
                return details, d["id"]
            except: pass
        
        return {"title": "Unknown", "duration_min": 0, "thumb": "", "vidid": ""}, ""

    # 5. ✅ Direct Stream Link (No Aria2 needed here)
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        key = prepared + str(prefer_audio)
        now = time.time()

        async with _direct_cache_lock:
            if key in _direct_cache:
                exp, url = _direct_cache[key]
                if exp > now + 10: return url

        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract():
                opts = {
                    "quiet": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": 10,
                    "extractor_args": {"youtube": {"player_client": ["android", "ios"]}}
                }
                if self.cookie: opts["cookiefile"] = self.cookie
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except: return None
            
            info = await loop.run_in_executor(self.pool, _extract)

        if info and info.get("url"):
            exp = _parse_expire(info["url"]) or int(now + 600)
            async with _direct_cache_lock: _direct_cache[key] = (exp - 5, info["url"])
            return info["url"]
        return None

    # 6. ✅ Native Download (Aria2 Removed)
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
        
        prepared = _normalize_link(link, videoid)
        is_video = bool(video or songvideo)
        
        # Stream Optimization check
        direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        if direct:
            return direct, True

        # Native Download Logic
        loop = asyncio.get_running_loop()
        def _native_download():
            try:
                base_dir = "/dev/shm/AnnieDownloads" if os.path.exists("/dev/shm") else "downloads"
                os.makedirs(base_dir, exist_ok=True)
                
                # Format Selection
                if is_video:
                    fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                else:
                    fmt = "bestaudio[ext=m4a]/bestaudio/best"

                opts = {
                    "format": fmt,
                    "outtmpl": f"{base_dir}/%(id)s.%(ext)s",
                    "quiet": True,
                    "cookiefile": self.cookie,
                    "noplaylist": True,
                    "hls_prefer_native": True, # Native HLS support
                }
                
                # Audio Post-processing
                if not is_video:
                     opts["postprocessors"] = [{
                         "key": "FFmpegExtractAudio",
                         "preferredcodec": "mp3",
                         "preferredquality": "192"
                     }]

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    
                    # Fix extension for audio
                    if not is_video and not path.endswith(".mp3"):
                        mp3_path = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3_path): return mp3_path
                    
                    return path
            except Exception as e:
                log.error(f"Native download failed: {e}")
                return None

        path = await loop.run_in_executor(self.pool, _native_download)
        return path, False

    # 7. ✅ Playlist Support
    async def playlist(self, link: str, limit: int, user_id=None, videoid=None) -> List[str]:
        if videoid: link = f"https://www.youtube.com/playlist?list={link}"
        cmd = [
            "yt-dlp", "-i", "--flat-playlist", "--playlist-end", str(limit),
            "--get-id", "--skip-download", "--no-warnings", link
        ]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, _ = await _exec_proc(*cmd, timeout=20)
        return [x for x in out.decode().split("\n") if x]

    # 8. ✅ Compatibility Wrappers (Crucial for avoiding AttributeErrors)
    async def details(self, link, videoid=None):
        d, vid = await self.track(link, videoid)
        return d.get("title", "Unknown"), d.get("duration_min", "0:00"), 0, d.get("thumb", ""), vid

    async def title(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("title", "Unknown")

    async def duration(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min", "0:00")

    async def thumbnail(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            path = f"downloads/thumb_{int(time.time())}.jpg"
            async with _ensure_aio_session() as sess:
                async with sess.get(url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f: f.write(await resp.read())
                        return path
        except: pass
        return None

# Instance
YouTube = YouTubeAPI()
