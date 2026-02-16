# file: AnnieXMedia/platforms/Youtube.py
# AnnieXMedia YouTube resolver (2026)
# Primary: py-yt-search (py_yt) for async search & metadata
# Fallbacks & heavy lifting: yt-dlp (fast and reliable)
# Uses aiohttp, orjson, curl_cffi (if available) for speed/impersonation

import asyncio
import contextlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

# Networking & performance
import aiohttp
# optional speedups / libs — imported lazily below where used
# Parsing / json
try:
    import orjson as _orjson  # type: ignore
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

# Main fallback extractor
import yt_dlp

# Threadpool config
MAX_YTDLP_THREADS = 16
MAX_CONCURRENT_EXTRACTS = 6
YTDLP_SOCKET_TIMEOUT = 8
PROBE_TIMEOUT = 1.2
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 128
META_CACHE_TTL = 3600

# Threadpool / semaphores / caches
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

# aiohttp session & connector (keepalive, speedups if installed)
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {}   # key -> (expiry_epoch, url)
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

# cookie search paths (project)
COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

# try to detect impersonation support
_impersonate_available = False
try:
    import curl_cffi  # type: ignore
    _impersonate_available = True
except Exception:
    _impersonate_available = False

# Optional uvloop usage (do not force if user already manages event loop)
try:
    import uvloop  # type: ignore
    _uvloop_available = True
except Exception:
    _uvloop_available = False

# Helper: find cookie file
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
    """Run subprocess (async) and return (stdout, stderr)."""
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
    """
    Quick HEAD then small-range GET probe to validate URL. Returns (ok, content_type).
    """
    try:
        sess = await _ensure_aio_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        # HEAD first
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400:
                    return True, r.headers.get("Content-Type")
        except Exception:
            # fallback to range GET
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

# Logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        self.impersonate = _impersonate_available

    # -------------------------
    # Primary: py_yt integrations
    # -------------------------
    async def _pyyt_videos_search(self, query: str, limit: int = 10, language: Optional[str] = None, region: Optional[str] = None):
        """Use py_yt.VideosSearch if available. Returns list of items or empty."""
        try:
            from py_yt import VideosSearch  # type: ignore
            vs = VideosSearch(query, limit=limit, language=language or "en", region=region or "US")
            res = await vs.next()
            return res.get("result") or []
        except Exception as e:
            log.debug("py_yt VideosSearch error: %s", e)
            return []

    async def _pyyt_video_get(self, video_id: str):
        """Use py_yt.Video.get if available. Returns dict or None"""
        try:
            from py_yt import Video  # type: ignore
            v = await Video.get(video_id)
            return v or None
        except Exception as e:
            log.debug("py_yt Video.get error: %s", e)
            return None

    async def search(self, query: str, limit: int = 10, language: Optional[str] = None, region: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Return list of dicts: {title, vidid, duration, link}
        Prefer py_yt search; fallback to yt-dlp ytsearch if needed.
        """
        results: List[Dict[str,str]] = []

        # try py_yt first (async)
        try:
            items = await self._pyyt_videos_search(query, limit=limit, language=language, region=region)
            for it in items:
                vid = it.get("id") or it.get("videoId") or ""
                title = it.get("title") or "Unknown"
                dur = it.get("duration") or it.get("duration_raw") or ""
                link = it.get("link") or (self.base + vid if vid else "")
                results.append({"title": title, "vidid": vid or "", "duration": dur or "", "link": link})
            if results:
                return results
        except Exception:
            pass

        # fallback: yt-dlp subprocess search
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                f"ytsearch{limit}:{query}",
                "--flat-playlist",
                "--no-warnings",
                "--skip-download",
            ]
            if self.cookie:
                cmd.insert(1, "--cookies")
                cmd.insert(2, self.cookie)

            out, _ = await _exec_proc(*cmd, timeout=12)
            if out:
                for line in out.decode().splitlines():
                    try:
                        data = _loads_bytes(line.encode())
                        vid = data.get("id", "")
                        results.append({
                            "title": data.get("title", "Unknown"),
                            "vidid": vid,
                            "duration": data.get("duration_string", ""),
                            "link": data.get("webpage_url") or (self.base + vid if vid else "")
                        })
                    except Exception:
                        continue
        except Exception as e:
            log.debug("yt-dlp search fallback failed: %s", e)

        return results

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        """
        Get metadata (cached) + vidid.
        Prefer py_yt.Video.get when possible; fallback to yt-dlp.
        """
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL:
                    return data, vid
                _meta_cache.pop(key, None)

        # try py_yt fast path
        try:
            # if a video id is present, use Video.get
            vid_candidate = ""
            if "v=" in prepared:
                vid_candidate = prepared.split("v=")[1].split("&")[0]
            elif "youtu.be/" in prepared:
                vid_candidate = prepared.split("youtu.be/")[1].split("?")[0]

            if vid_candidate:
                vinfo = await self._pyyt_video_get(vid_candidate)
                if vinfo:
                    # py_yt returns thumbnails list or thumbnail url
                    thumbs = vinfo.get("thumbnails") or vinfo.get("thumbnail") or []
                    thumb = ""
                    if isinstance(thumbs, list) and thumbs:
                        t = thumbs[-1]
                        thumb = t.get("url") if isinstance(t, dict) else str(t)
                    elif isinstance(thumbs, str):
                        thumb = thumbs
                    details = {
                        "title": vinfo.get("title", "") or "",
                        "link": vinfo.get("link", prepared) or prepared,
                        "vidid": vinfo.get("id", vid_candidate) or vid_candidate,
                        "duration_min": vinfo.get("duration") or vinfo.get("length"),
                        "thumb": (thumb.split("?")[0] if thumb else ""),
                        "cookiefile": self.cookie,
                    }
                    async with _meta_cache_lock:
                        _meta_cache[key] = (now, details, details.get("vidid", ""))
                    return details, details.get("vidid", "")
            # otherwise try search with py_yt
            items = await self._pyyt_videos_search(prepared, limit=1)
            if items:
                d = items[0]
                thumb = (d.get("thumbnails") or [{}])[-1].get("url", "") if isinstance(d.get("thumbnails", None), list) else d.get("thumbnail", "")
                details = {
                    "title": d.get("title", "") or "",
                    "link": d.get("link", prepared) or prepared,
                    "vidid": d.get("id", "") or "",
                    "duration_min": d.get("duration"),
                    "thumb": (thumb.split("?")[0] if thumb else ""),
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock:
                    _meta_cache[key] = (now, details, details.get("vidid", ""))
                return details, details.get("vidid", "")
        except Exception as e:
            log.debug("py_yt fast path failed: %s", e)

        # fallback: yt-dlp dump-json
        cmd = ["yt-dlp", "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        if self.cookie:
            cmd = ["yt-dlp", "--cookies", self.cookie, "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        out, err = await _exec_proc(*cmd, timeout=12)
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
                log.debug("dump-json parse failed; stderr=%s", (err.decode() if err else ""))

        # another fallback: remote components
        cmd2 = ["yt-dlp", "--remote-components", "ejs:github", "--dump-json", prepared, "--no-warnings"]
        if self.cookie:
            cmd2 = ["yt-dlp", "--cookies", self.cookie, "--remote-components", "ejs:github", "--dump-json", prepared, "--no-warnings"]
        out2, err2 = await _exec_proc(*cmd2, timeout=16)
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
                log.debug("remote dump-json parse failed; stderr=%s", (err2.decode() if err2 else ""))

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
        """Download thumbnail to local downloads/ and return path."""
        if not url:
            return None
        try:
            base_dir = "downloads"
            if not os.path.exists(base_dir):
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
            log.warning("download_thumb failed: %s", e)
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t:
            return 0
        try:
            if isinstance(t, int):
                return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts:
                s = s * 60 + p
            return s
        except Exception:
            try:
                return int(float(t))
            except Exception:
                return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        """
        Return list of formats (dicts). Uses yt-dlp API (blocking) because format discovery is heavy.
        """
        prepared = _normalize_link(link, videoid)
        out: List[Dict[str, Any]] = []
        try:
            # use yt-dlp API in threadpool
            loop = asyncio.get_running_loop()
            def _blocking():
                try:
                    opts = {"quiet": True}
                    if cf := get_cookie_file():
                        opts["cookiefile"] = cf
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        return info.get("formats", [])
                except Exception as e:
                    log.debug("formats blocking error: %s", e)
                    return []
            fmts = await loop.run_in_executor(self.pool, _blocking)
            for fmt in fmts:
                fs = fmt.get("filesize") or fmt.get("filesize_approx")
                out.append({
                    "format": fmt.get("format"),
                    "filesize": fs,
                    "format_id": str(fmt.get("format_id")),
                    "ext": fmt.get("ext"),
                    "format_note": fmt.get("format_note", ""),
                    "vcodec": fmt.get("vcodec"),
                    "acodec": fmt.get("acodec"),
                })
        except Exception as e:
            log.debug("formats() failed: %s", e)
        return out, prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        """
        Attempt to return a direct playable URL quickly.
        Strategy:
          1) Check cache
          2) Try yt-dlp python API in threadpool
          3) Fallback to `yt-dlp -g` subprocess (and remote-components)
          4) Probe candidates and cache expiry
        """
        prepared = _normalize_link(link)
        if not prepared:
            return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3:
                    return url
                else:
                    _direct_cache.pop(key, None)

        # use yt-dlp python API inside threadpool guarded by semaphore
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract():
                try:
                    opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "noplaylist": True,
                        "skip_download": True,
                        "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                        "extractor_args": {"youtube": {"player_client": ["android", "web"], "player_skip": ["webpage", "configs"]}},
                    }
                    if self.cookie:
                        opts["cookiefile"] = self.cookie
                    if self.impersonate:
                        opts["impersonate"] = "chrome"
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except Exception as e:
                    return {"_err": str(e)}
            info = await loop.run_in_executor(self.pool, _extract)

        # if API failed -> fallback to subprocess -g
        if not info or (isinstance(info, dict) and info.get("_err")):
            # try -g plain
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", prepared]
                if self.cookie:
                    cmd = ["yt-dlp", "-g", "--cookies", self.cookie, "--no-warnings", "--force-ipv4", prepared]
                out, _ = await _exec_proc(*cmd, timeout=8)
                if out:
                    cand = out.decode().splitlines()[0].strip()
                    ok, _ctype = await _probe_url(cand)
                    if ok:
                        expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                        expiry = int(expiry) - 3
                        async with _direct_cache_lock:
                            _direct_cache[key] = (expiry, cand)
                        return cand
            except Exception:
                pass
            # try -g with remote-components
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--remote-components", "ejs:github", "--force-ipv4", prepared]
                if self.cookie:
                    cmd = ["yt-dlp", "-g", "--cookies", self.cookie, "--remote-components", "ejs:github", "--no-warnings", "--force-ipv4", prepared]
                out2, _ = await _exec_proc(*cmd, timeout=14)
                if out2:
                    cand = out2.decode().splitlines()[0].strip()
                    ok, _ctype = await _probe_url(cand)
                    if ok:
                        expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                        expiry = int(expiry) - 3
                        async with _direct_cache_lock:
                            _direct_cache[key] = (expiry, cand)
                        return cand
            except Exception:
                pass
            return None

        # parse info
        fmts: List[dict] = info.get("formats") or []

        # try top-level url
        top_url = info.get("url")
        if top_url:
            ok, _ = await _probe_url(top_url)
            if ok:
                expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, top_url)
                return top_url

        # if no formats, attempt dump-json remote
        if not fmts:
            try:
                cmd = ["yt-dlp", "--dump-json", prepared, "--remote-components", "ejs:github", "--no-warnings"]
                if self.cookie:
                    cmd = ["yt-dlp", "--cookies", self.cookie, "--dump-json", prepared, "--remote-components", "ejs:github", "--no-warnings"]
                out3, _ = await _exec_proc(*cmd, timeout=16)
                if out3:
                    j = _loads_bytes(out3)
                    fmts = j.get("formats") or []
            except Exception:
                fmts = []

        # score candidates
        candidates: List[Tuple[int, str]] = []
        for f in fmts:
            url = f.get("url")
            if not url:
                continue
            proto = (f.get("protocol") or "").lower()
            if not proto.startswith(("http", "https", "m3u8")):
                continue
            if prefer_audio and (f.get("acodec") or "") == "none":
                continue
            if not prefer_audio and (f.get("vcodec") or "") != "none" and (f.get("acodec") or "") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if (f.get("acodec") or "") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if proto.startswith("m3u8"):
                candidates.append((40, url))

        candidates.sort(key=lambda x: x[0], reverse=True)

        # probe candidates
        tries = 0
        for _score, cand in candidates:
            if tries >= 6:
                break
            tries += 1
            ok, _ctype = await _probe_url(cand)
            if ok:
                expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, cand)
                return cand

        if not prefer_audio:
            return await self.get_direct_link(link, prefer_audio=True)

        return None

    async def download(self,
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
        Return (path_or_direct_url_or_None, is_direct_flag).
        Strategy:
          - check RAM cache
          - try direct link (fast)
          - otherwise download with yt-dlp to RAM (or /dev/shm)
        """
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        # compute vid
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

        # RAM cache check
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            try:
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False
            except Exception:
                continue

        loop = asyncio.get_running_loop()

        # format_id specified: download specific
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
                except Exception as e:
                    log.warning("specific download failed: %s", e)
                    return None
            res = await loop.run_in_executor(self.pool, _specific)
            return (res, False) if res else (None, False)

        # try direct fast-path
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception as e:
            log.debug("get_direct_link err: %s", e)
            direct = None

        if direct:
            # schedule background cache (non-blocking)
            def _delayed_cache():
                try:
                    time.sleep(6)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True

        # fallback: download to RAM immediately
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

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        """
        Return list of video ids from playlist (flat).
        Uses yt-dlp subprocess for speed & reliability.
        """
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

# exported instance
YouTube = YouTubeAPI()
