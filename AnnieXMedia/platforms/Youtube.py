# file: AnnieXMedia/platforms/Youtube.py

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

try:
    import orjson as _orjson
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# الموارد ديناميكية حسب المتاح في السيرفر
_cpus = os.cpu_count() or 1
MAX_YTDLP_THREADS = min(32, _cpus * 4)
MAX_CONCURRENT_EXTRACTS = min(16, _cpus * 2)

YTDLP_SOCKET_TIMEOUT = 5
PROBE_TIMEOUT = 1.0
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 100
META_CACHE_TTL = 3600

_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {} 
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "/app/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None

def get_yt_opts(extra_opts: dict = None) -> dict:
    """تجلب إعدادات yt-dlp وتستخدم متصفح كروم كبديل تلقائي للكوكيز"""
    opts = {
        "quiet": True, 
        "no_warnings": True, 
        "socket_timeout": YTDLP_SOCKET_TIMEOUT,
        "extractor_args": {"youtube": {"player_client": ["web"]}} # ✅ تسريع وتخطي الحظر
    }
    cf = get_cookie_file()
    if cf:
        opts["cookiefile"] = cf
    else:
        # يسحب تسجيل الدخول بتاعك من كروم تلقائياً
        opts["cookiesfrombrowser"] = ("chrome",)
    
    if extra_opts:
        opts.update(extra_opts)
    return opts

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 15) -> Tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception): proc.kill()
        return b"", b"timeout"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid: return "https://www.youtube.com/watch?v=" + str(videoid)
    if not link: return ""
    link = link.strip()
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params: return int(params["expire"][0])
    except Exception: pass
    return None

async def _probe_url(url: str, timeout: float = PROBE_TIMEOUT) -> Tuple[bool, Optional[str]]:
    try:
        sess = await _ensure_aio_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400: return True, r.headers.get("Content-Type")
        except:
            try:
                async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                    if r2.status in (200, 206): return True, r2.headers.get("Content-Type")
            except: return False, None
    except: return False, None
    return False, None

def _score_format(fmt: dict, prefer_audio: bool) -> int:
    score = 0
    proto = (fmt.get("protocol") or "").lower()
    ext = (fmt.get("ext") or "").lower()
    vcodec, acodec = fmt.get("vcodec") or "", fmt.get("acodec") or ""
    
    # أولوية للـ m3u8 لو البث مباشر
    if "m3u8" in proto: score += 100
    if proto.startswith("https"): score += 30
    if proto.startswith("http"): score += 20
    if vcodec and vcodec != "none" and acodec and acodec != "none": score += 50
    if prefer_audio and acodec and acodec != "none": score += 15
    if ext in ("mp4",): score += 10
    if ext in ("m4a","webm"): score += 8
    try: score += int(fmt.get("tbr") or fmt.get("abr") or 0) // 100
    except: pass
    return score

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        try:
            import curl_cffi
            self.impersonate = True
        except: self.impersonate = False

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    if getattr(ent, "type", None) == "url":
                        return text[ent.offset: ent.offset + ent.length].split("&si")[0]
                    if u := getattr(ent, "url", None):
                        return u.split("&si")[0]
                except: continue
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        results = []
        try:
            from youtubesearchpython.aio import VideosSearch
            res = await VideosSearch(query, limit=limit).next()
            for r in res.get("result", []):
                results.append({"title": r.get("title", "Unknown"), "vidid": r.get("id", ""), "duration": r.get("duration", "")})
            if results: return results
        except: pass

        loop = asyncio.get_running_loop()
        def _yt_search():
            opts = get_yt_opts({"extract_flat": True, "skip_download": True})
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(f"ytsearch{limit}:{query}", download=False).get("entries", [])
        
        try:
            entries = await loop.run_in_executor(self.pool, _yt_search)
            for e in entries:
                if e: results.append({"title": e.get("title", "Unknown"), "vidid": e.get("id", ""), "duration": e.get("duration_string", "")})
        except: pass
        return results

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid
                _meta_cache.pop(key, None)

        try:
            from youtubesearchpython.aio import VideosSearch
            if results := (await VideosSearch(prepared, limit=1).next()).get("result", []):
                data = results[0]
                thumb = (data.get("thumbnails") or [{}])[-1].get("url", "")
                details = {
                    "title": data.get("title", "") or "", "link": data.get("link", prepared) or prepared,
                    "vidid": data.get("id", "") or "", "duration_min": data.get("duration"), "thumb": thumb.split("?")[0] if thumb else ""
                }
                async with _meta_cache_lock: _meta_cache[key] = (now, details, data.get("id", ""))
                return details, data.get("id", "")
        except: pass

        loop = asyncio.get_running_loop()
        def _extract_meta():
            opts = get_yt_opts({"skip_download": True})
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(prepared, download=False)
        try:
            info = await loop.run_in_executor(self.pool, _extract_meta)
            details = {
                "title": info.get("title", "Unknown"), "link": info.get("webpage_url", prepared),
                "vidid": info.get("id", ""), "duration_min": info.get("duration_string") or info.get("duration"),
                "thumb": (info.get("thumbnail") or "").split("?")[0]
            }
            async with _meta_cache_lock: _meta_cache[key] = (now, details, info.get("id", ""))
            return details, info.get("id", "")
        except: pass
        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": ""}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min")
        return data.get("title", ""), dur, int(self._to_seconds(dur)) if dur else 0, data.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        return (await self.track(link, videoid))[0].get("title", "")

    async def duration(self, link: str, videoid: Union[bool, str, None] = None) -> Optional[str]:
        return (await self.track(link, videoid))[0].get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        return (await self.track(link, videoid))[0].get("thumb", "")
    
    # ✅ دالة الصورة الأساسية عشان التشغيل ميوقعش
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            os.makedirs("downloads", exist_ok=True)
            path = os.path.join("downloads", f"thumb_{int(time.time())}.jpg")
            async with (await _ensure_aio_session()).get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f: f.write(await resp.read())
                    return path
        except: pass
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        if isinstance(t, int): return t
        try:
            s = 0
            for p in str(t).split(":"): s = s * 60 + int(p)
            return s
        except: return int(float(t)) if str(t).replace('.','',1).isdigit() else 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        loop = asyncio.get_running_loop()
        def _get_fmts():
            with yt_dlp.YoutubeDL(get_yt_opts()) as ydl:
                return ydl.extract_info(prepared, download=False).get("formats", [])
        try:
            fmts = await loop.run_in_executor(self.pool, _get_fmts)
            return [{"format": f.get("format"), "filesize": f.get("filesize") or f.get("filesize_approx"), "format_id": str(f.get("format_id")), "ext": f.get("ext"), "format_note": f.get("format_note", "")} for f in fmts], prepared
        except: return [], prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        """✅ استخراج الرابط المباشر (البث المباشر) بسرعة وتخطي"""
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_cache_lock:
            if cached := _direct_cache.get(key):
                if cached[0] > now + 3: return cached[1]
                _direct_cache.pop(key, None)

        info = None
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_fast():
                opts = get_yt_opts({
                    "noplaylist": True, "skip_download": True, "nocheckcertificate": True
                })
                if self.impersonate: opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception as e: return {"_err": str(e)}

            info = await loop.run_in_executor(self.pool, _extract_fast)

        # لو الـ API فشل، نشغل Subprocess -g كحل بديل فوري
        if not info or info.get("_err"):
            cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", "--extractor-args", "youtube:player_client=web"]
            cf = get_cookie_file()
            if cf:
                cmd.extend(["--cookies", cf])
            cmd.append(prepared)
            
            out, _ = await _exec_proc(*cmd, timeout=10)
            if out:
                urls = out.decode().splitlines()
                if urls:
                    cand = urls[0].strip()
                    if (await _probe_url(cand))[0]:
                        async with _direct_cache_lock: _direct_cache[key] = (int(_parse_expire(cand) or now + CACHE_DEFAULT_TTL) - 3, cand)
                        return cand
            return None

        # التعامل مع البث المباشر (is_live)
        is_live = info.get("is_live") or info.get("live_status") == "is_live"
        if is_live and info.get("url"):
            top_url = info.get("url")
            if (await _probe_url(top_url))[0]:
                async with _direct_cache_lock: _direct_cache[key] = (now + CACHE_DEFAULT_TTL, top_url)
                return top_url

        if top_url := info.get("url"):
            if not is_live and (await _probe_url(top_url))[0]:
                async with _direct_cache_lock: _direct_cache[key] = (int(_parse_expire(top_url) or now + CACHE_DEFAULT_TTL) - 3, top_url)
                return top_url

        candidates = []
        for f in info.get("formats", []):
            url = f.get("url")
            if not url or not url.startswith(("http", "https", "m3u8")): continue
            if prefer_audio and (f.get("acodec") or "none") == "none": continue
            if not prefer_audio and (f.get("vcodec") or "none") != "none" and (f.get("acodec") or "none") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if (f.get("acodec") or "none") != "none": candidates.append((_score_format(f, prefer_audio), url)); continue
            if "m3u8" in url: candidates.append((100, url))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for _, cand in candidates[:6]:
            if (await _probe_url(cand))[0]:
                async with _direct_cache_lock: _direct_cache[key] = (int(_parse_expire(cand) or now + CACHE_DEFAULT_TTL) - 3, cand)
                return cand

        if not prefer_audio: return await self.get_direct_link(link, prefer_audio=True)
        return None

    async def download(self, link: str, mystic: Any, video: Union[bool, str] = None, videoid: Union[bool, str] = None, songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None, title: Union[bool, str] = None) -> Tuple[Optional[str], bool]:
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        try: vid = str(videoid) if videoid else prepared.split("v=")[1].split("&")[0]
        except: vid = str(int(time.time()))

        ram_base = os.path.join("/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads"), vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            if os.path.exists(f"{ram_base}{ext}") and os.path.getsize(f"{ram_base}{ext}") > 1024:
                return f"{ram_base}{ext}", False

        loop = asyncio.get_running_loop()

        if format_id:
            def _specific():
                opts = get_yt_opts({"format": f"{format_id}+140" if songvideo else format_id, "outtmpl": f"{ram_base}.%(ext)s", "force_ipv4": True})
                if songaudio: opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                if songvideo: opts["merge_output_format"] = "mp4"
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        path = ydl.prepare_filename(ydl.extract_info(prepared, download=True))
                        return os.path.splitext(path)[0] + ".mp3" if songaudio and not path.endswith(".mp3") and os.path.exists(os.path.splitext(path)[0] + ".mp3") else path
                except: return None
            return (await loop.run_in_executor(self.pool, _specific), False)

        try: direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except: direct = None

        if direct:
            loop.run_in_executor(self.pool, lambda: [time.sleep(4), self._background_download(prepared, f"{ram_base}.%(ext)s", is_video)])
            return direct, True

        def _fallback():
            opts = get_yt_opts({"format": "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best", "outtmpl": f"{ram_base}.%(ext)s"})
            if not is_video: opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "192"}]
            else: opts["merge_output_format"] = "mp4"
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    path = ydl.prepare_filename(ydl.extract_info(prepared, download=True))
                    return os.path.splitext(path)[0] + ".mp3" if not is_video and not path.endswith(".mp3") and os.path.exists(os.path.splitext(path)[0] + ".mp3") else path
            except: return None

        res = await loop.run_in_executor(self.pool, _fallback)
        return (res, False) if res and os.path.exists(res) else (None, False)

    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            opts = get_yt_opts({
                "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": out_template, "force_ipv4": True,
                "external_downloader": "aria2c", "external_downloader_args": ["-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            })
            if not is_video: opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else: opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([link])
        except: pass

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        link = (self.listbase + link if videoid else link).split("&")[0]
        loop = asyncio.get_running_loop()
        def _get_list():
            opts = get_yt_opts({"extract_flat": True, "skip_download": True, "playlistend": limit, "compat_opts": ["no-youtube-unavailable-videos"]})
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return [e.get("id") for e in ydl.extract_info(link, download=False).get("entries", []) if e.get("id")]
            except: return []
        return await loop.run_in_executor(self.pool, _get_list)

YouTube = YouTubeAPI()
