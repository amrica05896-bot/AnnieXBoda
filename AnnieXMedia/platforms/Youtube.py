# file: AnnieXMedia/platforms/Youtube.py
# Ultra Fast YouTube resolver for AnnieXMedia
# Search/metadata via InnerTube API, optional fallback for direct URLs

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

import aiohttp

try:
    import yt_dlp  # optional fallback for direct link extraction
except Exception:
    yt_dlp = None  # type: ignore


log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# =========================
# Tunables
# =========================
MAX_YTDLP_THREADS = 12
MAX_CONCURRENT_REQUESTS = 12
AIO_CONN_LIMIT = 64
CACHE_TTL_SEARCH = 120
CACHE_TTL_META = 3600
CACHE_TTL_DIRECT = 180
REQUEST_TIMEOUT = 8
PLAYER_TIMEOUT = 8
PROBE_TIMEOUT = 3.0

# =========================
# InnerTube config
# =========================
INNERTUBE_KEY = "AIzaSyA-DEFAULT"
INNERTUBE_CONTEXT = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20260101.00.00",
        "hl": "en",
        "gl": "US",
        "utcOffsetMinutes": 0,
    }
}

SEARCH_URL = "https://www.youtube.com/youtubei/v1/search?key={key}"
PLAYER_URL = "https://www.youtube.com/youtubei/v1/player?key={key}"
BROWSE_URL = "https://www.youtube.com/youtubei/v1/browse?key={key}"

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

# =========================
# Globals
# =========================
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_request_sema = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_search_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_direct_cache: Dict[str, Tuple[int, str]] = {}

_search_lock = asyncio.Lock()
_meta_lock = asyncio.Lock()
_direct_lock = asyncio.Lock()


def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None


async def _ensure_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(
            connector=_aio_connector,
            raise_for_status=False,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        )
    return _aio_session


async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"


def _safe_json_loads(raw: bytes) -> Any:
    try:
        import orjson  # type: ignore

        return orjson.loads(raw)
    except Exception:
        try:
            return json.loads(raw.decode("utf-8", "ignore"))
        except Exception:
            return {}


def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid and str(videoid) not in ("True", "False"):
        return f"https://www.youtube.com/watch?v={videoid}"

    if not link:
        return ""

    link = link.strip()

    if "youtu.be/" in link:
        vid = link.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={vid}"

    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        vid = link.split("/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={vid}"

    return link.split("&")[0]


def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params:
            return int(params["expire"][0])
    except Exception:
        pass
    return None


def _thumbnail_from_id(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _extract_text(obj: Any) -> str:
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        if "simpleText" in obj and isinstance(obj["simpleText"], str):
            return obj["simpleText"]
        runs = obj.get("runs")
        if isinstance(runs, list):
            parts = []
            for r in runs:
                if isinstance(r, dict):
                    t = r.get("text")
                    if isinstance(t, str):
                        parts.append(t)
            return "".join(parts)
    return ""


def _walk_for_key(obj: Any, wanted_keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []

    def rec(x: Any):
        if isinstance(x, dict):
            if any(k in x for k in wanted_keys):
                found.append(x)
            for v in x.values():
                rec(v)
        elif isinstance(x, list):
            for item in x:
                rec(item)

    rec(obj)
    return found


def _extract_video_items(payload: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    candidates = _walk_for_key(payload, ("videoRenderer",))
    for c in candidates:
        vr = c.get("videoRenderer")
        if not isinstance(vr, dict):
            continue

        vid = vr.get("videoId") or ""
        title = _extract_text(vr.get("title"))
        duration = _extract_text(vr.get("lengthText")) or "LIVE" if vr.get("upcomingEventData") else ""
        thumb = ""
        thumbs = vr.get("thumbnail", {}).get("thumbnails", [])
        if isinstance(thumbs, list) and thumbs:
            last = thumbs[-1]
            if isinstance(last, dict):
                thumb = last.get("url", "") or ""

        channel = _extract_text(vr.get("ownerText"))
        views = _extract_text(vr.get("viewCountText"))

        if vid:
            items.append(
                {
                    "title": title or "Unknown",
                    "vidid": str(vid),
                    "duration": duration,
                    "thumb": thumb or _thumbnail_from_id(str(vid)),
                    "channel": channel,
                    "views": views,
                }
            )
    return items


def _pick_stream_url(info: Dict[str, Any], prefer_audio: bool = True) -> Optional[str]:
    streaming = info.get("streamingData") or {}
    formats = []
    if isinstance(streaming, dict):
        for key in ("formats", "adaptiveFormats"):
            val = streaming.get(key)
            if isinstance(val, list):
                formats.extend(val)

    def score(fmt: Dict[str, Any]) -> int:
        s = 0
        mime = str(fmt.get("mimeType", "")).lower()
        if mime.startswith("audio/"):
            s += 50
        if mime.startswith("video/"):
            s += 20
        if "mp4" in mime:
            s += 10
        if "webm" in mime:
            s += 8
        br = fmt.get("bitrate") or 0
        try:
            s += int(br) // 100000
        except Exception:
            pass
        if prefer_audio and mime.startswith("audio/"):
            s += 25
        return s

    # direct url first
    candidates: List[Tuple[int, str]] = []
    for f in formats:
        if not isinstance(f, dict):
            continue
        url = f.get("url")
        if not url:
            continue
        candidates.append((score(f), str(url)))

    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates:
        return candidates[0][1]

    return None


async def _probe_url(url: str, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        sess = await _ensure_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400:
                    return True
        except Exception:
            pass

        try:
            async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                return r2.status in (200, 206)
        except Exception:
            return False
    except Exception:
        return False


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _request_sema
        self.cookie = get_cookie_file()
        self.impersonate = False
        try:
            import curl_cffi  # type: ignore

            self.impersonate = True
        except Exception:
            self.impersonate = False

    async def _post_json(self, url: str, payload: Dict[str, Any], timeout: int = REQUEST_TIMEOUT) -> Dict[str, Any]:
        sess = await _ensure_session()
        async with _request_sema:
            try:
                async with sess.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                ) as r:
                    if r.status >= 400:
                        txt = await r.text()
                        log.debug("POST %s -> %s %s", url, r.status, txt[:500])
                        return {}
                    return await r.json(content_type=None)
            except Exception as e:
                log.debug("POST failed %s: %s", url, e)
                return {}

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
                    t = getattr(ent, "type", None)
                    off = getattr(ent, "offset", None)
                    ln = getattr(ent, "length", None)
                    if t == "url" and off is not None and ln is not None:
                        return text[off : off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u:
                        return str(u).split("&si")[0]
                except Exception:
                    continue
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        now = time.time()
        async with _search_lock:
            cached = _search_cache.get(query)
            if cached and now - cached[0] < CACHE_TTL_SEARCH:
                return cached[1][:limit]

        payload = {
            "context": INNERTUBE_CONTEXT,
            "query": query,
        }

        data = await self._post_json(SEARCH_URL.format(key=INNERTUBE_KEY), payload, timeout=REQUEST_TIMEOUT)
        results = _extract_video_items(data) if data else []

        # fallback: lightweight yt-dlp search only if InnerTube returned nothing
        if not results:
            try:
                cmd = [
                    "yt-dlp",
                    "--dump-single-json",
                    f"ytsearch{limit}:{query}",
                    "--flat-playlist",
                    "--no-warnings",
                    "--skip-download",
                ]
                if self.cookie:
                    cmd.insert(1, "--cookies")
                    cmd.insert(2, self.cookie)
                out, _ = await _exec_proc(*cmd, timeout=10)
                if out:
                    raw = _safe_json_loads(out)
                    if isinstance(raw, dict):
                        entries = raw.get("entries") or []
                        for e in entries:
                            if not isinstance(e, dict):
                                continue
                            vid = e.get("id") or ""
                            if vid:
                                results.append(
                                    {
                                        "title": e.get("title", "Unknown"),
                                        "vidid": str(vid),
                                        "duration": e.get("duration_string", "") or e.get("duration", ""),
                                        "thumb": e.get("thumbnail", "") or _thumbnail_from_id(str(vid)),
                                    }
                                )
            except Exception:
                pass

        results = results[:limit]
        async with _search_lock:
            _search_cache[query] = (now, results)
        return results

    async def slider(self, query: str, query_type: int) -> Tuple[str, str, str, str]:
        results = await self.search(query, limit=10)
        if not results:
            raise ValueError("No results found")

        idx = query_type % len(results)
        item = results[idx]
        vid = str(item.get("vidid", "") or "")
        d, _ = await self.track(vid, videoid=vid)
        return (
            d.get("title", "Unknown"),
            str(d.get("duration_min", "00:00")),
            d.get("thumb", "") or _thumbnail_from_id(vid),
            vid,
        )

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "m:" + (videoid if isinstance(videoid, str) and videoid else prepared)
        now = time.time()

        async with _meta_lock:
            cached = _meta_cache.get(key)
            if cached and now - cached[0] < CACHE_TTL_META:
                return cached[1], cached[2]

        vid = ""
        if videoid and str(videoid) not in ("True", "False"):
            vid = str(videoid)
        else:
            m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", prepared)
            if m:
                vid = m.group(1)
            else:
                m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", prepared)
                if m:
                    vid = m.group(1)
                else:
                    m = re.search(r"youtube\.com/(?:shorts|live)/([A-Za-z0-9_-]{6,})", prepared)
                    if m:
                        vid = m.group(1)

        # InnerTube player
        if vid:
            payload = {
                "context": INNERTUBE_CONTEXT,
                "videoId": vid,
                "contentCheckOk": True,
                "racyCheckOk": True,
            }
            data = await self._post_json(PLAYER_URL.format(key=INNERTUBE_KEY), payload, timeout=PLAYER_TIMEOUT)
            if data:
                details = data.get("videoDetails") or {}
                micro = data.get("microformat", {}).get("playerMicroformatRenderer", {}) if isinstance(data.get("microformat"), dict) else {}

                title = details.get("title") or ""
                thumb = _thumbnail_from_id(vid)
                thumbs = (
                    micro.get("thumbnail", {})
                    .get("thumbnails", [])
                    if isinstance(micro, dict)
                    else []
                )
                if isinstance(thumbs, list) and thumbs:
                    last = thumbs[-1]
                    if isinstance(last, dict):
                        thumb = last.get("url", thumb) or thumb

                duration_min = details.get("lengthSeconds") or micro.get("lengthSeconds") or None
                if isinstance(duration_min, str) and duration_min.isdigit():
                    duration_min = int(duration_min)

                result = {
                    "title": title,
                    "link": prepared if prepared else self.base + vid,
                    "vidid": vid,
                    "duration_min": duration_min,
                    "thumb": thumb,
                    "cookiefile": self.cookie,
                }

                async with _meta_lock:
                    _meta_cache[key] = (now, result, vid)
                return result, vid

        # fallback to yt-dlp if no video id or player failed
        if yt_dlp is not None and prepared:
            def _extract():
                try:
                    opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "noplaylist": True,
                        "skip_download": True,
                        "socket_timeout": REQUEST_TIMEOUT,
                    }
                    if self.cookie:
                        opts["cookiefile"] = self.cookie
                    if self.impersonate:
                        opts["impersonate"] = "chrome"
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except Exception as e:
                    return {"_err": str(e)}

            info = await asyncio.get_running_loop().run_in_executor(self.pool, _extract)
            if isinstance(info, dict) and not info.get("_err"):
                vid2 = str(info.get("id", "") or "")
                if vid2 in ("True", "False"):
                    vid2 = ""
                result = {
                    "title": info.get("title", "") or "",
                    "link": info.get("webpage_url", prepared) or prepared,
                    "vidid": vid2,
                    "duration_min": info.get("duration"),
                    "thumb": (info.get("thumbnail") or "").split("?")[0] or (vid2 and _thumbnail_from_id(vid2) or ""),
                    "cookiefile": self.cookie,
                }
                async with _meta_lock:
                    _meta_cache[key] = (now, result, vid2)
                return result, vid2

        empty = {
            "title": "Unknown",
            "link": prepared,
            "vidid": vid,
            "duration_min": None,
            "thumb": _thumbnail_from_id(vid) if vid else "",
            "cookiefile": self.cookie,
        }
        async with _meta_lock:
            _meta_cache[key] = (now, empty, vid)
        return empty, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if not vid or str(vid) in ("True", "False"):
            raise ValueError("Video not found")
        dur = data.get("duration_min")
        sec = int(self._to_seconds(dur)) if dur else 0
        return data.get("title", ""), dur, sec, data.get("thumb", ""), str(vid)

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
        if not url:
            return None
        try:
            base_dir = "downloads"
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            session = await _ensure_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception as e:
            log.warning("Failed to download thumbnail: %s", e)
        return None

    def _to_seconds(self, t: Optional[Union[str, int]]) -> int:
        if not t:
            return 0
        try:
            if isinstance(t, int):
                return t
            s = 0
            parts = [int(p) for p in str(t).split(":")]
            for p in parts:
                s = s * 60 + p
            return s
        except Exception:
            try:
                return int(float(t))
            except Exception:
                return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        if not prepared:
            return [], ""
        out: List[Dict[str, Any]] = []
        if yt_dlp is None:
            return out, prepared
        ytdl_opts = {"quiet": True, "skip_download": True, "no_warnings": True}
        if cf := get_cookie_file():
            ytdl_opts["cookiefile"] = cf
        try:
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(prepared, download=False)
                for fmt in info.get("formats", []):
                    fs = fmt.get("filesize") or fmt.get("filesize_approx")
                    out.append(
                        {
                            "format": fmt.get("format"),
                            "filesize": fs,
                            "format_id": str(fmt.get("format_id")),
                            "ext": fmt.get("ext"),
                            "format_note": fmt.get("format_note", ""),
                        }
                    )
        except Exception as e:
            log.debug("formats() extract failed: %s", e)
        return out, prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared:
            return None

        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now + 3:
                return cached[1]
            if cached:
                _direct_cache.pop(key, None)

        # Fast path via InnerTube player
        vid = ""
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", prepared)
        if m:
            vid = m.group(1)

        if vid:
            payload = {
                "context": INNERTUBE_CONTEXT,
                "videoId": vid,
                "contentCheckOk": True,
                "racyCheckOk": True,
            }
            data = await self._post_json(PLAYER_URL.format(key=INNERTUBE_KEY), payload, timeout=PLAYER_TIMEOUT)
            if data:
                direct = _pick_stream_url(data, prefer_audio=prefer_audio)
                if direct and await _probe_url(direct):
                    expiry = _parse_expire(direct) or (now + CACHE_TTL_DIRECT)
                    expiry = int(expiry) - 3
                    async with _direct_lock:
                        _direct_cache[key] = (expiry, direct)
                    return direct

        # Fallback to yt-dlp direct extraction
        if yt_dlp is not None:
            async with self.sema:
                loop = asyncio.get_running_loop()

                def _extract_info_blocking():
                    ydl_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "noplaylist": True,
                        "skip_download": True,
                        "socket_timeout": REQUEST_TIMEOUT,
                        "extractor_args": {"youtube": {"player_client": ["mweb"], "player_skip": ["webpage", "configs"]}},
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

                info = await loop.run_in_executor(self.pool, _extract_info_blocking)

            if isinstance(info, dict) and not info.get("_err"):
                top = info.get("url")
                if top and await _probe_url(str(top)):
                    top = str(top)
                    expiry = _parse_expire(top) or (now + CACHE_TTL_DIRECT)
                    expiry = int(expiry) - 3
                    async with _direct_lock:
                        _direct_cache[key] = (expiry, top)
                    return top

                direct = _pick_stream_url(info, prefer_audio=prefer_audio)
                if direct and await _probe_url(direct):
                    expiry = _parse_expire(direct) or (now + CACHE_TTL_DIRECT)
                    expiry = int(expiry) - 3
                    async with _direct_lock:
                        _direct_cache[key] = (expiry, direct)
                    return direct

        return None

    async def video(self, link: str, is_live: bool = False) -> Tuple[int, str]:
        try:
            direct = await self.get_direct_link(link, prefer_audio=not is_live)
            if direct:
                return 1, direct
            return 0, ""
        except Exception as e:
            log.debug("Video extraction failed: %s", e)
            return 0, ""

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

        try:
            if videoid and str(videoid) not in ("True", "False"):
                vid = str(videoid)
            else:
                m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", prepared)
                if m:
                    vid = m.group(1)
                else:
                    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", prepared)
                    if m:
                        vid = m.group(1)
                    else:
                        vid = str(int(time.time()))
        except Exception:
            vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            try:
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False
            except Exception:
                continue

        # Direct stream is preferred for speed
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception:
            direct = None

        if direct:
            return direct, True

        # Optional fallback download via yt-dlp
        if yt_dlp is None:
            return None, False

        loop = asyncio.get_running_loop()

        def _fallback():
            try:
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "force_ipv4": True,
                    "prefer_ffmpeg": True,
                    "extractor_args": {"youtube": {"player_client": ["mweb"]}},
                }
                if not is_video:
                    ydl_opts["postprocessors"] = [
                        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                    ]
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

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + str(link)
        if "&" in str(link):
            link = str(link).split("&")[0]

        # Try yt-dlp playlist extraction first because it is reliable
        if yt_dlp is not None:
            try:
                cmd = [
                    "yt-dlp",
                    "-i",
                    "--compat-options",
                    "no-youtube-unavailable-videos",
                    "--get-id",
                    "--flat-playlist",
                    "--playlist-end",
                    str(limit),
                    "--skip-download",
                    str(link),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                out, _ = await proc.communicate()
                result = [key for key in out.decode().split("\n") if key]
                if result:
                    return result
            except Exception:
                pass

        # InnerTube browse fallback
        try:
            # playlist_id from URL
            parsed = urlparse(str(link))
            q = parse_qs(parsed.query)
            playlist_id = ""
            if "list" in q and q["list"]:
                playlist_id = q["list"][0]
            elif "youtube.com/playlist?list=" in str(link):
                playlist_id = str(link).split("list=")[-1].split("&")[0]

            if not playlist_id:
                return []

            payload = {
                "context": INNERTUBE_CONTEXT,
                "browseId": f"VL{playlist_id}",
            }
            data = await self._post_json(BROWSE_URL.format(key=INNERTUBE_KEY), payload, timeout=REQUEST_TIMEOUT)
            if not data:
                return []

            vids = []
            for item in _extract_video_items(data):
                vid = item.get("vidid")
                if vid:
                    vids.append(str(vid))
                if len(vids) >= int(limit):
                    break
            return vids
        except Exception:
            return []


# exported instance
YouTube = YouTubeAPI()
