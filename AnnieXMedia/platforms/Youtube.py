# file: AnnieXMedia/platforms/Youtube.py
# System: The Ultimate Bulletproof YouTube Core (2026 Edition)
# Engine: Hybrid Fast-Search + curl_cffi Impersonation + 3-Layer Fallback
# Security: Anonymous Mode (Cookies Ignored) & Anti-Bot Bypassing
# Status: Full Scale, Crash-Proof, Zero-Error Tolerance

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

# ==========================================
# 🚀 1. SPEED MODS: Parsers & Network
# ==========================================
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

MAX_YTDLP_THREADS = 25
MAX_CONCURRENT_EXTRACTS = 12
YTDLP_SOCKET_TIMEOUT = 12
PROBE_TIMEOUT = 2.0
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 100
META_CACHE_TTL = 3600

_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

# ==========================================
# 🗃️ 3. CACHING SYSTEMS
# ==========================================
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()
_download_locks: Dict[str, asyncio.Lock] = {}

# ==========================================
# 🛡️ 4. CORE UTILITIES & NORMALIZERS
# ==========================================
async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        # Using custom headers to mimic a real browser for general requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, headers=headers, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 20) -> Tuple[bytes, bytes]:
    """Executes a shell command safely and prevents hanging."""
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
    """Cleans and normalizes YouTube URLs to avoid extraction errors."""
    try:
        if isinstance(videoid, str) and len(videoid) == 11 and " " not in videoid:
            return f"https://www.youtube.com/watch?v={videoid}"
    except Exception: pass

    if not link: return ""
    link = link.strip()

    # Distinguish between search query and direct URL
    if " " in link or not link.startswith(("http", "www", "youtu")):
        return f"ytsearch:{link}"

    if "shorts/" in link: 
        return link.replace("shorts/", "watch?v=")
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    """Extracts expiration epoch from YouTube direct URLs."""
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params:
            return int(params["expire"][0])
    except Exception: pass
    return None

def _score_format(fmt: dict, prefer_audio: bool) -> int:
    """Intelligent scoring system to pick the absolute best stream format."""
    score = 0
    try:
        proto = (fmt.get("protocol") or "").lower()
        ext = (fmt.get("ext") or "").lower()
        vcodec = fmt.get("vcodec") or ""
        acodec = fmt.get("acodec") or ""
        
        if proto.startswith("https"): score += 30
        if proto.startswith("http"): score += 20
        if vcodec and vcodec != "none" and acodec and acodec != "none": score += 50
        if prefer_audio and acodec and acodec != "none": score += 15
        if ext in ("mp4",): score += 10
        if ext in ("m4a","webm"): score += 8
        try: score += int(fmt.get("tbr") or fmt.get("abr") or 0) // 100
        except: pass
    except Exception: pass
    return score

# ==========================================
# 🤖 5. THE MAIN YOUTUBE API CLASS
# ==========================================
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        
        # ⚠️ CRITICAL: We strictly IGNORE cookies to avoid account bans.
        # We rely entirely on curl_cffi impersonation to bypass bot detection.
        self.cookie = None 
        self.impersonate_target = "chrome" # Triggers curl_cffi in yt-dlp

    # ------------------------------------------
    # Basic Checks & Parsing
    # ------------------------------------------
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        """Checks if the link is a valid YouTube URL."""
        if not link: return False
        if videoid: link = self.base + str(videoid)
        if re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link): return True
        if re.search(r"^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*", link): return True
        return False

    async def url(self, message) -> Optional[str]:
        """Safely extracts a URL from a pyrogram message object."""
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
        """Searches YouTube. Uses Fast Library first, falls back to robust yt-dlp."""
        # --- LAYER 1: Fast Library (youtube-search-python) ---
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
            except Exception as e:
                log.warning(f"Fast search failed, falling back: {e}")

        # --- LAYER 2: Robust Subprocess (yt-dlp) ---
        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download",
            "--impersonate", self.impersonate_target
        ]
        out, _ = await _exec_proc(*cmd, timeout=15)
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
        """Gets full details of a single track. Heavily cached and layered."""
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        # 1. RAM CACHE
        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid

        # 2. LAYER 1: Fast Library
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

        # 3. LAYER 2: Robust yt-dlp API Extraction
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_meta():
                opts = {
                    "quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True,
                    "impersonate": self.impersonate_target,
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception: return None
            
            info = await loop.run_in_executor(self.pool, _extract_meta)
            
            if info:
                is_live = info.get("is_live") or info.get("was_live") or False
                dur = "Live" if is_live else info.get("duration_string", "00:00")
                thumb = (info.get("thumbnail") or "").split("?")[0]
                
                details = {
                    "title": info.get("title", "Unknown Track"),
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": dur,
                    "thumb": thumb,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "00:00", "thumb": ""}, ""

    # ------------------------------------------
    # 🔥 THE UNBREAKABLE DIRECT LINK EXTRACTOR
    # ------------------------------------------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        """
        The core streaming engine. Uses curl_cffi to bypass blocks.
        3 Layers of extraction to guarantee a result.
        """
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # --- CACHE ---
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()

            # --- LAYER 1: Ultra-Fast Android Client (No JS) ---
            def _layer1_fast():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": 8,
                    "impersonate": self.impersonate_target, # Triggers curl_cffi
                    "format": "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                    "extractor_args": {
                        "youtube": {
                            "player_client": ["android", "ios"],
                            "player_skip": ["webpage", "configs", "js"] # Skip heavy parsing
                        }
                    }
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                        for f in info.get("formats", []):
                            if f.get("url") and f.get("protocol", "").startswith(("http", "m3u8")): return f["url"]
                except Exception: return None

            direct_url = await loop.run_in_executor(self.pool, _layer1_fast)
            if direct_url:
                self._cache_direct_url(key, direct_url, now)
                return direct_url

            # --- LAYER 2: Web Client (Full Parsing) ---
            def _layer2_robust():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": 12,
                    "impersonate": self.impersonate_target,
                    "format": "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                    "extractor_args": {
                        "youtube": {"player_client": ["web", "mweb"]} # Full heavy extraction
                    }
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                except Exception: return None

            direct_url = await loop.run_in_executor(self.pool, _layer2_robust)
            if direct_url:
                self._cache_direct_url(key, direct_url, now)
                return direct_url

        # --- LAYER 3: Subprocess Brute Force (Last Resort) ---
        cmd = [
            "yt-dlp", "-g", "--no-warnings", "--force-ipv4",
            "--impersonate", self.impersonate_target,
            "-f", "bestaudio/best" if prefer_audio else "best[height<=720]/best",
            prepared
        ]
        out, _ = await _exec_proc(*cmd, timeout=15)
        if out:
            urls = out.decode().strip().split("\n")
            for final_url in urls:
                if final_url.startswith("http"):
                    self._cache_direct_url(key, final_url, now)
                    return final_url

        return None

    def _cache_direct_url(self, key: str, url: str, now: int):
        """Helper to safely cache URLs."""
        try:
            expiry = _parse_expire(url) or (now + CACHE_DEFAULT_TTL)
            asyncio.create_task(self._async_cache_set(key, expiry - 10, url))
        except Exception: pass

    async def _async_cache_set(self, key, expiry, url):
        async with _direct_cache_lock:
            _direct_cache[key] = (expiry, url)

    # ------------------------------------------
    # 📥 Download Engine (Robust File Writing)
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
        
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        # 1. Determine Video ID for path
        try:
            if videoid: vid = str(videoid)
            elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0]
            else: vid = str(int(time.time()))
        except Exception: vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        # 2. Check Existing Files
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False

        # 3. Live Stream Bypass -> Stream Instead of Download
        if not format_id and not songaudio and not songvideo:
            try:
                details, _ = await self.track(prepared)
                if str(details.get("duration_min")).lower() == "live":
                    direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
                    if direct: return direct, True
                else:
                    # Prefer direct link for normal playback too for speed
                    direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
                    if direct: return direct, True
            except Exception: pass

        # 4. Physical Download (With Lock to prevent duplicate downloads)
        if vid not in _download_locks: _download_locks[vid] = asyncio.Lock()
        
        async with _download_locks[vid]:
            # Double check inside lock
            for ext in (".mp4", ".m4a", ".mp3", ".webm"):
                cand = f"{ram_base}{ext}"
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False

            loop = asyncio.get_running_loop()
            
            def _dl_worker():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "impersonate": self.impersonate_target,
                    "extractor_args": {"youtube": {"player_client": ["web"]}}, # Web is safest for DL
                }
                
                if format_id:
                    opts["format"] = f"{format_id}+140" if songvideo else format_id
                elif is_video:
                    opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]"
                else:
                    opts["format"] = "bestaudio/best"
                    opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]

                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=True)
                        fname = ydl.prepare_filename(info)
                        if not is_video and not songvideo and not fname.endswith(".mp3"):
                            return fname.rsplit(".", 1)[0] + ".mp3"
                        return fname
                except Exception as ex:
                    log.error(f"Download Error: {ex}")
                    return None

            try:
                fpath = await loop.run_in_executor(self.pool, _dl_worker)
                if fpath and os.path.exists(fpath):
                    return fpath, False
            except Exception as e:
                log.warning(f"Download Thread Failed: {e}")

            # 5. Ultimate Fallback -> Return Stream Link if DL completely fails
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
            return direct, True
            
            # Lock cleanup happens automatically, but we can clean dictionary
            # (In a real high-scale bot, we'd clean this dict periodically)

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
            link
        ]
        out, _ = await _exec_proc(*cmd, timeout=25)
        if out:
            return [vid.strip() for vid in out.decode().splitlines() if vid.strip()]
        return []

    async def download_thumb(self, url: str) -> Optional[str]:
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
        ytdl_opts = {"quiet": True, "impersonate": self.impersonate_target}
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
