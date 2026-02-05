# file: AnnieXMedia/platforms/Youtube.py
# AnnieXMedia - Ultra-fast, complete Youtube resolver (2026)
# - yt-dlp Python API inside bounded ThreadPool
# - semaphore to limit concurrent heavy extractions
# - aiohttp tiny HEAD/Range probes for validating direct URLs
# - in-memory cache respecting 'expire' param
# - optional impersonation via curl_cffi if available
# - prefers muxed mp4 for video; falls back to best audio (m4a/webm)
# - safe fallbacks: subprocess -g, format inspection, audio fallback
# - minimal external dependencies at runtime (yt-dlp, aiohttp recommended)

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

# optional fast json loader
try:
    import orjson as _orjson  # type: ignore
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

# logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# ---------- Tunables ----------
MAX_YTDLP_THREADS = 16
MAX_CONCURRENT_EXTRACTS = 6
YTDLP_SOCKET_TIMEOUT = 6        # small socket timeout
PROBE_TIMEOUT = 1.2             # HEAD / small GET probe timeout
CACHE_DEFAULT_TTL = 300         # fallback TTL for direct urls (seconds)
AIO_CONN_LIMIT = 64
META_CACHE_TTL = 3600           # metadata cache TTL

# ---------- Threadpool/semaphore ----------
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

# ---------- aiohttp session (reused) ----------
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False)
_aio_session: Optional[aiohttp.ClientSession] = None

# ---------- Caches ----------
# direct cache: key -> (expiry_epoch, url)
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()

# metadata cache: qkey -> (ts, data, vid)
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

# ---------- Cookie candidates (drop cookies.txt in one of these if needed) ----------
COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "/app/cookies.txt",
    "platforms/cookies.txt",
    "assets/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None

# ---------- Helpers ----------
async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    """
    Run subprocess and wait for communicate with timeout.
    Returns (stdout, stderr) bytes. On timeout returns (b"", b"timeout").
    """
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
    Quick HEAD then small-range GET probe. Short timeouts to favor speed.
    Returns (ok, content_type).
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
            # fallback to small-range GET
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
    """
    Heuristic to rank formats. Higher is better.
    """
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

# ---------- Main API ----------

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        # detect impersonation capability
        try:
            import curl_cffi  # type: ignore
            self.impersonate = True
            log.debug("curl_cffi detected -> impersonation enabled")
        except Exception:
            self.impersonate = False
            log.debug("curl_cffi not present -> impersonation disabled")

    # ----- extract URL from a Pyrogram Message -----
    async def url(self, message) -> Optional[str]:
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
                    # MessageEntityType.URL / TEXT_LINK handling if Pyrogram types present
                    t = getattr(ent, "type", None)
                    if t == "url" or t == getattr(ent, "type", None):
                        # handle offsets if available (older pyrogram may differ)
                        off = getattr(ent, "offset", None)
                        ln = getattr(ent, "length", None)
                        if off is not None and ln is not None:
                            return text[off: off + ln].split("&si")[0]
                    # TEXT_LINK
                    u = getattr(ent, "url", None)
                    if u:
                        return u.split("&si")[0]
                except Exception:
                    continue
        return None

    # ----- meta/track (cached) -----
    async def track(self, link: str, videoid: Union[bool, str] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL:
                    return data, vid
                _meta_cache.pop(key, None)

        # try fast API (youtubesearchpython) if installed (optional)
        try:
            from youtubesearchpython.aio import VideosSearch  # local import optional
            try:
                res = await VideosSearch(prepared, limit=1).next()
                results = res.get("result", [])
            except Exception:
                results = []
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

        # fallback: yt-dlp --dump-json (subprocess) - fast and robust
        cmd = ["yt-dlp"]
        if self.cookie:
            cmd += ["--cookies", self.cookie]
        cmd += ["--dump-json", prepared]
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
                pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": self.cookie}, ""

    # ---------- core fast resolver ----------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        """
        Return a direct playable URL fast (or None).
        prefer_audio=True recommended for PyTgCalls (audio-only).
        """
        prepared = _normalize_link(link)
        if not prepared:
            return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1) fast cache check
        async with _direct_cache_lock:
            ent = _direct_cache.get(key)
            if ent:
                expiry, url = ent
                if expiry > now + 3:
                    log.debug("direct cache hit %s", key)
                    return url
                else:
                    _direct_cache.pop(key, None)

        # 2) use yt-dlp API inside limited semaphore + threadpool
        async with self.sema:
            loop = asyncio.get_running_loop()

            def _extract_info():
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    "extractor_args": {"youtube": {"player_client": ["android", "web"], "player_skip": ["webpage", "configs"]}},
                }
                if self.cookie:
                    ydl_opts["cookiefile"] = self.cookie
                if self.impersonate:
                    ydl_opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except Exception as e:
                    return {"_err": str(e)}

            info = await loop.run_in_executor(self.pool, _extract_info)

        # 3) if API extraction failed, fallback to subprocess -g (very fast)
        if not info or (isinstance(info, dict) and info.get("_err")):
            log.debug("yt-dlp API failed for %s: %s", prepared, info.get("_err") if isinstance(info, dict) else repr(info))
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", prepared]
                if self.cookie:
                    cmd = ["yt-dlp", "-g", "--cookies", self.cookie, "--no-warnings", "--force-ipv4", prepared]
                out, _err = await _exec_proc(*cmd, timeout=8)
                if out:
                    candidate = out.decode().splitlines()[0].strip()
                    ok, _ctype = await _probe_url(candidate)
                    if ok:
                        expiry = _parse_expire(candidate) or (now + CACHE_DEFAULT_TTL)
                        expiry = int(expiry) - 3
                        async with _direct_cache_lock:
                            _direct_cache[key] = (expiry, candidate)
                        return candidate
            except Exception:
                pass
            # no candidate
            return None

        # 4) got info -> choose best format
        fmts: List[dict] = info.get("formats") or []

        # quick path: top-level url sometimes present
        top_url = info.get("url")
        if top_url:
            ok, _ctype = await _probe_url(top_url)
            if ok:
                expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, top_url)
                return top_url

        # build candidate list
        candidates: List[Tuple[int, str]] = []
        for f in fmts:
            url = f.get("url")
            if not url:
                continue
            proto = (f.get("protocol") or "").lower()
            if not proto.startswith(("http", "https", "m3u8")):
                continue
            # skip audio-less if prefer_audio
            if prefer_audio and (f.get("acodec") or "") == "none":
                continue
            # prefer muxed (video+audio) if asking for video
            if not prefer_audio and (f.get("vcodec") or "") != "none" and (f.get("acodec") or "") != "none":
                score = _score_format(f, prefer_audio)
                candidates.append((score, url))
                continue
            # audio candidate
            if (f.get("acodec") or "") != "none":
                score = _score_format(f, prefer_audio)
                candidates.append((score, url))
                continue
            # m3u8 fallback
            if proto.startswith("m3u8"):
                candidates.append((40, url))

        # sort candidates descending
        candidates.sort(key=lambda x: x[0], reverse=True)

        # probe top candidates (limit tries to keep latency low)
        tries = 0
        for _score, cand in candidates:
            if tries >= 4:
                break
            tries += 1
            ok, _ctype = await _probe_url(cand)
            if ok:
                expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, cand)
                return cand

        # 5) last fallback: if video requested, try audio fallback
        if not prefer_audio:
            return await self.get_direct_link(link, prefer_audio=True)

        return None

    # ---------- download fallback (blocking) ----------
    async def download(self, link: str, mystic, video: Union[bool, str] = None, songaudio: Union[bool, str] = None) -> Tuple[Optional[str], bool]:
        is_video = bool(video)
        prepared = _normalize_link(link)
        loop = asyncio.get_running_loop()

        def _dl_blocking():
            fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            opts = {
                "format": fmt,
                "outtmpl": os.path.join("/tmp", "%(id)s.%(ext)s"),
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "force_ipv4": True,
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    return path
            except Exception as e:
                log.warning("fallback download failed: %s", e)
                return None

        path = await loop.run_in_executor(self.pool, _dl_blocking)
        if path and os.path.exists(path):
            return path, False
        return None, False

    # ---------- playlist helper ----------
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
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

# singleton
YouTube = YouTubeAPI()

# ---------------- optional test runner ----------------
if __name__ == "__main__":
    async def main():
        url = "https://www.youtube.com/watch?v=1xsDmAYVlrs"
        start = time.time()
        direct = await YouTube.get_direct_link(url, prefer_audio=True)
        took = (time.time() - start) * 1000
        print("direct:", direct)
        print(f"took {took:.1f} ms")
        # close aio session
        global _aio_session
        if _aio_session and not _aio_session.closed:
            await _aio_session.close()

    asyncio.run(main())
