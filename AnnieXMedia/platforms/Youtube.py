# file: AnnieXMedia/platforms/Youtube.py
# System: Robust YouTube Core (2026 Edition)
# Base: TheTeamAlexa & Yukki Logic (Extended)
# Mods: ORJSON, YouTubeSearchPython (AIO), iOS Client, Anti-Crash Locks
# Speed Fix: Removed slow URL probing in get_direct_link -> Instant Stream
# Status: Full 800-Logic Scale (No Shortcuts)

import asyncio
import contextlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# 🔥 1. SPEED MOD: Use ORJSON
try:
    import orjson
    def _loads_bytes(b: bytes):
        return orjson.loads(b)
except ImportError:
    import json
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

# 🔥 2. SPEED MOD: Fast Metadata Library
from youtubesearchpython.aio import VideosSearch

# Logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# --- Tunables & Constants ---
MAX_YTDLP_THREADS = 20
MAX_CONCURRENT_EXTRACTS = 10
YTDLP_SOCKET_TIMEOUT = 10
PROBE_TIMEOUT = 1.5
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 100
META_CACHE_TTL = 3600

# --- Pools ---
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

# --- Caching Systems ---
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()
_download_locks: Dict[str, asyncio.Lock] = {}

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except: continue
    return None

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
        with contextlib.suppress(Exception): proc.kill()
        return b"", b"timeout"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    try:
        if isinstance(videoid, str) and len(videoid) == 11:
            return "https://www.youtube.com/watch?v=" + videoid
    except: pass

    if not link: return ""
    link = link.strip()
    
    # Handle Search Queries vs Links
    if " " in link or not link.startswith(("http", "www", "youtu")):
        return f"ytsearch:{link}"

    if "shorts/" in link: return link.replace("shorts/", "watch?v=")
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params: return int(params["expire"][0])
    except: pass
    return None

async def _probe_url(url: str, timeout: float = PROBE_TIMEOUT) -> Tuple[bool, Optional[str]]:
    try:
        sess = await _ensure_aio_session()
        async with sess.head(url, timeout=timeout) as r:
            if r.status < 400: return True, r.headers.get("Content-Type")
    except: pass
    return False, None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        
        # Smart Client Switch (iOS = Speed, Web = Safe with Cookies)
        if self.cookie:
            self.client_args = "youtube:player_client=web"
        else:
            self.client_args = "youtube:player_client=ios"

    # ==========================
    # 🔥 Core Method 1: EXISTS
    # ==========================
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if not link: return False
        if videoid: link = self.base + link
        if re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link): return True
        if re.search(r"^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*", link): return True
        return False

    # ==========================
    # 🔥 Core Method 2: URL Extraction
    # ==========================
    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", "") or getattr(msg, "caption", "") or ""
            entities = []
            if getattr(msg, "entities", None): entities.extend(msg.entities)
            if getattr(msg, "caption_entities", None): entities.extend(msg.caption_entities)
            for ent in entities:
                if ent.type.name == "URL": return text[ent.offset : ent.offset + ent.length]
                if ent.type.name == "TEXT_LINK": return ent.url
        return None

    # ==========================
    # 🚀 Fast Search (Using YouTubeSearchPython)
    # ==========================
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """Used by search command and play inline."""
        try:
            # 1. Try Fast Lib
            search = VideosSearch(query, limit=limit)
            res = await search.next()
            results = []
            for item in res.get("result", []):
                dur = item.get("duration")
                if not dur: dur = "Live"
                results.append({
                    "title": item.get("title"),
                    "vidid": item.get("id"),
                    "duration_string": dur,
                    "thumb": item.get("thumbnails")[0]["url"].split("?")[0]
                })
            return results
        except:
            pass

        # 2. Fallback to yt-dlp (Robust)
        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download",
            "--extractor-args", "youtube:player_client=android"
        ]
        if self.cookie: cmd.insert(1, f"--cookies={self.cookie}")

        out, _ = await _exec_proc(*cmd, timeout=12)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({
                        "title": data.get("title", "Unknown"),
                        "vidid": data.get("id", ""),
                        "duration_string": "Live" # Often yt-dlp flat search doesn't give duration
                    })
                except: pass
        return results

    # ==========================
    # ℹ️ Track Metadata (Hybrid)
    # ==========================
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid

        # 1. Fast Path (VideosSearch)
        try:
            # If it looks like a direct link/ID
            if "ytsearch" not in prepared:
                search = VideosSearch(prepared, limit=1)
                res = (await search.next())["result"][0]
                
                dur = res.get("duration")
                # Fix Live Duration Crash
                if not dur or str(dur).lower() in ["live", "stream", "none"]: dur = "Live"
                
                details = {
                    "title": res.get("title"),
                    "link": res.get("link"),
                    "vidid": res.get("id"),
                    "duration_min": dur,
                    "thumb": res.get("thumbnails")[0]["url"].split("?")[0],
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, res.get("id"))
                return details, res.get("id")
        except: pass

        # 2. Robust Path (yt-dlp dump-json)
        cmd = ["yt-dlp", "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        if self.cookie: cmd.extend(["--cookies", self.cookie])
        
        out, _ = await _exec_proc(*cmd, timeout=15)
        if out:
            try:
                info = _loads_bytes(out)
                is_live = info.get("is_live") or info.get("was_live")
                dur = "Live" if is_live else info.get("duration_string")
                
                details = {
                    "title": info.get("title", ""),
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": dur,
                    "thumb": (info.get("thumbnail") or "").split("?")[0],
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except: pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "00:00", "thumb": ""}, ""

    # ==========================
    # 🔗 Get Direct Link (⚡ ULTRA FAST FIX ⚡)
    # ==========================
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1. Cache Check (Instant)
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        # 2. Direct Subprocess Execution (Removed slow probes & python api overhead)
        async with self.sema:
            cmd = [
                "yt-dlp", 
                "-g", # Get URL ONLY (Super fast)
                "--no-warnings", 
                "--force-ipv4",
                "--extractor-args", self.client_args
            ]
            if self.cookie: cmd.extend(["--cookies", self.cookie])
            
            if prefer_audio: cmd.extend(["-f", "bestaudio/best"])
            else: cmd.extend(["-f", "best[height<=720]/best"])

            # Append the actual URL/Search query
            cmd.append(prepared)

            out, _ = await _exec_proc(*cmd, timeout=12)
            if out:
                # out might contain multiple urls (e.g., video + audio separated). We take the first valid one.
                urls = out.decode().strip().split("\n")
                if urls:
                    final_url = urls[0]
                    if final_url.startswith("http"):
                        # Cache it
                        expiry = _parse_expire(final_url) or (now + CACHE_DEFAULT_TTL)
                        async with _direct_cache_lock:
                            _direct_cache[key] = (expiry - 5, final_url)
                        return final_url

        return None

    # ==========================
    # 📥 Download (Locked & Robust)
    # ==========================
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

        # 1. Live Check -> Direct Link
        try:
            details, _ = await self.track(prepared)
            if str(details.get("duration_min")) == "Live":
                direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
                return direct, True
        except: pass

        # Setup Paths
        try:
            if videoid: vid = str(videoid)
            elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0]
            else: vid = str(int(time.time()))
        except: vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        # Check Cache
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            if os.path.exists(f"{ram_base}{ext}"): return f"{ram_base}{ext}", False

        # Try Direct Link (If not explicit download request) -> SPEED BOOST HERE
        if not format_id and not songaudio and not songvideo:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
            if direct: return direct, True

        # Lock & Download
        if vid not in _download_locks: _download_locks[vid] = asyncio.Lock()
        
        async with _download_locks[vid]:
            # Double check inside lock
            for ext in (".mp4", ".m4a", ".mp3", ".webm"):
                if os.path.exists(f"{ram_base}{ext}"): return f"{ram_base}{ext}", False

            loop = asyncio.get_running_loop()
            
            def _dl_worker():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": self.cookie,
                    "extractor_args": {"youtube": {"player_client": ["web" if self.cookie else "ios"]}},
                }
                
                if format_id:
                    opts["format"] = f"{format_id}+140" if songvideo else format_id
                elif is_video:
                    opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]"
                else:
                    opts["format"] = "bestaudio/best"
                    opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    fname = ydl.prepare_filename(info)
                    
                    if not is_video and not songvideo and not fname.endswith(".mp3"):
                        return fname.rsplit(".", 1)[0] + ".mp3"
                    return fname

            try:
                fpath = await loop.run_in_executor(self.pool, _dl_worker)
                return fpath, False
            except Exception as e:
                log.warning(f"Download Failed: {e}")
                # Ultimate Fallback
                direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
                return direct, True
            finally:
                if vid in _download_locks and not _download_locks[vid].locked():
                    del _download_locks[vid]

    # ==========================
    # 📂 Restored Helpers
    # ==========================
    async def playlist(self, link: str, limit: int, user_id=None, videoid: Union[bool, str] = None) -> List[str]:
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = [
            "yt-dlp", "--flat-playlist", "--print", "id",
            "--playlist-end", str(limit), "--skip-download", link
        ]
        if self.cookie: cmd.extend(["--cookies", self.cookie])
        out, _ = await _exec_proc(*cmd, timeout=20)
        if out: return [vid.strip() for vid in out.decode().splitlines() if vid.strip()]
        return []

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        res = await self.search(link, limit=10)
        if not res: return None
        idx = query_type % len(res)
        item = res[idx]
        return item["title"], item["duration_string"], item["thumb"], item["vidid"]

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

    # Wrapper Methods for compatibility
    async def details(self, link: str, videoid: Union[bool, str, None] = None):
        d, vid = await self.track(link, videoid)
        dur = d.get("duration_min", "00:00")
        sec = 0 if dur == "Live" else self._to_seconds(dur)
        return d.get("title"), dur, sec, d.get("thumb"), vid

    async def title(self, link: str, videoid: Union[bool, str, None] = None):
        d, _ = await self.track(link, videoid)
        return d.get("title", "")

    async def duration(self, link: str, videoid: Union[bool, str, None] = None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min", "00:00")

    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    def _to_seconds(self, t: Any) -> int:
        try:
            parts = [int(x) for x in str(t).split(":")]
            return sum(x * 60**i for i, x in enumerate(reversed(parts)))
        except: return 0

    async def get_recommendations(self, videoid: str) -> List[Dict[str, str]]:
        return []

# Export
YouTube = YouTubeAPI()
