# file: AnnieXMedia/platforms/Youtube.py
# System: Ultimate YouTube Core (Full API Compatibility)
# Fixes: 'exists' method, 'url' crash, Live Streams, Playlists, Caching
# Authored By Certified Coders © 2026

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

# --- JSON Parser ---
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except ImportError:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

# --- Logging ---
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

# --- Config ---
MAX_WORKERS = 16
CONCURRENT_DL_LIMIT = 6
SOCKET_TIMEOUT = 10
CACHE_TTL = 18000  # 5 Hours Cache

# --- Pools ---
_thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_extract_sema = asyncio.Semaphore(CONCURRENT_DL_LIMIT)
_aio_connector = aiohttp.TCPConnector(limit=100, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

# --- Caches ---
_direct_cache: Dict[str, Tuple[float, str]] = {}
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_lock = asyncio.Lock()
_download_locks: Dict[str, asyncio.Lock] = {}

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "assets/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None

async def _ensure_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector)
    return _aio_session

async def _exec_shell(cmd: List[str], timeout: int = 20) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        try: proc.kill()
        except: pass
        return b"", b"timeout"
    except Exception:
        return b"", b"error"

def _normalize_link(link: str, videoid: Union[str, bool, None] = None) -> str:
    try:
        if isinstance(videoid, str) and len(videoid) == 11:
            return f"https://www.youtube.com/watch?v={videoid}"
    except: pass

    if not link: return ""
    link = link.strip()
    
    if "shorts/" in link:
        return link.replace("shorts/", "watch?v=")
    if "youtu.be/" in link:
        try:
            vid = link.split("youtu.be/")[1].split("?")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        except: pass
        
    return link

def _extract_id(link: str) -> str:
    if "v=" in link:
        return link.split("v=")[1].split("&")[0]
    if "youtu.be/" in link:
        return link.split("/")[-1].split("?")[0]
    return str(int(time.time()))

def _parse_expire(url: str) -> int:
    try:
        qs = parse_qs(urlparse(url).query)
        if "expire" in qs:
            return int(qs["expire"][0])
    except: pass
    return int(time.time()) + 3600

class YouTubeAPI:
    def __init__(self):
        self.cookie = get_cookie_file()
        self.pool = _thread_pool

    # ==========================
    # 🔥 CORE METHOD: EXISTS (Fixes play.py error)
    # ==========================
    async def exists(self, link: str) -> bool:
        """
        Checks if the input is a valid YouTube link.
        Returns True if link, False if search query.
        """
        if not link:
            return False
        if re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link):
            return True
        if re.search(r"^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*", link):
            return True
        return False

    # ==========================
    # 🔍 Search & Slider
    # ==========================
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download", "--print-json"
        ]
        if self.cookie: cmd.extend(["--cookies", self.cookie])

        out, _ = await _exec_shell(cmd, timeout=12)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    d = _loads_bytes(line.encode())
                    results.append({
                        "title": d.get("title", "Unknown"),
                        "vidid": d.get("id", ""),
                        "duration_string": d.get("duration_string", "Live")
                    })
                except: pass
        return results

    async def slider(self, query: str, query_type: int) -> Tuple[str, str, str, str]:
        """Used by play.py for inline search results."""
        results = await self.search(query, limit=10)
        if not results:
            raise ValueError("No results found")
        
        # Ensure index is within bounds
        idx = query_type % len(results)
        item = results[idx]
        
        return (
            item["title"],
            item["duration_string"],
            f"https://img.youtube.com/vi/{item['vidid']}/hqdefault.jpg",
            item["vidid"]
        )

    # ==========================
    # ℹ️ Metadata (Track)
    # ==========================
    async def track(self, link: str, videoid: Union[str, bool, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = f"meta:{prepared}"
        now = time.time()

        async with _lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < 3600:
                    return data, vid

        cmd = [
            "yt-dlp", "--dump-json", prepared, "--no-warnings",
            "--socket-timeout", str(SOCKET_TIMEOUT), "--skip-download"
        ]
        if self.cookie: cmd.extend(["--cookies", self.cookie])

        out, _ = await _exec_shell(cmd, timeout=15)
        
        if out:
            try:
                info = _loads_bytes(out)
                is_live = info.get("is_live") or info.get("was_live") or False
                
                details = {
                    "title": info.get("title", "Unknown Track"),
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": "Live" if is_live else (info.get("duration_string") or "00:00"),
                    "thumb": (info.get("thumbnail") or "").split("?")[0],
                    "is_live": is_live
                }
                
                async with _lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except: pass

        return {"title": "Error", "link": prepared, "vidid": "", "duration_min": "00:00", "thumb": "", "is_live": False}, ""

    # ==========================
    # 📥 Download Engine
    # ==========================
    async def download(
        self,
        link: str,
        mystic: Any,
        video: bool = False,
        videoid: Union[str, bool, None] = None,
        **kwargs
    ) -> Tuple[Optional[str], bool]:
        
        prepared = _normalize_link(link, videoid)
        
        # Live Check
        try:
            details, _ = await self.track(prepared)
            if details.get("is_live"):
                direct = await self.get_direct_link(prepared, prefer_audio=not video)
                return direct, True
        except: pass

        vid = _extract_id(prepared)
        d_dir = "downloads"
        if not os.path.exists(d_dir): os.makedirs(d_dir, exist_ok=True)
        base_path = os.path.join(d_dir, vid)
        
        possible_files = [f"{base_path}.mp3", f"{base_path}.m4a", f"{base_path}.mp4", f"{base_path}.webm"]
        for p in possible_files:
            if os.path.exists(p) and os.path.getsize(p) > 1024:
                return p, False

        # Locking
        if vid not in _download_locks: _download_locks[vid] = asyncio.Lock()
        
        async with _download_locks[vid]:
            for p in possible_files:
                if os.path.exists(p) and os.path.getsize(p) > 1024:
                    return p, False

            loop = asyncio.get_running_loop()
            def _dl_task():
                fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" if video else "bestaudio/best"
                opts = {
                    "format": fmt,
                    "outtmpl": f"{base_path}.%(ext)s",
                    "quiet": True, "no_warnings": True, "noplaylist": True,
                    "cookiefile": self.cookie,
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}] if not video else [],
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    fname = ydl.prepare_filename(info)
                    if not video:
                        return fname.rsplit(".", 1)[0] + ".mp3"
                    return fname

            try:
                fpath = await loop.run_in_executor(self.pool, _dl_task)
                return fpath, False
            except:
                direct = await self.get_direct_link(prepared, prefer_audio=not video)
                return direct, True
            finally:
                if vid in _download_locks and not _download_locks[vid].locked():
                    del _download_locks[vid]

    # ==========================
    # 🔗 Direct Link (Cache)
    # ==========================
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        vid_id = _extract_id(prepared)
        cache_key = f"{vid_id}|{'audio' if prefer_audio else 'video'}"
        now = time.time()

        async with _lock:
            if cache_key in _direct_cache:
                expiry, url = _direct_cache[cache_key]
                if expiry > (now + 300): return url
                else: del _direct_cache[cache_key]

        async with _extract_sema:
            cmd = ["yt-dlp", "-g", prepared, "--no-warnings", "--force-ipv4"]
            if self.cookie: cmd.extend(["--cookies", self.cookie])
            if prefer_audio: cmd.extend(["-f", "bestaudio/best"])
            else: cmd.extend(["-f", "best[height<=720]/best"])

            out, _ = await _exec_shell(cmd, timeout=20)
            if out:
                url = out.decode().strip().split("\n")[0]
                if url.startswith("http"):
                    real_expiry = _parse_expire(url)
                    async with _lock:
                        _direct_cache[cache_key] = (real_expiry, url)
                    return url
        return None

    # ==========================
    # 📂 Utils & Fixes
    # ==========================
    async def playlist(self, link: str, limit: int, user_id=None, videoid: Union[str, bool] = None) -> List[str]:
        try:
            list_id = None
            if "list=" in link: list_id = link.split("list=")[1].split("&")[0]
            elif videoid: list_id = videoid
            
            if not list_id: return []

            cmd = [
                "yt-dlp", "--flat-playlist", "--print", "id",
                "--playlist-end", str(limit), "--no-warnings",
                f"https://www.youtube.com/playlist?list={list_id}"
            ]
            if self.cookie: cmd.extend(["--cookies", self.cookie])

            out, _ = await _exec_shell(cmd, timeout=25)
            if out: return [vid.strip() for vid in out.decode().splitlines() if vid.strip()]
        except: pass
        return []

    async def get_recommendations(self, videoid: str) -> List[Dict[str, str]]:
        return []

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            path = f"downloads/thumb_{int(time.time())}.jpg"
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
        except: pass
        return None

    async def details(self, link: str, videoid: Union[bool, str, None] = None):
        d, vid = await self.track(link, videoid)
        if not vid: raise ValueError("Video not found")
        dur_str = str(d.get("duration_min", "0"))
        sec = 0 if "Live" in dur_str else self._to_seconds(dur_str)
        return d.get("title"), dur_str, sec, d.get("thumb"), vid

    def _to_seconds(self, t: Any) -> int:
        try:
            if isinstance(t, int): return t
            parts = [int(x) for x in str(t).split(":")]
            return sum(x * 60**i for i, x in enumerate(reversed(parts)))
        except: return 0

    # 🔥 FIX: Crash-Proof URL Extraction (Prevents 'NoneType is not iterable') 🔥
    async def url(self, message) -> Optional[str]:
        if not message: return None
        
        # Safe Text Extraction
        text = getattr(message, "text", "") or getattr(message, "caption", "") or ""
        
        # Safe Entity Extraction (Always a list)
        entities = []
        if getattr(message, "entities", None):
            entities.extend(message.entities)
        if getattr(message, "caption_entities", None):
            entities.extend(message.caption_entities)
            
        for ent in entities:
            if ent.type.name == "URL":
                return text[ent.offset : ent.offset + ent.length]
            if ent.type.name == "TEXT_LINK":
                return ent.url
        return None

# Export
YouTube = YouTubeAPI()
