# file: AnnieXMedia/platforms/Youtube.py
# System: The Ultimate PURE STREAMING YouTube Core (2026 Edition)
# Engine: Zero-Disk Streaming + curl_cffi Impersonation + Web Client Only
# Logic: ALL requests are forced into Instant Direct Links. Physical downloading is OBLITERATED.
# Status: Lightning Fast, Crash-Proof, No Disk Space Used.

import asyncio
import contextlib
import logging
import os
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# 🚀 1. SPEED MOD: Use ORJSON
try:
    import orjson
    def _loads_bytes(b: bytes): return orjson.loads(b)
except ImportError:
    import json
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

try:
    from youtubesearchpython.aio import VideosSearch
except ImportError:
    VideosSearch = None

# ==========================================
# 🛠️ 2. CONFIGURATION & POOLS
# ==========================================
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

MAX_YTDLP_THREADS = 30
MAX_CONCURRENT_EXTRACTS = 15
YTDLP_SOCKET_TIMEOUT = 12
AIO_CONN_LIMIT = 100
META_CACHE_TTL = 3600

_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

# ==========================================
# 🗃️ 3. CACHING SYSTEMS (RAM ONLY)
# ==========================================
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

# ==========================================
# 🍪 4. COOKIE MANAGER
# ==========================================
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
        except Exception:
            continue
    return None

# ==========================================
# 🛡️ 5. CORE UTILITIES
# ==========================================
async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, headers=headers, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 15) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"
    except Exception as e:
        log.error(f"Subprocess Execution Error: {e}")
        return b"", str(e).encode()

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    try:
        if isinstance(videoid, str) and len(videoid) == 11 and " " not in videoid:
            return f"https://www.youtube.com/watch?v={videoid}"
    except Exception: pass

    if not link: return ""
    link = link.strip()

    if " " in link or not link.startswith(("http", "www", "youtu")):
        return f"ytsearch:{link}"

    if "shorts/" in link: 
        return link.replace("shorts/", "watch?v=")
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params:
            return int(params["expire"][0])
    except Exception: pass
    return None

# ==========================================
# 🤖 6. THE MAIN YOUTUBE API CLASS
# ==========================================
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        
        # ⚠️ COOKIES ENABLED
        self.cookie = get_cookie_file() 
        if self.cookie:
            log.info(f"🍪 Loaded YouTube Cookies from: {self.cookie}")
        
        # ⚠️ CHROME IMPERSONATION ENABLED (curl_cffi)
        self.impersonate_target = "chrome" 

    # ------------------------------------------
    # Exists & URL
    # ------------------------------------------
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if not link: return False
        if videoid: link = self.base + str(videoid)
        if re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link): return True
        if re.search(r"^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*", link): return True
        return False

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
                    if ent.type.name == "URL": return text[ent.offset : ent.offset + ent.length].split("&si")[0]
                    if ent.type.name == "TEXT_LINK": return ent.url.split("&si")[0]
                except Exception: continue
        return None

    # ------------------------------------------
    # High-Speed Metadata & Searching
    # ------------------------------------------
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        if VideosSearch:
            try:
                search_obj = VideosSearch(query, limit=limit)
                res = await search_obj.next()
                results = []
                for item in res.get("result", []):
                    dur = item.get("duration")
                    if not dur or str(dur).lower() in ["live", "stream", "none"]: dur = "Live"
                    results.append({
                        "title": item.get("title", "Unknown"),
                        "vidid": item.get("id", ""),
                        "duration_string": dur,
                        "thumb": (item.get("thumbnails") or [{}])[0].get("url", "").split("?")[0]
                    })
                if results: return results
            except Exception: pass

        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download",
            "--impersonate", self.impersonate_target
        ]
        if self.cookie: cmd.extend(["--cookies", self.cookie])
        
        out, _ = await _exec_proc(*cmd, timeout=12)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({
                        "title": data.get("title", "Unknown"),
                        "vidid": data.get("id", ""),
                        "duration_string": data.get("duration_string", "Live")
                    })
                except Exception: pass
        return results

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid

        if VideosSearch and "ytsearch" not in prepared:
            try:
                search_obj = VideosSearch(prepared, limit=1)
                res = (await search_obj.next())["result"][0]
                dur = res.get("duration")
                if not dur or str(dur).lower() in ["live", "stream", "none"]: dur = "Live"
                details = {
                    "title": res.get("title", "Unknown Track"),
                    "link": res.get("link", prepared),
                    "vidid": res.get("id", ""),
                    "duration_min": dur,
                    "thumb": (res.get("thumbnails") or [{}])[0].get("url", "").split("?")[0],
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, res.get("id", ""))
                return details, res.get("id", "")
            except Exception: pass

        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_meta():
                opts = {
                    "quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True,
                    "impersonate": self.impersonate_target,
                    "extractor_args": {"youtube": {"player_client": ["web"]}} # STRICTLY WEB
                }
                if self.cookie: opts["cookiefile"] = self.cookie
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception: return None
            
            info = await loop.run_in_executor(self.pool, _extract_meta)
            if info:
                is_live = info.get("is_live") or info.get("was_live") or False
                dur = "Live" if is_live else info.get("duration_string", "00:00")
                details = {
                    "title": info.get("title", "Unknown Track"),
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": dur,
                    "thumb": (info.get("thumbnail") or "").split("?")[0],
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "00:00", "thumb": ""}, ""

    # ------------------------------------------
    # 🔥 PURE STREAMING ENGINE (Get Direct Link)
    # ------------------------------------------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        """
        The core streaming engine. Uses curl_cffi & Web Client to bypass blocks and extract m3u8/googlevideo.
        """
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1. INSTANT RAM CACHE
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 5: return url
                else: _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()

            # 2. PYTHON API EXTRACTION (Fast & Deciphers everything)
            def _api_extract():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": 10,
                    "impersonate": self.impersonate_target, 
                    "format": "bestaudio/best" if prefer_audio else "best[ext=mp4][height<=720]/best",
                    "extractor_args": {"youtube": {"player_client": ["web"]}} # STRICTLY WEB
                }
                if self.cookie: opts["cookiefile"] = self.cookie

                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                        for f in info.get("formats", []):
                            if f.get("url") and f.get("protocol", "").startswith(("http", "m3u8")): return f["url"]
                except Exception as e:
                    log.error(f"Stream Extraction Error: {e}")
                    return None
                return None

            direct_url = await loop.run_in_executor(self.pool, _api_extract)

        # 3. SUBPROCESS BRUTE FORCE (If API gets stuck)
        if not direct_url:
            log.info("API Stream Extraction failed, using Subprocess...")
            cmd = [
                "yt-dlp", "-g", "--no-warnings", "--force-ipv4",
                "--impersonate", self.impersonate_target,
                "--extractor-args", "youtube:player_client=web",
                "-f", "bestaudio/best" if prefer_audio else "best[ext=mp4][height<=720]/best",
                prepared
            ]
            if self.cookie: cmd.extend(["--cookies", self.cookie])
            out, _ = await _exec_proc(*cmd, timeout=15)
            if out:
                urls = out.decode().strip().split("\n")
                for final_url in urls:
                    if final_url.startswith("http"):
                        direct_url = final_url
                        break

        # 4. SAVE TO CACHE AND RETURN
        if direct_url:
            expiry = _parse_expire(direct_url) or (now + 18000) # Cache for 5 hours if no expire token
            async with _direct_cache_lock:
                _direct_cache[key] = (expiry - 60, direct_url)
            return direct_url

        return None

    # ------------------------------------------
    # 📥 THE OVERRIDDEN DOWNLOAD METHOD
    # ------------------------------------------
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
        """
        🚨 OBLITERATED PHYSICAL DOWNLOADS 🚨
        This method now FORCES every request to act as a stream.
        It immediately returns the Direct URL (m3u8/HTTP) and `True` (indicating it's a direct stream).
        ZERO disk space used. Maximum speed achieved.
        """
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        # Force fetch the direct stream URL
        direct_stream_url = await self.get_direct_link(prepared, prefer_audio=not is_video)

        if direct_stream_url:
            # Return URL, and 'True' which tells stream.py this is a direct HTTP/M3U8 link, not a local file.
            return direct_stream_url, True

        # If it utterly fails (e.g. video deleted), return None
        log.error(f"CRITICAL: Failed to get stream link for {prepared}")
        return None, False

    # ------------------------------------------
    # 🗂️ Utilities & Helpers
    # ------------------------------------------
    async def playlist(self, link: str, limit: int, user_id=None, videoid: Union[bool, str] = None) -> List[str]:
        if videoid: link = self.listbase + str(videoid)
        if "&" in link: link = link.split("&")[0]
        
        cmd = [
            "yt-dlp", "--flat-playlist", "--print", "id",
            "--playlist-end", str(limit), "--skip-download",
            "--impersonate", self.impersonate_target,
        ]
        if self.cookie: cmd.extend(["--cookies", self.cookie])
        cmd.append(link)

        out, _ = await _exec_proc(*cmd, timeout=20)
        if out:
            return [vid.strip() for vid in out.decode().splitlines() if vid.strip()]
        return []

    async def download_thumb(self, url: str) -> Optional[str]:
        """Thumbnails are small, so saving them to disk is fine for Telegram covers."""
        if not url: return None
        try:
            base_dir = "downloads"
            if not os.path.exists(base_dir): os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}_{random.randint(1,100)}.jpg")
            
            session = await _ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception as e:
            log.debug(f"Thumb DL fail: {e}")
        return None

    # --- Wrappers for existing Bot Architecture ---
    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if vid == "": raise ValueError("Video not found")
        dur = data.get("duration_min", "00:00")
        sec = 0 if str(dur).lower() == "live" else self._to_seconds(dur)
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

    async def slider(self, query: str, query_type: int):
        results = await self.search(query, limit=10)
        if not results: raise ValueError("No results")
        idx = query_type % len(results)
        item = results[idx]
        return item["title"], item["duration_string"], item["thumb"], item["vidid"]

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(float(p)) for p in str(t).split(":")]
            return sum(x * 60**i for i, x in enumerate(reversed(parts)))
        except Exception: return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        ytdl_opts = {
            "quiet": True, 
            "impersonate": self.impersonate_target,
            "extractor_args": {"youtube": {"player_client": ["web"]}}
        }
        if self.cookie: ytdl_opts["cookiefile"] = self.cookie
        
        out: List[Dict[str, Any]] = []
        try:
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(prepared, download=False)
                for fmt in info.get("formats", []):
                    out.append({
                        "format": fmt.get("format"),
                        "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                        "format_id": str(fmt.get("format_id")),
                        "ext": fmt.get("ext"),
                        "format_note": fmt.get("format_note", ""),
                    })
        except Exception: pass
        return out, prepared

# Export
YouTube = YouTubeAPI()
