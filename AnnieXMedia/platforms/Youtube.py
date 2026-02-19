# file: AnnieXMedia/platforms/Youtube.py
# System: The Ultimate Bulletproof YouTube Core (2026 Edition)
# Engine: Hybrid Fast-Search + curl_cffi Impersonation + Smart Cookie Routing
# Logic: 1-Second extraction for normal tracks, Deep Deciphering for Live/Age-Restricted
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
YTDLP_SOCKET_TIMEOUT = 15
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
# 🍪 4. COOKIE MANAGER
# ==========================================
COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    """Scans multiple locations to find a valid Netscape cookies.txt file."""
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None

# ==========================================
# 🛡️ 5. CORE UTILITIES & NORMALIZERS
# ==========================================
async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
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
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params:
            return int(params["expire"][0])
    except Exception: pass
    return None

def _score_format(fmt: dict, prefer_audio: bool) -> int:
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
# 🤖 6. THE MAIN YOUTUBE API CLASS
# ==========================================
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        
        # ⚠️ Load Cookies
        self.cookie = get_cookie_file() 
        if self.cookie:
            log.info(f"🍪 Loaded YouTube Cookies from: {self.cookie}")
        else:
            log.warning("⚠️ No cookies.txt found. Proceeding with anonymous mode.")

        # ⚠️ Forcing curl_cffi impersonation
        self.impersonate_target = "chrome" 

    # ------------------------------------------
    # Basic Checks & Parsing
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
        # --- LAYER 1: Fast Library ---
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
        if self.cookie: cmd.extend(["--cookies", self.cookie])
        
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

        # 3. LAYER 2: Robust yt-dlp API
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_meta():
                opts = {
                    "quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True,
                    "impersonate": self.impersonate_target,
                }
                if self.cookie: opts["cookiefile"] = self.cookie
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
    # 🔥 THE SMART DIRECT LINK EXTRACTOR
    # ------------------------------------------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True, is_live: bool = False) -> Optional[str]:
        """
        The core streaming engine. Uses curl_cffi and Cookies.
        Smart Routing:
        - If Normal Video -> Uses Android client & skips JS (No Cookies to avoid mismatch). SPEED: 1s.
        - If Live / Failed -> Uses Web client & parses JS (With Cookies). SPEED: ~4s.
        """
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # --- RAM CACHE ---
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()

            # LAYER 1: FAST EXTRACT (Android, No JS, No Cookies)
            def _layer1_fast():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": 6,
                    "impersonate": self.impersonate_target,
                    "format": "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                    "extractor_args": {
                        "youtube": {
                            "player_client": ["android", "ios"],
                            "player_skip": ["webpage", "configs", "js"]
                        }
                    }
                }
                # Intentionally NOT using cookies here to avoid Android+WebCookie mismatch
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                        for f in info.get("formats", []):
                            if f.get("url") and f.get("protocol", "").startswith(("http", "m3u8")): return f["url"]
                except Exception: return None
                return None

            # LAYER 2: ROBUST EXTRACT (Web, Full JS, With Cookies)
            def _layer2_robust():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": 15,
                    "impersonate": self.impersonate_target,
                    "format": "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                    "extractor_args": {"youtube": {"player_client": ["web"]}} # Full Deciphering
                }
                if self.cookie: opts["cookiefile"] = self.cookie # Safely inject cookies for Web client
                
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                        for f in info.get("formats", []):
                            if f.get("url") and f.get("protocol", "").startswith(("http", "m3u8")): return f["url"]
                except Exception as e:
                    log.error(f"Robust Extraction failed: {e}")
                    return None
                return None

            # Route 1: Try Fast (If not explicitly live)
            direct_url = None
            if not is_live:
                direct_url = await loop.run_in_executor(self.pool, _layer1_fast)
            
            # Route 2: Fallback to Robust (If Live, or if Fast failed due to Age restriction/DRM)
            if not direct_url:
                log.info("Using Robust Web Extraction (Live Stream or Age Restricted detected)...")
                direct_url = await loop.run_in_executor(self.pool, _layer2_robust)

            # Route 3: Subprocess Brute Force
            if not direct_url:
                log.info("API Failed, resorting to Subprocess Brute Force...")
                cmd = [
                    "yt-dlp", "-g", "--no-warnings", "--force-ipv4",
                    "--impersonate", self.impersonate_target,
                    "--extractor-args", "youtube:player_client=web",
                    "-f", "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                ]
                if self.cookie: cmd.extend(["--cookies", self.cookie])
                cmd.append(prepared)
                
                out, _ = await _exec_proc(*cmd, timeout=20)
                if out:
                    urls = out.decode().strip().split("\n")
                    for final_url in urls:
                        if final_url.startswith("http"):
                            direct_url = final_url
                            break

            if direct_url:
                expiry = _parse_expire(direct_url) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry - 10, direct_url)
                return direct_url

        return None

    # ------------------------------------------
    # 📥 Download Engine (Streaming Entry Point)
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

        # 1. Path Generation
        try:
            if videoid: vid = str(videoid)
            elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0]
            else: vid = str(int(time.time()))
        except Exception: vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        # 2. Check Existing Disk Cache
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False

        # 3. Stream Routing (Bypass Download entirely if not requested)
        if not format_id and not songaudio and not songvideo:
            try:
                # Find out if it's Live
                details, _ = await self.track(prepared)
                is_live_stream = str(details.get("duration_min")).lower() == "live"
                
                # Get the link using the Smart Router
                direct = await self.get_direct_link(prepared, prefer_audio=not is_video, is_live=is_live_stream)
                if direct: return direct, True
            except Exception as e:
                log.debug(f"Direct link extraction failed during download check: {e}")

        # 4. Physical Download (With Lock)
        if vid not in _download_locks: _download_locks[vid] = asyncio.Lock()
        
        async with _download_locks[vid]:
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
                    # Web client is the most stable for physical downloads
                    "extractor_args": {"youtube": {"player_client": ["web"]}}, 
                }
                if self.cookie: opts["cookiefile"] = self.cookie
                
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
                    log.error(f"yt-dlp Download Error: {ex}")
                    return None

            try:
                fpath = await loop.run_in_executor(self.pool, _dl_worker)
                if fpath and os.path.exists(fpath): return fpath, False
            except Exception as e:
                log.error(f"Download Thread Exception: {e}")

            # ULTIMATE RESCUE: If physical download fails, force stream extraction as web client
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video, is_live=True)
            if direct: return direct, True
            
            # If everything fails, play.py will handle None safely
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
