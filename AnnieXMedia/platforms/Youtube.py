# file: AnnieXMedia/platforms/Youtube.py
# Robust YouTube resolver for AnnieXMedia (2026)
# STRICT MODE: Direct Links ONLY. ZERO Downloads. Maximum Speed.

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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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
    except Exception: pass
    return score

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
        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download",
            "--extractor-args", "youtube:player_client=mweb,default"
        ]
        if self.cookie:
            cmd.insert(1, "--cookies")
            cmd.insert(2, self.cookie)
            
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

    async def video(self, link: str, is_live: bool = False) -> Tuple[int, str]:
        try:
            prepared = _normalize_link(link)
            cmd = ["yt-dlp", "-g", "--force-ipv4", "--extractor-args", "youtube:player_client=mweb,default", prepared]
            if self.cookie:
                cmd = ["yt-dlp", "-g", "--cookies", self.cookie, "--force-ipv4", "--extractor-args", "youtube:player_client=mweb,default", prepared]
            out, err = await _exec_proc(*cmd, timeout=8)
            if out:
                url = out.decode().splitlines()[0].strip()
                return 1, url
            return 0, ""
        except Exception as e:
            log.debug(f"Video extraction failed: {e}")
            return 0, ""

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
            details = {
                "title": data.get("title", "") or "",
                "link": data.get("link", prepared) or prepared,
                "vidid": v_id,
                "duration_min": data.get("duration"),
                "thumb": thumb.split("?")[0] if thumb else "",
                "cookiefile": self.cookie,
            }
            async with _meta_cache_lock: _meta_cache[key] = (now, details, v_id)
            return details, v_id

        cmd = ["yt-dlp", "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        if self.cookie:
            cmd = ["yt-dlp", "--cookies", self.cookie, "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        out, err = await _exec_proc(*cmd, timeout=10)
        if out:
            try:
                info = _loads_bytes(out)
                v_id = info.get("id", "")
                if str(v_id) in ["True", "False"]: v_id = ""
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", "") or "",
                    "link": info.get("webpage_url", prepared) or prepared,
                    "vidid": v_id,
                    "duration_min": info.get("duration"),
                    "thumb": thumb,
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock: _meta_cache[key] = (now, details, v_id)
                return details, v_id
            except Exception: pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": self.cookie}, ""

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
                    with open(path, "wb") as f: f.write(data)
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
        except Exception: return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        ytdl_opts = {"quiet": True}
        if cf := get_cookie_file(): ytdl_opts["cookiefile"] = cf
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
        except Exception: pass
        return out, prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # الكاش: الاستجابة في 0.001 ثانية
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_info_blocking():
                ydl_opts = {
                    "format": "bestaudio/best" if prefer_audio else "best", 
                    "quiet": True, 
                    "no_warnings": True, 
                    "noplaylist": True, 
                    "skip_download": True, 
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT, 
                    "extractor_args": {"youtube": {"player_client": ["mweb", "default"]}}
                }
                if self.cookie:
                    ydl_opts["cookiefile"] = self.cookie
                if self.impersonate:
                    ydl_opts["impersonate"] = "chrome" 
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(prepared, download=False)
                except Exception as e: return {"_err": str(e)}

            info = await loop.run_in_executor(self.pool, _extract_info_blocking)

        if not info or (isinstance(info, dict) and info.get("_err")):
            # Fallback لـ subprocess لو الـ API فشل (برضه رابط مباشر بس مفيش تنزيل)
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", "--extractor-args", "youtube:player_client=mweb,default", prepared]
                if self.cookie:
                    cmd = ["yt-dlp", "-g", "--cookies", self.cookie, "--no-warnings", "--force-ipv4", "--extractor-args", "youtube:player_client=mweb,default", prepared]
                out, _err = await _exec_proc(*cmd, timeout=8)
                if out:
                    candidate = out.decode().splitlines()[0].strip()
                    ok, _ctype = await _probe_url(candidate)
                    if ok:
                        expiry = _parse_expire(candidate) or (now + CACHE_DEFAULT_TTL)
                        async with _direct_cache_lock: _direct_cache[key] = (int(expiry) - 3, candidate)
                        return candidate
            except Exception: pass
            return None

        fmts: List[dict] = info.get("formats") or []
        top_url = info.get("url")
        if top_url:
            ok, _ = await _probe_url(top_url)
            if ok:
                expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock: _direct_cache[key] = (int(expiry) - 3, top_url)
                return top_url

        candidates: List[Tuple[int, str]] = []
        for f in fmts:
            url = f.get("url")
            if not url: continue
            proto = (f.get("protocol") or "").lower()
            if not proto.startswith(("http", "https", "m3u8")): continue
            if prefer_audio and (f.get("acodec") or "") == "none": continue
            if not prefer_audio and (f.get("vcodec") or "") != "none" and (f.get("acodec") or "") != "none": candidates.append((_score_format(f, prefer_audio), url)); continue
            if (f.get("acodec") or "") != "none": candidates.append((_score_format(f, prefer_audio), url)); continue
            if proto.startswith("m3u8"): candidates.append((40, url))

        candidates.sort(key=lambda x: x[0], reverse=True)
        tries = 0
        for _score, cand in candidates:
            if tries >= 6: break
            tries += 1
            ok, _ctype = await _probe_url(cand)
            if ok:
                expiry = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock: _direct_cache[key] = (int(expiry) - 3, cand)
                return cand

        if not prefer_audio: return await self.get_direct_link(link, prefer_audio=True)
        return None

    # 🛑 تم مسح كود الـ _fallback نهائياً. بيجيب مباشر يا بيفشل فوراً.
    async def download(
        self, link: str, mystic: Any, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None, title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        # ⚡ محاولة سحب الرابط المباشر فقط
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception as e:
            log.debug("get_direct_link err: %s", e)
            direct = None

        if direct:
            log.info(f"✅ Extracted Direct Link successfully for {prepared}")
            return direct, True  # True تعني تشغيل مباشر (Stream) وليس ملف
            
        log.error(f"❌ Failed to extract Direct Link for {prepared}. No fallback allowed.")
        return None, False

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp --extractor-args 'youtube:player_client=mweb,default' -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try: result = [key for key in out.decode().split("\n") if key]
        except Exception: result = []
        return result

YouTube = YouTubeAPI()
