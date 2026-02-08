# file: AnnieXMedia/platforms/Youtube.py
# Turbo YouTube Resolver for AnnieXMedia (2026)
# Optimization: Fast Client (Android), Skip Webpage, High Concurrency

import asyncio
import contextlib
import json
import logging
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# --- [ JSON Parser Optimization ] ---
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes): return _orjson.loads(b)
except ImportError:
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

# --- [ Logging & Tunables ] ---
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers: logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# High Performance Settings
MAX_YTDLP_THREADS = 20        # Increased for mass handling
MAX_CONCURRENT_EXTRACTS = 10  # Increased parallelism
YTDLP_SOCKET_TIMEOUT = 5      # Fail fast, retry fast
PROBE_TIMEOUT = 1.0           # Quick probe
CACHE_DEFAULT_TTL = 600       # 10 Minutes cache for links
AIO_CONN_LIMIT = 100          # High connection pool
META_CACHE_TTL = 3600         # 1 Hour cache for metadata

# Thread Pool
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

# Optimized TCP Connector
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=60, ttl_dns_cache=300)
_aio_session: Optional[aiohttp.ClientSession] = None

# In-Memory Caches
_direct_cache: Dict[str, Tuple[int, str]] = {} 
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt", "cookies.txt", "AnnieXMedia/cookies.txt",
    "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0: return os.path.abspath(p)
    return None

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except (asyncio.TimeoutError, Exception):
        return b"", b""

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    # 🛑 Safety Filter: Prevent 'True' videoid
    if videoid is True or videoid is False: videoid = None
    
    if videoid: return f"https://www.youtube.com/watch?v={videoid}"
    if not link: return ""
    
    link = link.strip()
    if "youtube.com/0" in link: return link.split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> int:
    try:
        if "expire=" in url:
            return int(url.split("expire=")[1].split("&")[0])
    except: pass
    return int(time.time()) + CACHE_DEFAULT_TTL

async def _probe_url(url: str) -> bool:
    """Ultra fast probe"""
    try:
        sess = await _ensure_aio_session()
        async with sess.head(url, timeout=PROBE_TIMEOUT) as r:
            return r.status < 400
    except: return False

def _score_format(fmt: dict, prefer_audio: bool) -> int:
    score = 0
    proto = fmt.get("protocol", "").lower()
    vcodec = fmt.get("vcodec", "none")
    acodec = fmt.get("acodec", "none")
    
    if "https" in proto: score += 30
    if vcodec != "none" and acodec != "none": score += 50
    if prefer_audio and acodec != "none": score += 20
    if fmt.get("ext") == "mp4": score += 10
    return score + int(fmt.get("tbr") or 0) // 100

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        try:
            import curl_cffi
            self.impersonate = "chrome"
        except:
            self.impersonate = None

    async def url(self, message) -> Optional[str]:
        if not message: return None
        text = getattr(message, "text", "") or getattr(message, "caption", "")
        if not text: return None
        
        # Regex is faster than entity iteration for simple links
        match = re.search(r'(https?://(?:www\.)?youtu(?:be\.com|\.be)/[^\s]+)', text)
        if match: return match.group(1).split("&")[0]
        
        # Fallback to entities if regex fails (e.g. text links)
        if hasattr(message, "entities"):
            for ent in (message.entities or []):
                if ent.type == "url" and ent.offset is not None:
                    return text[ent.offset:ent.offset+ent.length].split("&")[0]
                if ent.type == "text_link":
                    return ent.url.split("&")[0]
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download",
            "--lazy-playlist"
        ]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, _ = await _exec_proc(*cmd, timeout=8)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({
                        "title": data.get("title", "Unknown"),
                        "vidid": data.get("id", ""),
                        "duration": data.get("duration_string", "")
                    })
                except: pass
        return results

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "meta:" + prepared
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid

        # 1. Try Fast Python API first
        def _fetch_meta():
            opts = {
                "quiet": True, "no_warnings": True, "skip_download": True,
                "socket_timeout": 5, "cookiefile": self.cookie,
                # 🛑 Speed Hack: Skip webpage download, use API
                "extractor_args": {"youtube": {"player_client": ["android", "web"], "player_skip": ["webpage", "configs", "js"]}}
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(prepared, download=False)

        try:
            info = await asyncio.get_running_loop().run_in_executor(self.pool, _fetch_meta)
            thumb = (info.get("thumbnail") or "").split("?")[0]
            details = {
                "title": info.get("title", "Unknown"),
                "link": info.get("webpage_url", prepared),
                "vidid": info.get("id", ""),
                "duration_min": info.get("duration"),
                "thumb": thumb,
                "cookiefile": self.cookie
            }
            async with _meta_cache_lock:
                _meta_cache[key] = (now, details, info.get("id", ""))
            return details, info.get("id", "")
        except Exception as e:
            log.warning(f"Meta fetch failed: {e}")
            return {"title": "Error", "link": prepared, "vidid": "", "thumb": ""}, ""

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        
        key = f"direct:{prepared}:{prefer_audio}"
        now = int(time.time())

        async with _direct_cache_lock:
            if key in _direct_cache:
                exp, url = _direct_cache[key]
                if exp > now + 10: return url

        async with self.sema:
            def _extract_core():
                opts = {
                    "quiet": True, "no_warnings": True, "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT, "format": "bestaudio/best" if prefer_audio else "best",
                    "cookiefile": self.cookie,
                    # 🛑 Speed Hack: This makes it 3x faster
                    "extractor_args": {"youtube": {"player_client": ["android"], "player_skip": ["webpage", "configs", "js"]}}
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(prepared, download=False)

            try:
                info = await asyncio.get_running_loop().run_in_executor(self.pool, _extract_core)
            except: return None

        if not info: return None
        
        # Select best format
        url = info.get("url")
        if not url:
            formats = info.get("formats", [])
            candidates = []
            for f in formats:
                u = f.get("url")
                if u and "http" in u:
                    candidates.append((_score_format(f, prefer_audio), u))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                url = candidates[0][1]

        if url:
            expire = _parse_expire(url)
            async with _direct_cache_lock:
                _direct_cache[key] = (expire - 10, url)
            return url
        return None

    async def download(
        self, link: str, mystic: Any, video: bool = False, videoid: Union[bool, str] = None,
        songaudio: bool = False, songvideo: bool = False, format_id: str = None, title: str = None
    ) -> Tuple[Optional[str], bool]:
        
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        
        # ID safe extraction
        vid = str(int(time.time()))
        if videoid and isinstance(videoid, str): vid = videoid
        elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0][:11]

        # RAM disk or Downloads
        base = "/dev/shm" if os.path.exists("/dev/shm") else "downloads"
        ram_path = os.path.join(base, vid)
        
        # Check cache
        for ext in [".mp3", ".mp4", ".m4a", ".webm"]:
            if os.path.exists(f"{ram_path}{ext}") and os.path.getsize(f"{ram_path}{ext}") > 1024:
                return f"{ram_path}{ext}", False

        # Fast Download Logic
        def _dl_task():
            fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            if format_id: fmt = f"{format_id}+140" if songvideo else format_id
            
            opts = {
                "format": fmt,
                "outtmpl": f"{ram_path}.%(ext)s",
                "cookiefile": self.cookie,
                "quiet": True,
                "no_warnings": True,
                "force_ipv4": True,
                "concurrent_fragment_downloads": 5, # 🛑 Download Speedup
                "extractor_args": {"youtube": {"player_client": ["web"]}}
            }
            
            if not is_video:
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    
                    if not is_video and not path.endswith(".mp3"):
                        mp3 = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3): return mp3
                    return path
            except Exception as e:
                log.error(f"Download failed: {e}")
                return None

        path = await asyncio.get_running_loop().run_in_executor(self.pool, _dl_task)
        return (path, False) if path else (None, False)

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            os.makedirs("downloads", exist_ok=True)
            path = f"downloads/thumb_{int(time.time())}.jpg"
            session = await _ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f: f.write(await resp.read())
                    return path
        except: pass
        return None

    # Helper accessors
    async def title(self, link, videoid=None): 
        d, _ = await self.track(link, videoid); return d.get("title", "")
    async def duration(self, link, videoid=None): 
        d, _ = await self.track(link, videoid); return d.get("duration_min")
    async def thumbnail(self, link, videoid=None): 
        d, _ = await self.track(link, videoid); return d.get("thumb", "")
    async def details(self, link, videoid=None):
        d, v = await self.track(link, videoid)
        return d.get("title"), d.get("duration_min"), 0, d.get("thumb"), v

YouTube = YouTubeAPI()
