import os
import sys
import time

# 🚀 السحر هنا: إجبار بايثون ومكتباتها (yt-dlp و aiohttp) على استخدام orjson لسرعة صاروخية
try:
    import orjson
    import json
    json.loads = orjson.loads
    json.dumps = lambda obj, **kwargs: orjson.dumps(obj).decode('utf-8')
    sys.modules['json'] = json  
except ImportError:
    import json

import asyncio
import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

MAX_YTDLP_THREADS = 32  # تم رفعها لزيادة استيعاب السيرفر
MAX_CONCURRENT_EXTRACTS = 16
YTDLP_SOCKET_TIMEOUT = 8
PROBE_TIMEOUT = 1.2
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
        _aio_session = aiohttp.ClientSession(
            connector=_aio_connector, 
            raise_for_status=False,
            json_serialize=json.dumps  # تم حقنه بـ orjson
        )
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
        return "https://youtube.com/watch?v=" + str(videoid)
    if not link:
        return ""
    link = link.strip()
    if "youtu.be" in link:
        return "https://youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts" in link or "youtube.com/live" in link:
        return "https://youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
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
        self.base = "https://youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        try:
            import curl_cffi  
            self.impersonate = True
        except Exception:
            self.impersonate = False

    def _sync_local_extract(self, query: str, flat: bool = False) -> dict:
        """ الخطة المحلية الصاروخية In-Memory """
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist" if flat else False,
            "noplaylist": not flat,
            "allowed_extractors": ["youtube"], # تسريع خطير لمنع استخراج مواقع أخرى
            "cachedir": False, # منع الكتابة عالهارد
            "socket_timeout": YTDLP_SOCKET_TIMEOUT,
            "compat_opts": ["no-youtube-unavailable-videos"],
            "remote_components": ["ejs:github", "ejs:npm"],
            "extractor_args": {"youtube": {"player_client": ["web"]}} # الويب عشان الكوكيز
        }
        if self.cookie: 
            opts["cookiefile"] = self.cookie
        if getattr(self, "impersonate", False): 
            opts["impersonate"] = "chrome"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(query, download=False)
        except Exception as e:
            # حماية ذكية: لو الكروم عمل مشكلة، نعيد بدون impersonate فوراً
            err_str = str(e).lower()
            if "impersonate" in err_str or "target" in err_str:
                opts.pop("impersonate", None)
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl_fallback:
                        return ydl_fallback.extract_info(query, download=False)
                except Exception:
                    pass
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
                        return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u:
                        return u.split("&si")[0]
                except Exception:
                    continue
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        loop = asyncio.get_running_loop()
        def _get_search():
            q = f"ytsearch{limit}:{query}"
            info = self._sync_local_extract(q, flat=True)
            results = []
            if info and "entries" in info:
                for data in info["entries"]:
                    try:
                        dur = data.get("duration_string")
                        if not dur or str(dur).lower() in ["live", "stream", "none"]:
                            dur = "Live"
                        results.append({
                            "title": data.get("title", "Unknown"),
                            "vidid": data.get("id", ""),
                            "duration": dur
                        })
                    except Exception:
                        pass
            return results
        return await loop.run_in_executor(self.pool, _get_search)

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
                
        # الاعتماد الكلي على المعالجة المحلية السريعة بدون API
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(self.pool, self._sync_local_extract, prepared, False)
        
        if info:
            thumb = (info.get("thumbnail") or "").split("?")[0]
            is_live = info.get("is_live") or info.get("was_live")
            dur = "Live" if is_live else info.get("duration_string", "0:00")
            details = {
                "title": info.get("title", "") or "",
                "link": info.get("webpage_url", prepared) or prepared,
                "vidid": info.get("id", "") or "",
                "duration_min": dur,
                "thumb": thumb,
                "cookiefile": self.cookie,
            }
            async with _meta_cache_lock:
                _meta_cache[key] = (now, details, info.get("id", ""))
            return details, info.get("id", "")
            
        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": self.cookie}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if vid == "":
            raise ValueError("Video not found")
        dur = data.get("duration_min")
        sec = 0 if str(dur).lower() in ["live", "none"] else int(self._to_seconds(dur))
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
        if not results:
            raise ValueError("No results found")
        idx = query_type % len(results)
        item = results[idx]
        thumb = item.get("thumb") or f"https://i.ytimg.com/vi/{item['vidid']}/hqdefault.jpg"
        return item["title"], item["duration"], thumb, item["vidid"]

    async def download_thumb(self, url: str) -> Optional[str]:
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
        except Exception:
            pass
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
        prepared = _normalize_link(link, videoid)
        out: List[Dict[str, Any]] = []
                
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(self.pool, self._sync_local_extract, prepared, False)
        if info:
            for fmt in info.get("formats", []):
                fs = fmt.get("filesize") or fmt.get("filesize_approx")
                out.append({
                    "format": fmt.get("format"),
                    "filesize": fs,
                    "format_id": str(fmt.get("format_id")),
                    "ext": fmt.get("ext"),
                    "format_note": fmt.get("format_note", ""),
                })
        return out, prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
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
                    
        # الاستخراج الداخلي المباشر
        async with self.sema:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(self.pool, self._sync_local_extract, prepared, False)
            
        if not info:
            return None
            
        fmts: List[dict] = info.get("formats") or []
        top_url = info.get("url")
        if top_url:
            ok, _ = await _probe_url(top_url)
            if ok:
                expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                expiry = int(expiry) - 3
                async with _direct_cache_lock:
                    _direct_cache[key] = (expiry, top_url)
                return top_url
                
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
            if videoid:
                vid = str(videoid)
            elif "v=" in prepared:
                vid = prepared.split("v=")[1].split("&")[0]
            elif "youtube.com/shorts" in prepared:
                vid = prepared.split("youtube.com/shorts/")[1].split("?")[0]
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
                
        loop = asyncio.get_running_loop()
        if format_id:
            def _specific():
                try:
                    opts = {
                        "format": (f"{format_id}+140" if songvideo else format_id),
                        "outtmpl": f"{ram_base}.%(ext)s",
                        "quiet": True,
                        "force_ipv4": True,
                        "allowed_extractors": ["youtube"],
                        "cachedir": False,
                        "remote_components": ["ejs:github", "ejs:npm"],
                        "extractor_args": {"youtube": {"player_client": ["web"]}},
                    }
                    if self.cookie: opts["cookiefile"] = self.cookie
                    if getattr(self, "impersonate", False): opts["impersonate"] = "chrome"
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
            
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception:
            direct = None
            
        if direct:
            def _delayed_cache():
                try:
                    time.sleep(6)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True
            
        def _fallback():
            try:
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "quiet": True,
                    "force_ipv4": True,
                    "allowed_extractors": ["youtube"],
                    "cachedir": False,
                    "remote_components": ["ejs:github", "ejs:npm"],
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                    "prefer_ffmpeg": True,
                }
                if self.cookie: ydl_opts["cookiefile"] = self.cookie
                if getattr(self, "impersonate", False): ydl_opts["impersonate"] = "chrome"
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
            except Exception:
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
                "quiet": True,
                "force_ipv4": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
                "allowed_extractors": ["youtube"],
                "cachedir": False,
                "remote_components": ["ejs:github", "ejs:npm"],
                "extractor_args": {"youtube": {"player_client": ["web"]}},
                "prefer_ffmpeg": True,
                "writethumbnail": True,
                "addmetadata": True,
            }
            if self.cookie: ydl_opts["cookiefile"] = self.cookie
            if getattr(self, "impersonate", False): ydl_opts["impersonate"] = "chrome"
            if not is_video:
                ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception:
            pass

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
            
        loop = asyncio.get_running_loop()
        def _get_playlist():
            opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": True,
                "playlistend": limit,
                "allowed_extractors": ["youtube"],
                "cachedir": False,
                "remote_components": ["ejs:github", "ejs:npm"],
                "extractor_args": {"youtube": {"player_client": ["web"]}}
            }
            if getattr(self, "cookie", None): opts["cookiefile"] = self.cookie
            if getattr(self, "impersonate", False): opts["impersonate"] = "chrome"
            
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    if not info or "entries" not in info: return []
                    return [e.get("id") for e in info["entries"] if e.get("id")]
            except Exception as e:
                err_str = str(e).lower()
                if "impersonate" in err_str or "target" in err_str:
                    opts.pop("impersonate", None)
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl_f:
                            info = ydl_f.extract_info(link, download=False)
                            if not info or "entries" not in info: return []
                            return [e.get("id") for e in info["entries"] if e.get("id")]
                    except Exception: pass
            return []
            
        return await loop.run_in_executor(self.pool, _get_playlist)

YouTube = YouTubeAPI()
