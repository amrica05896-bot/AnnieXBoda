# file: AnnieXMedia/platforms/Youtube.py
# System: Robust YouTube Core (2026 Edition)
# Fix: Multi-Layer Fallback restored to fix Live Stream / Deciphering failures (AssistantErr)

import asyncio
import contextlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# 🔥 ORJSON for Speed
try:
    import orjson
    def _loads_bytes(b: bytes): return orjson.loads(b)
except ImportError:
    import json
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

from youtubesearchpython.aio import VideosSearch

log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# Config
MAX_YTDLP_THREADS = 20
MAX_CONCURRENT_EXTRACTS = 10
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
_download_locks: Dict[str, asyncio.Lock] = {}

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 15) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception): proc.kill()
        return b"", b"timeout"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    try:
        if isinstance(videoid, str) and len(videoid) == 11 and not " " in videoid:
            return f"https://www.youtube.com/watch?v={videoid}"
    except: pass
    if not link: return ""
    link = link.strip()
    if " " in link or not link.startswith(("http", "www", "youtu")): return f"ytsearch:{link}"
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params: return int(params["expire"][0])
    except: pass
    return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = None  # Force No-Cookies
        try:
            import curl_cffi
            self.impersonate_target = "chrome"
        except:
            self.impersonate_target = None

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if not link: return False
        if videoid: link = self.base + link
        if re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link): return True
        if re.search(r"^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*", link): return True
        return False

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    if ent.type.name == "URL": return text[ent.offset : ent.offset + ent.length].split("&si")[0]
                    if ent.type.name == "TEXT_LINK": return ent.url.split("&si")[0]
                except: continue
        return None

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            search = VideosSearch(query, limit=limit)
            res = await search.next()
            results = []
            for item in res.get("result", []):
                dur = item.get("duration")
                if not dur: dur = "Live"
                results.append({
                    "title": item.get("title"), "vidid": item.get("id"),
                    "duration_string": dur, "thumb": item.get("thumbnails")[0]["url"].split("?")[0]
                })
            if results: return results
        except: pass

        cmd = ["yt-dlp", "--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
        out, _ = await _exec_proc(*cmd, timeout=12)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({
                        "title": data.get("title", "Unknown"),
                        "vidid": data.get("id", ""),
                        "duration_string": "Live"
                    })
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

        try:
            if "ytsearch" not in prepared:
                search = VideosSearch(prepared, limit=1)
                res = (await search.next())["result"][0]
                dur = res.get("duration")
                if not dur or str(dur).lower() in ["live", "stream", "none"]: dur = "Live"
                details = {
                    "title": res.get("title", ""), "link": res.get("link", prepared),
                    "vidid": res.get("id", ""), "duration_min": dur,
                    "thumb": res.get("thumbnails")[0]["url"].split("?")[0]
                }
                async with _meta_cache_lock: _meta_cache[key] = (now, details, res.get("id"))
                return details, res.get("id")
        except: pass

        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True,
            "impersonate": self.impersonate_target
        }
        loop = asyncio.get_running_loop()
        def _get_meta():
            with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(prepared, download=False)
            
        try:
            info = await loop.run_in_executor(self.pool, _get_meta)
            if info:
                is_live = info.get("is_live") or info.get("was_live")
                dur = "Live" if is_live else info.get("duration_string", "00:00")
                details = {
                    "title": info.get("title", ""), "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""), "duration_min": dur,
                    "thumb": (info.get("thumbnail") or "").split("?")[0]
                }
                async with _meta_cache_lock: _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
        except: pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "00:00", "thumb": ""}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None):
        data, vid = await self.track(link, videoid)
        if vid == "": raise ValueError("Video not found")
        dur = data.get("duration_min", "00:00")
        sec = 0 if str(dur).lower() == "live" else self._to_seconds(dur)
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
        if not results: raise ValueError("No results")
        idx = query_type % len(results)
        item = results[idx]
        return item["title"], item["duration_string"], item["thumb"], item["vidid"]

    def _to_seconds(self, t: Any) -> int:
        if not t: return 0
        try:
            parts = [int(float(p)) for p in str(t).split(":")]
            return sum(x * 60**i for i, x in enumerate(reversed(parts)))
        except: return 0

    # 🚀🚀🚀 MULTI-LAYER DIRECT LINK EXTRACTOR (Fixes AssistantErr) 🚀🚀🚀
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1. RAM CACHE
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()

            # LAYER 1: Ultra-Fast Android Client (Often fails on live streams)
            def _fast_extract():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "socket_timeout": 5, 
                    "format": "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                    "impersonate": self.impersonate_target,
                    "extractor_args": {"youtube": {"player_client": ["android", "ios"], "player_skip": ["webpage", "configs", "js"]}}
                }
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=False)
                        if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                        for f in info.get("formats", []):
                            if f.get("url") and f.get("protocol", "").startswith(("http", "m3u8")): return f["url"]
                except: return None

            direct_url = await loop.run_in_executor(self.pool, _fast_extract)

            # LAYER 2: Robust Web Client (Rescue for Live Streams)
            if not direct_url:
                def _robust_extract():
                    opts = {
                        "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "socket_timeout": 10,
                        "format": "bestaudio/best" if prefer_audio else "best[height<=720]/best",
                        "impersonate": self.impersonate_target,
                        "extractor_args": {"youtube": {"player_client": ["web"]}} # Full Deciphering
                    }
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(prepared, download=False)
                            if 'url' in info and info['url'].startswith(("http", "m3u8")): return info['url']
                            for f in info.get("formats", []):
                                if f.get("url") and f.get("protocol", "").startswith(("http", "m3u8")): return f["url"]
                    except Exception as e:
                        log.debug(f"Robust Fallback Error: {e}")
                        return None
                
                direct_url = await loop.run_in_executor(self.pool, _robust_extract)

        if direct_url:
            expiry = _parse_expire(direct_url) or (now + CACHE_DEFAULT_TTL)
            async with _direct_cache_lock:
                _direct_cache[key] = (expiry - 5, direct_url)
            return direct_url

        return None

    # 📥 Download / Streaming Entry Point
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str, None] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)

        try:
            if videoid: vid = str(videoid)
            elif "v=" in prepared: vid = prepared.split("v=")[1].split("&")[0]
            else: vid = str(int(time.time()))
        except: vid = str(int(time.time()))

        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False

        # Live Stream & Fast Stream Bypass
        if not format_id and not songaudio and not songvideo:
            try:
                # We ALWAYS try direct link first. It handles both Live and Normal.
                direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
                if direct: return direct, True
            except: pass

        if vid not in _download_locks: _download_locks[vid] = asyncio.Lock()
        
        async with _download_locks[vid]:
            for ext in (".mp4", ".m4a", ".mp3", ".webm"):
                cand = f"{ram_base}{ext}"
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False

            loop = asyncio.get_running_loop()
            
            def _dl_worker():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "impersonate": self.impersonate_target,
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                
                if format_id:
                    opts["format"] = f"{format_id}+140" if songvideo else format_id
                elif is_video:
                    opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]"
                else:
                    opts["format"] = "bestaudio/best"
                    opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]

                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=True)
                        fname = ydl.prepare_filename(info)
                        if not is_video and not songvideo and not fname.endswith(".mp3"):
                            return fname.rsplit(".", 1)[0] + ".mp3"
                        return fname
                except Exception as ex:
                    log.error(f"Download Engine Failed: {repr(ex)}")
                    return None

            try:
                fpath = await loop.run_in_executor(self.pool, _dl_worker)
                if fpath and os.path.exists(fpath): return fpath, False
            except Exception as e:
                log.warning(f"Download Worker Exception: {e}")

            # ULTIMATE RESCUE FALLBACK -> Avoid returning None, False
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
            if direct: return direct, True
            
            return None, False

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + str(videoid)
        if "&" in link: link = link.split("&")[0]
        cmd = [
            "yt-dlp", "--flat-playlist", "--print", "id",
            "--playlist-end", str(limit), "--skip-download",
            link
        ]
        out, _ = await _exec_proc(*cmd, timeout=20)
        if out: return [vid.strip() for vid in out.decode().splitlines() if vid.strip()]
        return []

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        ytdl_opts = {"quiet": True, "impersonate": self.impersonate_target}
        out: List[Dict[str, Any]] = []
        try:
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(prepared, download=False)
                for fmt in info.get("formats", []):
                    out.append({
                        "format": fmt.get("format"),
                        "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                        "format_id": str(fmt.get("format_id")),
                        "ext": fmt.get("ext"),
                        "format_note": fmt.get("format_note", ""),
                    })
        except: pass
        return out, prepared

# Export
YouTube = YouTubeAPI()
