# Authored By Certified Coders © 2026
# Module: Youtube Resolver (Native Speed Edition ⚡)
# Optimized: No Aria2, Multi-threaded Native DL, Fast API Search

import asyncio
import contextlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp
from youtubesearchpython.aio import VideosSearch

# Optional faster JSON parser
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

# Logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# Tunables (Native Speed Optimization)
MAX_YTDLP_THREADS = 12
MAX_CONCURRENT_EXTRACTS = 10
YTDLP_SOCKET_TIMEOUT = 5
PROBE_TIMEOUT = 1.0
CACHE_DEFAULT_TTL = 600
AIO_CONN_LIMIT = 100
META_CACHE_TTL = 7200

# Pools / semaphores / caches
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

_aio_connector = aiohttp.TCPConnector(
    limit=AIO_CONN_LIMIT, 
    ssl=False, 
    keepalive_timeout=300,
    ttl_dns_cache=300
)
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
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

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params:
            return int(params["expire"][0])
    except Exception:
        pass
    return None

async def _probe_url(url: str, timeout: float = PROBE_TIMEOUT) -> Tuple[bool, Optional[str]]:
    try:
        sess = await _ensure_aio_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400:
                    return True, r.headers.get("Content-Type")
        except Exception:
            try:
                async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                    if r2.status in (200, 206):
                        return True, r2.headers.get("Content-Type")
            except Exception:
                return False, None
    except Exception:
        return False, None
    return False, None

def _score_format(fmt: dict, prefer_audio: bool) -> int:
    score = 0
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
    try:
        br = int(fmt.get("tbr") or fmt.get("abr") or 0)
        score += br // 100
    except Exception:
        pass
    return score

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        try:
            import curl_cffi
            self.impersonate = True
        except Exception:
            self.impersonate = False

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
                    if u:
                        return u.split("&si")[0]
                except Exception:
                    continue
        return None

    # 🚀 Turbo Search (using Library)
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            search = VideosSearch(query, limit=limit)
            result = await search.next()
            out = []
            for res in result.get("result", []):
                out.append({
                    "title": res.get("title", "Unknown"),
                    "vidid": res.get("id", ""),
                    "duration": res.get("duration", "00:00")
                })
            return out
        except Exception:
            return []

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL:
                    return data, vid
                _meta_cache.pop(key, None)

        try:
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", [])
        except Exception:
            results = []

        if results:
            data = results[0]
            thumb = (data.get("thumbnails") or [{}])[-1].get("url", "")
            details = {
                "title": data.get("title", "") or "",
                "link": data.get("link", prepared) or prepared,
                "vidid": data.get("id", "") or "",
                "duration_min": data.get("duration"),
                "thumb": thumb.split("?")[0] if thumb else "",
                "cookiefile": self.cookie,
            }
            async with _meta_cache_lock:
                _meta_cache[key] = (now, details, data.get("id", ""))
            return details, data.get("id", "")
        
        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": self.cookie}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if vid == "":
            raise ValueError("Video not found")
        dur = data.get("duration_min")
        sec = int(self._to_seconds(dur)) if dur else 0
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
    
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            base_dir = "downloads"
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            session = await _ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception as e:
            log.warning(f"Failed to download thumbnail: {e}")
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except Exception:
            return 0

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        """Ultra-Fast Slider using Library"""
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            search = VideosSearch(link, limit=10)
            res = (await search.next())["result"]
            if query_type >= len(res): return None
            
            item = res[query_type]
            return item["title"], item["duration"], item["thumbnails"][0]["url"].split("?")[0], item["id"]
        except:
            return None

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        ytdl_opts = {"quiet": True, "cookiefile": self.cookie}
        out: List[Dict[str, Any]] = []
        try:
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(prepared, download=False)
                for fmt in info.get("formats", []):
                    fs = fmt.get("filesize") or fmt.get("filesize_approx")
                    out.append({
                        "format": fmt.get("format"),
                        "filesize": fs,
                        "format_id": str(fmt.get("format_id")),
                        "ext": fmt.get("ext"),
                        "format_note": fmt.get("format_note", ""),
                    })
        except Exception:
            pass
        return out, prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3:
                    return url
                _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_info_blocking():
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    "extractor_args": {"youtube": {"player_client": ["android", "web"], "player_skip": ["webpage", "configs"]}},
                }
                if self.cookie: ydl_opts["cookiefile"] = self.cookie
                if self.impersonate: ydl_opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except Exception as e:
                    return {"_err": str(e)}

            info = await loop.run_in_executor(self.pool, _extract_info_blocking)

        if not info or (isinstance(info, dict) and info.get("_err")):
            return None

        # Process info
        top_url = info.get("url")
        if top_url and (await _probe_url(top_url))[0]:
            expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
            async with _direct_cache_lock:
                _direct_cache[key] = (expiry - 3, top_url)
            return top_url

        fmts = info.get("formats", [])
        candidates = []
        for f in fmts:
            url = f.get("url")
            if not url: continue
            proto = (f.get("protocol") or "").lower()
            if not proto.startswith(("http", "https")): continue
            if prefer_audio and (f.get("acodec") or "") == "none": continue
            if not prefer_audio and (f.get("vcodec") or "") != "none" and (f.get("acodec") or "") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if (f.get("acodec") or "") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, cand in candidates[:6]:
            if (await _probe_url(cand))[0]:
                expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry - 3, cand)
                return cand

        if not prefer_audio:
            return await self.get_direct_link(link, prefer_audio=True)
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
        """
        Stream Downloader (Native Speed)
        Return (path_or_direct_url_or_None, is_direct_flag)
        """
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        try:
            if videoid: vid = str(videoid)
            elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0]
            else: vid = str(int(time.time()))
        except: vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False

        loop = asyncio.get_running_loop()

        # 2) Specific Format Download
        if format_id:
            def _specific():
                try:
                    opts = {
                        "format": (f"{format_id}+140" if songvideo else format_id),
                        "outtmpl": f"{ram_base}.%(ext)s",
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "force_ipv4": True,
                        "concurrent_fragment_downloads": 5, # 🔥 NATIVE SPEED BOOST
                        "buffersize": 1024 * 1024,
                    }
                    if songaudio:
                        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                    if songvideo:
                        opts["merge_output_format"] = "mp4"
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=True)
                        path = ydl.prepare_filename(info)
                        if songaudio and not path.endswith(".mp3"):
                            p = os.path.splitext(path)[0] + ".mp3"
                            if os.path.exists(p): return p
                        return path
                except: return None
            res = await loop.run_in_executor(self.pool, _specific)
            return (res, False) if res else (None, False)

        # 3) Direct Link (Native Background DL)
        direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        if direct:
            loop.run_in_executor(self.pool, lambda: self._background_download(prepared, f"{ram_base}.%(ext)s", is_video))
            return direct, True

        # 4) Fallback Download (Native Speed)
        def _fallback():
            try:
                fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "force_ipv4": True,
                    "prefer_ffmpeg": True,
                    "concurrent_fragment_downloads": 5, # 🔥 NATIVE SPEED BOOST
                    "buffersize": 1024 * 1024,
                }
                if not is_video:
                    ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                else:
                    ydl_opts["merge_output_format"] = "mp4"
                    
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    return ydl.prepare_filename(info)
            except: return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded):
            return downloaded, False

        return None, False

    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            # ✅ Native Native Speed (No Aria2)
            fmt = "bestvideo[height<=720]+bestaudio/best" if is_video else "bestaudio/best"
            ydl_opts = {
                "format": fmt,
                "outtmpl": out_template,
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "concurrent_fragment_downloads": 5, # 🔥 Native Speed
                "buffersize": 1024 * 1024,
            }
            if is_video: ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except: pass

    async def playlist(self, link, limit, user_id=None, videoid=None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [key for key in out.decode().split("\n") if key]

YouTube = YouTubeAPI()
