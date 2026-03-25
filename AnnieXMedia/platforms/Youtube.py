# file: AnnieXMedia/platforms/Youtube.py
# Robust YouTube resolver for AnnieXMedia (2026)
# Fixed: Boolean ID Fix, TV/Android Clients, Removed Cookies, & Added Lightning Fast Scraper (0.5s)

import asyncio
import contextlib
import json
import logging
import os
import time
import re  # ✅ تم إضافة مكتبة re للبحث السريع
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
YTDLP_SOCKET_TIMEOUT = 8
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

CLIENT_ARGS = ["--extractor-args", "youtube:player_client=tv,android"]
CLIENT_API_ARGS = {"youtube": {"player_client": ["tv", "android"]}}

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
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
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
        cmd = ["yt-dlp"] + CLIENT_ARGS + ["--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
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
            cmd = ["yt-dlp"] + CLIENT_ARGS + ["-g", "--force-ipv4", prepared]
            out, err = await _exec_proc(*cmd, timeout=10)
            if out: return 1, out.decode().splitlines()[0].strip()
            return 0, ""
        except Exception: return 0, ""

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

        cmd = ["yt-dlp"] + CLIENT_ARGS + ["--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        out, err = await _exec_proc(*cmd, timeout=12)
        if out:
            try:
                info = _loads_bytes(out)
                v_id = info.get("id", "")
                if str(v_id) in ["True", "False"]: v_id = ""
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {"title": info.get("title", ""), "link": info.get("webpage_url", prepared), "vidid": v_id, "duration_min": info.get("duration"), "thumb": thumb}
                async with _meta_cache_lock: _meta_cache[key] = (now, details, v_id)
                return details, v_id
            except Exception: pass

        cmd2 = ["yt-dlp"] + CLIENT_ARGS + ["--remote-components", "ejs:github", "--dump-json", prepared, "--no-warnings"]
        out2, err2 = await _exec_proc(*cmd2, timeout=16)
        if out2:
            try:
                info = _loads_bytes(out2)
                v_id = info.get("id", "")
                if str(v_id) in ["True", "False"]: v_id = ""
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {"title": info.get("title", ""), "link": info.get("webpage_url", prepared), "vidid": v_id, "duration_min": info.get("duration"), "thumb": thumb}
                async with _meta_cache_lock: _meta_cache[key] = (now, details, v_id)
                return details, v_id
            except Exception: pass

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
    
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            base_dir = "downloads"
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            session = await _ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f: f.write(await resp.read())
                    return path
        except Exception: pass
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
        ytdl_opts = {"quiet": True, "extractor_args": CLIENT_API_ARGS}
        out: List[Dict[str, Any]] = []
        try:
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(prepared, download=False)
                for fmt in info.get("formats", []):
                    fs = fmt.get("filesize") or fmt.get("filesize_approx")
                    out.append({"format": fmt.get("format"), "filesize": fs, "format_id": str(fmt.get("format_id")), "ext": fmt.get("ext"), "format_note": fmt.get("format_note", "")})
        except Exception: pass
        return out, prepared

    # 🚀 الدالة الصاروخية الجديدة (تعمل في 0.5 ثانية)
    async def fast_scrape(self, prepared_url: str) -> Optional[str]:
        try:
            sess = await _ensure_aio_session()
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with sess.get(prepared_url, headers=headers, timeout=2) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});", html)
                    if match:
                        data = json.loads(match.group(1))
                        formats = data.get("streamingData", {}).get("formats", []) + data.get("streamingData", {}).get("adaptiveFormats", [])
                        audio_cands = []
                        for f in formats:
                            if "audio" in f.get("mimeType", "").lower() and "url" in f:
                                audio_cands.append((_score_format(f, True), f["url"]))
                        if audio_cands:
                            audio_cands.sort(key=lambda x: x[0], reverse=True)
                            return audio_cands[0][1] # إرجاع أفضل جودة صوت
        except Exception as e:
            log.debug(f"Fast scrape failed: {e}")
        return None

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now + 3: return cached[1]

        # 🚀 1. المحاولة الأولى: السحب السريع الصاروخي
        if prefer_audio:
            fast_url = await self.fast_scrape(prepared)
            if fast_url:
                ok, _ = await _probe_url(fast_url)
                if ok:
                    exp = _parse_expire(fast_url) or (now + CACHE_DEFAULT_TTL)
                    async with _direct_cache_lock: _direct_cache[key] = (int(exp) - 3, fast_url)
                    log.info("⚡ Fast Scrape Success in 0.5s!")
                    return fast_url

        # 🐢 2. المحاولة التانية: الـ Fallback البطيء (لو الفيديو متشفّر)
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_info_blocking():
                ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "socket_timeout": YTDLP_SOCKET_TIMEOUT, "extractor_args": CLIENT_API_ARGS}
                if self.impersonate: ydl_opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception as e: return {"_err": str(e)}
            info = await loop.run_in_executor(self.pool, _extract_info_blocking)

        if not info or (isinstance(info, dict) and info.get("_err")):
            try:
                cmd = ["yt-dlp"] + CLIENT_ARGS + ["-g", "--no-warnings", "--force-ipv4", prepared]
                out, _err = await _exec_proc(*cmd, timeout=8)
                if out:
                    candidate = out.decode().splitlines()[0].strip()
                    ok, _ = await _probe_url(candidate)
                    if ok:
                        exp = _parse_expire(candidate) or (now + CACHE_DEFAULT_TTL)
                        async with _direct_cache_lock: _direct_cache[key] = (int(exp) - 3, candidate)
                        return candidate
            except Exception: pass
            return None

        fmts: List[dict] = info.get("formats") or []
        top_url = info.get("url")
        if top_url:
            ok, _ = await _probe_url(top_url)
            if ok:
                exp = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock: _direct_cache[key] = (int(exp) - 3, top_url)
                return top_url

        if not fmts:
            try:
                cmd = ["yt-dlp"] + CLIENT_ARGS + ["--dump-json", prepared, "--remote-components", "ejs:github", "--no-warnings"]
                out3, _ = await _exec_proc(*cmd, timeout=16)
                if out3: fmts = _loads_bytes(out3).get("formats") or []
            except Exception: fmts = []

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
            ok, _ = await _probe_url(cand)
            if ok:
                exp = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock: _direct_cache[key] = (int(exp) - 3, cand)
                return cand

        if not prefer_audio: return await self.get_direct_link(link, prefer_audio=True)
        return None

    async def download(self, link: str, mystic: Any, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> Tuple[Optional[str], bool]:
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        try:
            if videoid and str(videoid) not in ["True", "False"]: vid = str(videoid)
            elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0]
            elif "youtu.be/" in prepared: vid = prepared.split("youtu.be/")[1].split("?")[0]
            else: vid = str(int(time.time()))
        except Exception: vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024: return cand, False

        loop = asyncio.get_running_loop()

        if format_id:
            def _specific():
                try:
                    opts = {"format": (f"{format_id}+140" if songvideo else format_id), "outtmpl": f"{ram_base}.%(ext)s", "quiet": True, "force_ipv4": True, "extractor_args": CLIENT_API_ARGS}
                    if songaudio: opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                    if songvideo: opts["merge_output_format"] = "mp4"
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        path = ydl.prepare_filename(ydl.extract_info(prepared, download=True))
                        if songaudio and not path.endswith(".mp3"):
                            p = os.path.splitext(path)[0] + ".mp3"
                            if os.path.exists(p): return p
                        return path
                except Exception: return None
            res = await loop.run_in_executor(self.pool, _specific)
            return (res, False) if res else (None, False)

        try: direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception: direct = None

        if direct: return direct, True

        def _fallback():
            try:
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                ydl_opts = {"format": fmt, "outtmpl": f"{ram_base}.%(ext)s", "quiet": True, "force_ipv4": True, "extractor_args": CLIENT_API_ARGS, "prefer_ffmpeg": True}
                if not is_video: ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "192"}]
                else: ydl_opts["merge_output_format"] = "mp4"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    path = ydl.prepare_filename(ydl.extract_info(prepared, download=True))
                    if not is_video and not path.endswith(".mp3"):
                        mp3 = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3): return mp3
                    return path
            except Exception: return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded): return downloaded, False
        return None, False

    async def playlist(self, link, limit, user_id=None, videoid=None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = f"yt-dlp --extractor-args 'youtube:player_client=tv,android' -i --compat-options no-youtube-unavailable-videos --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try: result = [key for key in out.decode().split("\n") if key]
        except Exception: result = []
        return result

YouTube = YouTubeAPI()
