# file: AnnieXMedia/platforms/Youtube.py
# Robust YouTube resolver for AnnieXMedia
# - retries with EJS remote-components when signature/n-challenge appear
# - prefers fast audio direct links as fallback
# - probe URLs before returning to avoid NoVideoSourceFound
# Requirements: python3.8+, yt-dlp, aiohttp recommended. Optional: orjson, curl_cffi

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

# Optional faster JSON parser
try:
    import orjson as _orjson  # type: ignore
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# Tunables
MAX_YTDLP_THREADS = 12
MAX_CONCURRENT_EXTRACTS = 4
YTDLP_SOCKET_TIMEOUT = 6
PROBE_TIMEOUT = 1.2
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 64
META_CACHE_TTL = 3600

# Pools & caches
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False)
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
    if ext in ("m4a", "webm"): score += 8
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
        # impersonation detection (curl_cffi)
        try:
            import curl_cffi  # type: ignore
            self.impersonate = True
        except Exception:
            self.impersonate = False

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
        # fast attempt with youtubesearchpython (if present)
        try:
            from youtubesearchpython.aio import VideosSearch
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
        # fallback: yt-dlp dump-json (try with remote-components if needed)
        out, err = await _exec_proc("yt-dlp", "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT), timeout=10)
        if out:
            try:
                info = _loads_bytes(out)
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", "") or "",
                    "link": info.get("webpage_url", prepared) or prepared,
                    "vidid": info.get("id", "") or "",
                    "duration_min": info.get("duration"),
                    "thumb": thumb,
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except Exception:
                log.debug("dump-json parse failed, stderr: %s", (err.decode() if err else ""))
        # try again with remote-components if initial failed and deno/npm might be required
        out2, err2 = await _exec_proc("yt-dlp", "--dump-json", prepared, "--remote-components", "ejs:github", "--no-warnings", timeout=12)
        if out2:
            try:
                info = _loads_bytes(out2)
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", "") or "",
                    "link": info.get("webpage_url", prepared) or prepared,
                    "vidid": info.get("id", "") or "",
                    "duration_min": info.get("duration"),
                    "thumb": thumb,
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except Exception:
                log.debug("remote dump-json parse failed, stderr: %s", (err2.decode() if err2 else ""))
        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": self.cookie}, ""

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared:
            return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())
        # cache
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3:
                    return url
                else:
                    _direct_cache.pop(key, None)
        # extraction with yt-dlp API in threadpool guarded by semaphore
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_blocking():
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    # prefer android client for faster un-throttled links
                    "extractor_args": {"youtube": {"player_client": ["android","web"], "player_skip": ["webpage","configs"]}},
                }
                if self.cookie:
                    opts["cookiefile"] = self.cookie
                if self.impersonate:
                    opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except Exception as e:
                    return {"_err": str(e)}
            info = await loop.run_in_executor(self.pool, _extract_blocking)
        # If API failed or returned signature/n warnings => try subprocess fallbacks
        if not info or (isinstance(info, dict) and info.get("_err")):
            log.debug("API failed; trying subprocess fallbacks for %s", prepared)
            # 1) try -g simple (fast)
            cmd_base = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", prepared]
            if self.cookie:
                cmd_base = ["yt-dlp", "-g", "--cookies", self.cookie, "--no-warnings", "--force-ipv4", prepared]
            out, err = await _exec_proc(*cmd_base, timeout=8)
            if out:
                cand = out.decode().splitlines()[0].strip()
                ok, _ = await _probe_url(cand)
                if ok:
                    expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                    expiry = int(expiry) - 3
                    async with _direct_cache_lock:
                        _direct_cache[key] = (expiry, cand)
                    return cand
            # 2) try -g with remote-components (EJS)
            cmd_ejs = ["yt-dlp", "-g", "--remote-components", "ejs:github", "--no-warnings", "--force-ipv4", prepared]
            if self.cookie:
                cmd_ejs = ["yt-dlp", "-g", "--cookies", self.cookie, "--remote-components", "ejs:github", "--no-warnings", "--force-ipv4", prepared]
            out2, err2 = await _exec_proc(*cmd_ejs, timeout=12)
            if out2:
                cand = out2.decode().splitlines()[0].strip()
                ok, _ = await _probe_url(cand)
                if ok:
                    expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                    expiry = int(expiry) - 3
                    async with _direct_cache_lock:
                        _direct_cache[key] = (expiry, cand)
                    return cand
            # give up here
            return None
        # From API info -> select formats
        fmts: List[dict] = info.get("formats") or []
        # If formats list empty -> maybe only images or signature problems; try subprocess dump-json w/ remote
        if not fmts:
            log.debug("No formats from api for %s, trying dump-json remote-components", prepared)
            out3, err3 = await _exec_proc("yt-dlp", "--dump-json", prepared, "--no-warnings", "--remote-components", "ejs:github", timeout=12)
            if out3:
                try:
                    j = _loads_bytes(out3)
                    fmts = j.get("formats") or []
                except Exception:
                    fmts = []
        # Quick top-level url check
        top_url = info.get("url")
        if top_url:
            ok, _ = await _probe_url(top_url)
            if ok:
                expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, top_url)
                return top_url
        # Score candidate formats
        candidates: List[Tuple[int,str]] = []
        for f in fmts:
            url = f.get("url")
            if not url:
                continue
            proto = (f.get("protocol") or "").lower()
            if not proto.startswith(("http","https","m3u8")):
                continue
            # skip audio-less when prefer audio
            if prefer_audio and (f.get("acodec") or "") == "none":
                continue
            # if requesting video prefer muxed
            if not prefer_audio and (f.get("vcodec") or "") != "none" and (f.get("acodec") or "") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if (f.get("acodec") or "") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if proto.startswith("m3u8"):
                candidates.append((40, url))
        candidates.sort(key=lambda x: x[0], reverse=True)
        # probe top candidates
        tries = 0
        for _score, cand in candidates:
            if tries >= 4:
                break
            tries += 1
            ok, _ = await _probe_url(cand)
            if ok:
                expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, cand)
                return cand
        # fallback to audio if not already audio
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
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        # vid id for file names
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
        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)
        # 1) RAM cache
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            try:
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False
            except Exception:
                continue
        # 2) format id specific
        if format_id:
            def _specific():
                try:
                    opts = {
                        "format": (f"{format_id}+140" if songvideo else format_id),
                        "outtmpl": f"{ram_base}.%(ext)s",
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "force_ipv4": True,
                        "extractor_args": {"youtube": {"player_client": ["web"]}},
                    }
                    if songaudio:
                        opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
                    if songvideo:
                        opts["merge_output_format"] = "mp4"
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=True)
                        path = ydl.prepare_filename(info)
                        if songaudio and not path.endswith(".mp3"):
                            p = os.path.splitext(path)[0] + ".mp3"
                            if os.path.exists(p): return p
                        return path
                except Exception as e:
                    log.warning("specific download failed: %s", e)
                    return None
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(self.pool, _specific)
            return (res, False) if res else (None, False)
        # 3) try direct fast-path
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception as e:
            log.debug("get_direct_link err: %s", e)
            direct = None
        if direct:
            # schedule background cache
            def _delayed_cache():
                try:
                    time.sleep(6)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop = asyncio.get_running_loop()
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True
        # 4) fallback full download
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
                    ydl_opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
                else:
                    ydl_opts["merge_output_format"] = "mp4"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    if not is_video and not path.endswith(".mp3"):
                        mp3 = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3): return mp3
                    return path
            except Exception as e:
                log.warning("fallback download failed: %s", e)
                return None
        loop = asyncio.get_running_loop()
        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded):
            return downloaded, False
        return None, False

    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x","16","-s","16","-j","16","-k","1M","--file-allocation=none","--disable-ipv6=true"]
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
                ydl_opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
            else:
                ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception as e:
            log.warning("background cache failed: %s", e)

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        cmd = (f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
               f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null")
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try:
            result = [k for k in out.decode().split("\n") if k]
        except Exception:
            result = []
        return result

YouTube = YouTubeAPI()
