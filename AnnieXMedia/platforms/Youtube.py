# file: AnnieXMedia/platforms/Youtube.py
# Robust YouTube resolver for AnnieXMedia (2026)
# 🚀 ULTRA FAST EDITION: Google Data API v3 (Search) + Shrutibots API (Stream Proxy) + yt-dlp (Fallback)

import asyncio
import contextlib
import json
import logging
import os
import re
import time
import urllib.parse
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

# Logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# --- 🚀 المفاتيح والروابط الأساسية ---
GOOGLE_API_KEY = "AIzaSyCIXHJRql0WncJmXLKITtC7oOP57eJDmzM"
SHRUTI_API_URL = "https://shrutibots.site"

# Tunables
MAX_YTDLP_THREADS = 16
MAX_CONCURRENT_EXTRACTS = 6
YTDLP_SOCKET_TIMEOUT = 8
PROBE_TIMEOUT = 1.2
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 64
META_CACHE_TTL = 3600

# Pools / semaphores / caches
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {}   # key -> (expiry_epoch, url)
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

def _parse_iso_duration(duration_str: str) -> str:
    if not duration_str: return "0:00"
    if duration_str == "P0D": return "Live"
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return "0:00"
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    if hours > 0: return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

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

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        try:
            import curl_cffi  # type: ignore
            self.impersonate = True
        except Exception:
            self.impersonate = False

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
                        return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u:
                        return u.split("&si")[0]
                except Exception:
                    continue
        return None

    # 🚀 بحث سريع بـ Google API
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            sess = await _ensure_aio_session()
            api_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults={limit}&q={urllib.parse.quote(query)}&type=video&key={GOOGLE_API_KEY}&fields=items(id/videoId,snippet/title)"
            async with sess.get(api_url, timeout=3) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for item in data.get("items", []):
                        results.append({
                            "title": item.get("snippet", {}).get("title", "Unknown"),
                            "vidid": item.get("id", {}).get("videoId", ""),
                            "duration": "0:00"
                        })
                    if results:
                        return results
        except Exception as e:
            log.warning(f"Official API Search Error, falling back to yt-dlp: {e}")

        cmd = ["yt-dlp", "--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
        if self.cookie:
            cmd.insert(1, "--cookies")
            cmd.insert(2, self.cookie)

        out, _ = await _exec_proc(*cmd, timeout=10)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({
                        "title": data.get("title", "Unknown"),
                        "vidid": data.get("id", ""),
                        "duration": data.get("duration_string", "")
                    })
                except Exception:
                    pass
        return results

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

        is_search = not prepared.startswith("http")
        target_vid = str(videoid) if videoid else None

        try:
            sess = await _ensure_aio_session()
            if is_search and not target_vid:
                search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=1&q={urllib.parse.quote(prepared)}&type=video&key={GOOGLE_API_KEY}&fields=items(id/videoId)"
                async with sess.get(search_url, timeout=3) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("items"):
                            target_vid = data["items"][0]["id"]["videoId"]
                            prepared = f"https://www.youtube.com/watch?v={target_vid}"

            if not target_vid:
                if "v=" in prepared:
                    target_vid = prepared.split("v=")[1].split("&")[0]
                elif "youtu.be/" in prepared:
                    target_vid = prepared.split("youtu.be/")[1].split("?")[0]
            
            if target_vid:
                details_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id={target_vid}&key={GOOGLE_API_KEY}"
                async with sess.get(details_url, timeout=3) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("items"):
                            item = data["items"][0]
                            title = item["snippet"]["title"]
                            thumb = item["snippet"]["thumbnails"].get("high", item["snippet"]["thumbnails"].get("default", {})).get("url", "")
                            duration_iso = item["contentDetails"]["duration"]
                            duration_min = _parse_iso_duration(duration_iso)
                            
                            details = {
                                "title": title,
                                "link": f"https://www.youtube.com/watch?v={target_vid}",
                                "vidid": target_vid,
                                "duration_min": duration_min,
                                "thumb": thumb,
                                "cookiefile": self.cookie,
                            }
                            async with _meta_cache_lock:
                                _meta_cache[key] = (now, details, target_vid)
                            return details, target_vid
        except Exception as e:
            log.warning(f"Official API Track Error: {e}")

        results = []
        try:
            from youtubesearchpython.aio import VideosSearch  # type: ignore
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

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": self.cookie}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if vid == "": raise ValueError("Video not found")
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

    # 🚀 الاستخراج المباشر والسريع
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1. كاش الذاكرة
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        # 🚀 2. الاعتماد الأساسي: الشحن الصاروخي عبر Shrutibots API 
        vid_id = None
        # استخراج دقيق للـ ID لتجنب أخطاء البادئة الوهمية (مثل 0 أو 1 قبل الـ ID)
        if "googleusercontent.com/youtube.com/" in prepared:
            vid_id = prepared.split("/")[-1].split("?")[0]
            if len(vid_id) == 12 and vid_id[0].isdigit(): vid_id = vid_id[1:] # إزالة الرقم الوهمي
            elif len(vid_id) > 11: vid_id = vid_id[-11:]
        elif "v=" in prepared:
            vid_id = prepared.split("v=")[1].split("&")[0][:11]
        else:
            match = re.search(r"([0-9A-Za-z_-]{11})", prepared)
            if match: vid_id = match.group(1)

        # إذا كان الـ ID صحيح (11 حرف) نستخدم الـ API الصاروخي
        if vid_id and len(vid_id) == 11:
            media_type = "audio" if prefer_audio else "video"
            try:
                sess = await _ensure_aio_session()
                api_url = f"{SHRUTI_API_URL}/download"
                async with sess.get(api_url, params={"url": vid_id, "type": media_type}, timeout=7) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token = data.get("download_token")
                        if token:
                            # السيرفر بيشتغل كـ Proxy كما أثبت الفحص
                            stream_url = f"{SHRUTI_API_URL}/stream/{vid_id}?type={media_type}&token={token}"
                            async with _direct_cache_lock:
                                _direct_cache[key] = (now + 18000, stream_url) # حفظ في الكاش لـ 5 ساعات
                            return stream_url
            except Exception as e:
                log.warning(f"Shrutibots Fast Fetch failed: {e}. Falling back to yt-dlp...")

        # 🔄 3. خطة الطوارئ (Fallback): العمل عبر yt-dlp لو السيرفر وقع
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_info_blocking():
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    "extractor_args": {"youtube": {"player_client": ["web"], "player_skip": ["configs"]}},
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
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--extractor-args", "youtube:player_client=web;player_skip=configs", "--force-ipv4", prepared]
                out, _err = await _exec_proc(*cmd, timeout=8)
                if out: return out.decode().splitlines()[0].strip()
            except Exception: pass
            return None

        fmts: List[dict] = info.get("formats") or []
        top_url = info.get("url")
        if top_url: return top_url
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

        # 🚀 الصاروخ: جلب الرابط المباشر للـ API فوراً للـ pytgcalls 
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception: direct = None

        if direct:
            # True تعني أن هذا رابط مباشر للتشغيل (Streaming)، وليس ملف محلي
            return direct, True

        return None, False

# exported instance
YouTube = YouTubeAPI()
