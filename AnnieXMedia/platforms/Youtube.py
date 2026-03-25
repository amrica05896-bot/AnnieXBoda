# file: AnnieXMedia/platforms/Youtube.py
# Robust YouTube resolver for AnnieXMedia
# Fixed: Forced Direct Links Only, iOS/TV Client Bypass (No PO Token required)

import asyncio
import contextlib
import json
import logging
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

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

MAX_YTDLP_THREADS = 16
MAX_CONCURRENT_EXTRACTS = 6
YTDLP_SOCKET_TIMEOUT = 5 
PROBE_TIMEOUT = 1.2
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 64
META_CACHE_TTL = 3600

_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

# 🚀 الحل: استخدام عميل الايفون والتلفزيون لتجاوز حظر التوكن
CLIENT_ARGS = ["--extractor-args", "youtube:player_client=ios,tv"]
CLIENT_API_ARGS = {"youtube": {"player_client": ["ios", "tv"]}}

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
    if videoid and str(videoid) not in ["True", "False"]:
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
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)"}
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400: return True, r.headers.get("Content-Type")
        except Exception:
            try:
                async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                    if r2.status in (200, 206): return True, r2.headers.get("Content-Type")
            except Exception: return False, None
    except Exception: return False, None
    return False, None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.impersonate = False

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
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
                    if u: return u.split("&si")[0]
                except Exception: continue
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        cmd = ["yt-dlp"] + CLIENT_ARGS + ["--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
        out, _ = await _exec_proc(*cmd, timeout=8)
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
                except Exception: pass
        return results

    async def slider(self, query: str, query_type: int) -> Tuple[str, str, str, str]:
        results = await self.search(query, limit=10)
        if not results: raise ValueError("No results found")
        idx = query_type % len(results)
        item = results[idx]
        vid = item["vidid"]
        d, _ = await self.track(vid, videoid=vid)
        return d.get("title", "Unknown"), str(d.get("duration_min", "00:00")), d.get("thumb", ""), vid

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid
                _meta_cache.pop(key, None)

        results = []
        try:
            from youtubesearchpython.aio import VideosSearch  # type: ignore
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", [])
        except Exception: pass

        if results:
            data = results[0]
            v_id = data.get("id", "")
            if str(v_id) in ["True", "False"]: v_id = ""
            thumb = (data.get("thumbnails") or [{}])[-1].get("url", "")
            details = {"title": data.get("title", ""), "link": data.get("link", prepared), "vidid": v_id, "duration_min": data.get("duration"), "thumb": thumb.split("?")[0] if thumb else ""}
            async with _meta_cache_lock: _meta_cache[key] = (now, details, v_id)
            return details, v_id

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": ""}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if not vid or str(vid) in ["True", "False"]: raise ValueError("Video not found")
        dur = data.get("duration_min")
        sec = int(self._to_seconds(dur)) if dur else 0
        return data.get("title", ""), dur, sec, data.get("thumb", ""), str(vid)

    async def title(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid); return d.get("title", "")

    async def duration(self, link: str, videoid: Union[bool, str, None] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid); return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid); return d.get("thumb", "")

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except Exception: return 0

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # الكاش (0.001 ثانية)
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now + 3: return cached[1]

        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_info_blocking():
                # جلب الرابط المباشر فقط وتجاهل التنزيل
                ydl_opts = {
                    "format": "140/251/bestaudio" if prefer_audio else "best",
                    "quiet": True, 
                    "no_warnings": True, 
                    "noplaylist": True, 
                    "skip_download": True, 
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT, 
                    "extractor_args": CLIENT_API_ARGS
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception as e: return {"_err": str(e)}
            info = await loop.run_in_executor(self.pool, _extract_info_blocking)

        if info and not info.get("_err"):
            top_url = info.get("url")
            if top_url:
                ok, _ = await _probe_url(top_url)
                if ok:
                    exp = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                    async with _direct_cache_lock: _direct_cache[key] = (int(exp) - 3, top_url)
                    return top_url

        return None

    # 🚀 هنا التعديل الأهم: إجبار الدالة على إرجاع رابط مباشر فقط، وإلغاء التنزيل المادي!
    async def download(self, link: str, mystic: Any, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> Tuple[Optional[str], bool]:
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        
        # استخراج الرابط المباشر فقط
        direct_url = await self.get_direct_link(prepared, prefer_audio=not is_video)
        
        if direct_url:
            log.info(f"✅ Extracted Direct Link successfully for {prepared}")
            return direct_url, True  # True معناها إن ده Stream مش ملف محمل
            
        log.error(f"❌ Failed to extract Direct Link for {prepared}")
        return None, False

YouTube = YouTubeAPI()
