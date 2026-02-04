# file: AnnieXMedia/platforms/Youtube.py
# Author: Certified Fixes 2026 (extreme-perf, drop-in replacement)
# Purpose: Ultra-fast YouTube resolver + robust download/cache + PyTgCalls-safe formats
# Notes:
#  - Use yt-dlp Python API in a bounded threadpool + semaphore to avoid subprocess thrash.
#  - Probe resolved direct URLs with lightweight HEAD / small-range GET to avoid NoVideoSourceFound.
#  - Cache direct URLs with respect to expire parameter when present.
#  - Provide track/details/formats/get_direct_link/download/playlist/slider and background caching.
#  - Designed to be drop-in for AnnieXMedia bots using PyTgCalls.

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch

# ---------------- logging ----------------
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    # basic config if not configured by app
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# ---------------- Config & tunables ----------------
if os.path.exists("/dev/shm"):
    DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
else:
    DOWNLOAD_PATH = os.path.abspath("downloads")
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

COOKIE_PATH_CANDIDATES = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

# Performance tuning
MAX_CONCURRENT_YTDLP = 6        # concurrently allow this many API extractions
YTDLP_THREADPOOL = 16          # threadpool size for blocking yt-dlp API calls
YTDLP_SOCKET_TIMEOUT = 6       # yt-dlp socket timeout
URL_PROBE_TIMEOUT = 2          # aiohttp HEAD probe timeout (seconds)
CACHE_DEFAULT_TTL = 300        # seconds fallback TTL when expire param missing
YOUTUBE_META_TTL = 3600        # metadata cache TTL (seconds)
MAX_WORKERS = YTDLP_THREADPOOL

# Threadpool + semaphores
_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_ytdlp_semaphore = asyncio.Semaphore(MAX_CONCURRENT_YTDLP)

# Shared aiohttp connector/session - reused for probes and thumbnail download
_AIO_CONN = aiohttp.TCPConnector(limit=64, ssl=False)
_AIO_SESSION: Optional[aiohttp.ClientSession] = None

# ---------------- caches ----------------
# metadata cache: key -> (timestamp, details dict, vid)
_meta_cache: Dict[str, Tuple[float, Dict, str]] = {}
_meta_cache_lock = asyncio.Lock()

# direct URL cache: key -> (expiry_epoch, direct_url)
_direct_url_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()

# ---------------- helpers ----------------
def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATH_CANDIDATES:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _AIO_SESSION
    if _AIO_SESSION is None or _AIO_SESSION.closed:
        _AIO_SESSION = aiohttp.ClientSession(connector=_AIO_CONN, raise_for_status=False)
    return _AIO_SESSION

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"

def _to_seconds(t: Optional[str]) -> int:
    if not t:
        return 0
    try:
        parts = [int(p) for p in str(t).split(":")]
        s = 0
        for p in parts:
            s = s * 60 + p
        return s
    except Exception:
        return 0

def _now_key(q: str) -> str:
    return "q:" + (q or "")

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

def _parse_expiry_from_url(url: str) -> Optional[int]:
    try:
        q = urlparse(url).query
        params = parse_qs(q)
        if "expire" in params:
            v = params["expire"][0]
            return int(v)
    except Exception:
        pass
    return None

async def _probe_url(url: str, timeout: int = URL_PROBE_TIMEOUT) -> Tuple[bool, Optional[str]]:
    """
    Lightweight probe to ensure URL responds and content-type is present.
    Try HEAD first, otherwise small-range GET. Returns (ok, content_type).
    """
    try:
        sess = await _ensure_aio_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        # HEAD
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400:
                    return True, r.headers.get("Content-Type", "")
        except Exception:
            # fallback to small GET range
            try:
                async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                    if r2.status in (200, 206):
                        return True, r2.headers.get("Content-Type", "")
            except Exception:
                return False, None
    except Exception:
        return False, None
    return False, None

# Safety helper: safe dict access
def _safe_get(d: dict, *keys, default=None):
    try:
        v = d
        for k in keys:
            v = v.get(k, {})
        return v or default
    except Exception:
        return default

# ---------------- YouTubeAPI class ----------------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self._url_re = re.compile(r"(?:youtube\.com|youtu\.be)")
        self.pool = _pool
        self.ytdl_sema = _ytdlp_semaphore
        self.cookie = get_cookie_file()

    # ----- extract URL from a Pyrogram Message -----
    async def url(self, message: Message) -> Optional[str]:
        if not message:
            return None
        msgs = [message]
        if getattr(message, "reply_to_message", None):
            msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    if ent.type == MessageEntityType.URL:
                        return text[ent.offset: ent.offset + ent.length].split("&si")[0]
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url.split("&si")[0]
                except Exception:
                    continue
        return None

    # ----- track/details (cache-friendly) -----
    async def track(self, link: str, videoid: Union[bool, str] = None) -> Tuple[Dict, str]:
        prepared = _normalize_link(link, videoid)
        key = _now_key(prepared)
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < YOUTUBE_META_TTL:
                    return data, vid
                _meta_cache.pop(key, None)

        # try youtubesearchpython first (fast)
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

        # fallback to yt-dlp --dump-json (rare)
        cookie = self.cookie
        cmd = ["yt-dlp"]
        if cookie:
            cmd += ["--cookies", cookie]
        cmd += ["--dump-json", prepared]
        out, err = await _exec_proc(*cmd, timeout=15)
        if out:
            try:
                info = json.loads(out.decode(errors="ignore"))
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", "") or "",
                    "link": info.get("webpage_url", prepared) or prepared,
                    "vidid": info.get("id", "") or "",
                    "duration_min": info.get("duration"),
                    "thumb": thumb,
                    "cookiefile": cookie,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except Exception:
                pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": cookie}, ""

    async def details(self, link: str, videoid: Union[bool, str] = None) -> Tuple[str, Optional[str], int, str, str]:
        d, vid = await self.track(link, videoid)
        if vid == "":
            raise ValueError("Video not found")
        dur = d.get("duration_min")
        sec = int(_to_seconds(dur)) if dur else 0
        return d.get("title", ""), dur, sec, d.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("title", "")

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url:
            return None
        try:
            sess = await _ensure_aio_session()
            async with sess.get(url, timeout=20) as resp:
                if resp.status == 200:
                    path = os.path.join(DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception:
            return None
        return None

    # return ffmpeg input args recommended for low-latency streaming
    def ffmpeg_stream_args(self) -> List[str]:
        return [
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-fflags", "+nobuffer",
            "-flags", "low_delay",
            "-probesize", "32",
            "-analyzeduration", "0",
        ]

    # formats (yt-dlp extract_info)
    async def formats(self, link: str, videoid: Union[bool, str] = None) -> Tuple[List[Dict], str]:
        prepared = link if not videoid else (self.base + str(videoid))
        ytdl_opts = {"quiet": True}
        if cf := get_cookie_file():
            ytdl_opts["cookiefile"] = cf
        out: List[Dict] = []
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

    # ---------- core fast resolver ----------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = False) -> Optional[str]:
        """
        Public entry (compat). Returns direct HTTP/HTTPS streaming URL or None.
        For audio streaming set prefer_audio=True.
        """
        return await self.get_direct(link, prefer_audio=prefer_audio)

    async def get_direct(self, link: str, prefer_audio: bool = True) -> Optional[str]:
        """
        Full featured fast resolver:
         - checks in-memory cache (respect expiry),
         - uses yt-dlp Python API in a limited semaphore+threadpool,
         - picks best progressive HTTP/HTTPS/m3u8 candidate suitable for PyTgCalls,
         - probes candidate with HEAD/small GET,
         - caches result until expiry.
        """
        prepared = _normalize_link(link)
        if not prepared:
            return None

        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1) cache hit
        async with _direct_cache_lock:
            ent = _direct_url_cache.get(key)
            if ent:
                expiry, cached_url = ent
                if expiry > now + 5:
                    log.debug("direct cache hit for %s", key)
                    return cached_url
                else:
                    _direct_url_cache.pop(key, None)

        # 2) extractor via yt-dlp API (bounded)
        async with self.ytdl_sema:
            loop = asyncio.get_running_loop()

            def _extract():
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    # prefer http progressive formats to avoid DASH complexities:
                    "format": ("bestaudio[protocol^=http]/bestaudio" if prefer_audio else "best[protocol^=http]/best"),
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    "extractor_args": {"youtube": {"player_client": ["web"], "player_skip": ["android", "android_tv", "ios"]}},
                }
                if self.cookie:
                    opts["cookiefile"] = self.cookie
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        return info
                except Exception as e:
                    return {"_err": str(e)}

            info = await loop.run_in_executor(self.pool, _extract)

        # 3) if extractor failed -> last-resort subprocess -g
        if not info or (isinstance(info, dict) and info.get("_err")):
            log.debug("yt-dlp API extractor failed for %s: %s", prepared, info.get("_err") if isinstance(info, dict) else repr(info))
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4"]
                if self.cookie:
                    cmd += ["--cookies", self.cookie]
                if prefer_audio:
                    cmd += ["-f", "bestaudio[ext=m4a]/bestaudio"]
                else:
                    cmd += ["-f", "best[ext=mp4]/best"]
                cmd += ["--extractor-args", "youtube:player_client=web", prepared]
                out, err = await _exec_proc(*cmd, timeout=8)
                if out:
                    candidate = out.decode().splitlines()[0].strip()
                    ok, ctype = await _probe_url(candidate)
                    if ok:
                        expiry = _parse_expiry_from_url(candidate) or (now + CACHE_DEFAULT_TTL)
                        expiry = int(expiry) - 6
                        async with _direct_cache_lock:
                            _direct_url_cache[key] = (expiry, candidate)
                        return candidate
            except Exception as e:
                log.debug("subprocess -g fallback failed: %s", e)
            return None

        # 4) select best candidate from info
        fmts = info.get("formats") or []
        best_fmt = None
        best_score = -10**9

        def score_format(f):
            s = 0
            proto = (f.get("protocol") or "").lower()
            ext = (f.get("ext") or "").lower()
            vcodec = f.get("vcodec") or ""
            acodec = f.get("acodec") or ""
            if proto.startswith("https"): s += 30
            if proto.startswith("http"): s += 20
            if vcodec and vcodec != "none" and acodec and acodec != "none": s += 50
            if prefer_audio and acodec and acodec != "none": s += 15
            if ext in ("mp4",): s += 10
            if ext in ("m4a", "webm"): s += 8
            try:
                br = int(f.get("tbr") or f.get("abr") or 0)
                s += br // 100
            except Exception:
                pass
            return s

        for f in fmts:
            url = f.get("url")
            if not url:
                continue
            proto = (f.get("protocol") or "").lower()
            # accept HTTP/HTTPS and HLS (m3u8)
            if not proto.startswith(("http", "https", "m3u8")):
                continue
            # audio requirement
            if prefer_audio and (f.get("acodec") or "") == "none":
                continue
            # video requirement - prefer muxed, but allow audio fallback if necessary
            if not prefer_audio and (f.get("vcodec") or "") == "none" and (f.get("acodec") or "") == "none":
                continue
            sc = score_format(f)
            if sc > best_score:
                best_score = sc
                best_fmt = f

        if not best_fmt:
            log.debug("No usable format selected for %s", prepared)
            return None

        candidate_url = best_fmt.get("url")
        ok, ctype = await _probe_url(candidate_url)
        if not ok:
            # try other candidates quick-scan
            for f in fmts:
                url = f.get("url")
                if not url or url == candidate_url:
                    continue
                ok2, ctype2 = await _probe_url(url)
                if ok2:
                    candidate_url = url
                    ok = True
                    ctype = ctype2
                    break

        if not ok:
            log.debug("All probes failed for %s", prepared)
            return None

        expiry = _parse_expiry_from_url(candidate_url) or (now + CACHE_DEFAULT_TTL)
        expiry = int(expiry) - 6

        async with _direct_cache_lock:
            _direct_url_cache[key] = (expiry, candidate_url)

        log.debug("Resolved direct %s -> %s (expiry=%s,ctype=%s)", prepared, candidate_url, expiry, ctype)
        return candidate_url

    # ---------- background downloader (blocking) ----------
    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            ydl_opts = {
                "format": fmt,
                "outtmpl": out_template,
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "force_ipv4": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
                "prefer_ffmpeg": True,
                "writethumbnail": True,
                "addmetadata": True,
            }
            if not is_video:
                ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception as e:
            log.warning("background cache failed: %s", e)

    # ---------- download primary ----------
    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        """
        Return (path_or_direct_url_or_None, is_direct_flag)
        is_direct_flag True => returned value is a direct HTTP stream URL (suitable for PyTgCalls)
        """
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        # compute vid (safe)
        try:
            if videoid:
                vid = str(videoid)
            elif "v=" in prepared:
                vid = prepared.split("v=")[1].split("&")[0]
            elif "youtu.be/" in prepared:
                vid = prepared.split("youtu.be/")[1].split("?")[0]
            else:
                vid = str(int(time.time()))
        except Exception:
            vid = str(int(time.time()))

        ram_base = os.path.join(DOWNLOAD_PATH, vid)

        # 1) check RAM cache
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            try:
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False
            except Exception:
                continue

        loop = asyncio.get_running_loop()

        # 2) format_id specific download
        if format_id:
            def _specific():
                try:
                    aria2_args = ["-x", "16", "-k", "1M", "--disable-ipv6=true"]
                    opts = {
                        "format": (f"{format_id}+140" if songvideo else format_id),
                        "outtmpl": f"{ram_base}.%(ext)s",
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "force_ipv4": True,
                        "extractor_args": {"youtube": {"player_client": ["web"]}},
                        "external_downloader": "aria2c",
                        "external_downloader_args": aria2_args,
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
                            if os.path.exists(p):
                                return p
                        return path
                except Exception:
                    return None
            res = await loop.run_in_executor(self.pool, _specific)
            return (res, False) if res else (None, False)

        # 3) try fast direct URL
        try:
            direct = await self.get_direct(link, prefer_audio=not is_video)
        except Exception as e:
            log.debug("get_direct exception: %s", e)
            direct = None

        if direct:
            # schedule background cache after short delay (non-blocking)
            def _delayed_cache():
                try:
                    time.sleep(6)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True

        # 4) fallback: download to RAM immediately
        def _fallback():
            try:
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "force_ipv4": True,
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                    "prefer_ffmpeg": True,
                }
                if not is_video:
                    ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "192"}]
                else:
                    ydl_opts["merge_output_format"] = "mp4"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    if not is_video and not path.endswith(".mp3"):
                        mp3 = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3):
                            return mp3
                    return path
            except Exception as e:
                log.warning("fallback download failed: %s", e)
                return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded):
            return downloaded, False

        return None, False

    # playlist & slider helpers
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try:
            result = [key for key in out.decode().split("\n") if key]
        except Exception:
            result = []
        return result

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        try:
            a = VideosSearch(link, limit=5)
            res = await a.next()
            if not res or not res.get("result"):
                return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]
        except Exception:
            return "Error", "0", "", "error"

# exported instance
YouTube = YouTubeAPI()
