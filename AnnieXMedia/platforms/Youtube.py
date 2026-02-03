# file: AnnieXMedia/platforms/Youtube.py
# Author: Certified Fixes 2026 (Alexa Killer Edition)
# Features: 
#   - Robust Error Handling (No crashes).
#   - Direct Stream Priority (Speed).
#   - Background RAM Caching.

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch

# إعداد اللوجر
log = logging.getLogger("AnnieXMedia.YouTube")
log.setLevel(logging.ERROR)

# ---------- Config ----------
if os.path.exists("/dev/shm"):
    DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
else:
    DOWNLOAD_PATH = os.path.abspath("downloads")
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

COOKIE_PATH_CANDIDATES = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

MAX_WORKERS = 16
YTDLP_TIMEOUT = 15
YOUTUBE_META_TTL = 3600

_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_cache: Dict[str, Tuple[float, Dict, str]] = {}
_cache_lock = asyncio.Lock()

# ---------- Helpers ----------
def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATH_CANDIDATES:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None

async def _exec_proc(*args: str, timeout: int = YTDLP_TIMEOUT) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"
    except Exception:
        return b"", b"error"

def _to_seconds(t: Optional[str]) -> int:
    if not t: return 0
    try:
        parts = [int(p) for p in str(t).split(":")]
        s = 0
        for p in parts: s = s * 60 + p
        return s
    except: return 0

def _now_key(q: str) -> str:
    return "q:" + (str(q) or "")

# ---------- YouTubeAPI ----------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _pool

    def _prepare_link(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        try:
            if videoid: return self.base + str(videoid)
            if not link: return ""
            link = str(link).strip()
            if "googleusercontent.com" in link:
                 try: return self.base + link.split("/")[-1].split("?")[0]
                 except: pass
            return link.split("&")[0]
        except:
            return ""

    # ----- Safe URL Extraction -----
    async def url(self, message: Message) -> Optional[str]:
        if not message: return None
        try:
            msgs = [message]
            if getattr(message, "reply_to_message", None):
                msgs.append(message.reply_to_message)
            
            for msg in msgs:
                text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
                entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
                
                for ent in entities:
                    if ent.type == MessageEntityType.URL:
                        return text[ent.offset: ent.offset + ent.length].split("&si")[0]
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url.split("&si")[0]
        except Exception:
            pass
        return None

    # ----- 1. Track & Details (Guaranteed Return) -----
    async def track(self, link: str, videoid: Union[bool, str] = None) -> Tuple[Dict, str]:
        prepared = self._prepare_link(link, videoid)
        key = _now_key(prepared)
        now = time.time()

        async with _cache_lock:
            if key in _cache:
                ts, data, vid = _cache[key]
                if now - ts < YOUTUBE_META_TTL:
                    return data, vid
                _cache.pop(key, None)

        # 1. Try python lib (Fastest)
        try:
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", [])
        except: results = []

        if results:
            try:
                data = results[0]
                thumb = (data.get("thumbnails") or [{}])[-1].get("url", "").split("?")[0]
                details = {
                    "title": data.get("title", "Unknown"),
                    "link": data.get("link", prepared),
                    "vidid": data.get("id", ""),
                    "duration_min": data.get("duration"),
                    "thumb": thumb,
                    "cookiefile": get_cookie_file(),
                }
                async with _cache_lock:
                    _cache[key] = (now, details, data.get("id", ""))
                return details, data.get("id", "")
            except: pass

        # 2. Fallback to yt-dlp json (Slower but accurate)
        cookie = get_cookie_file()
        cmd = ["yt-dlp", "--dump-json", "--no-warnings", prepared]
        if cookie: cmd.insert(1, f"--cookies={cookie}")
        
        out, _ = await _exec_proc(*cmd, timeout=12)
        if out:
            try:
                info = json.loads(out.decode(errors="ignore"))
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", "Unknown"),
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": info.get("duration_string"),
                    "thumb": thumb,
                    "cookiefile": cookie,
                }
                async with _cache_lock:
                    _cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except: pass

        # Return empty safe values on failure
        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "0:00", "thumb": ""}, ""

    async def details(self, link: str, videoid: Union[bool, str] = None):
        d, vid = await self.track(link, videoid)
        if not vid: return None # Safe None return
        return d.get("title", "Unknown"), d.get("duration_min"), _to_seconds(d.get("duration_min")), d.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("title", "Unknown")

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        path = os.path.join(DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        with open(path, "wb") as f: f.write(await resp.read())
                        return path
        except: return None

    # ---------- 2. Smart Direct Link (Alexa Speed) ----------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = False) -> Optional[str]:
        prepared = self._prepare_link(link)
        if not prepared: return None

        cookie = get_cookie_file()
        loop = asyncio.get_running_loop()

        def _extract_info():
            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best",
                "noplaylist": True,
                "force_ipv4": True,
                "geo_bypass": True,
                "socket_timeout": 10,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            if cookie: opts["cookiefile"] = cookie
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(prepared, download=False)
            except: return None

        info = await loop.run_in_executor(self.pool, _extract_info)
        
        # Fallback to subprocess if internal fails
        if not info:
            try:
                cmd = ["yt-dlp", "-g", "--force-ipv4", "--no-warnings"]
                if cookie: cmd += ["--cookies", cookie]
                if prefer_audio: cmd += ["-f", "bestaudio[ext=m4a]/bestaudio"]
                else: cmd += ["-f", "best[ext=mp4][protocol^=http]"]
                cmd.append(prepared)
                out, _ = await _exec_proc(*cmd, timeout=10)
                if out: return out.decode().splitlines()[0].strip()
            except: pass
            return None

        # Smart Ranking
        formats = info.get("formats") or []
        candidates = []

        def rank(fmt):
            score = 0
            proto = (fmt.get("protocol") or "").lower()
            ext = (fmt.get("ext") or "").lower()
            vcodec = fmt.get("vcodec") or "none"
            acodec = fmt.get("acodec") or "none"
            
            if proto.startswith("http") and "dash" not in proto: score += 50
            if proto.startswith("https"): score += 10
            if ext == "mp4": score += 20
            elif ext == "m4a": score += 10
            
            # Video needs Muxed (Video+Audio)
            if not prefer_audio and vcodec != "none" and acodec != "none": score += 100
            # Audio needs Audio codec
            if prefer_audio and acodec != "none" and vcodec == "none": score += 50
            
            return score

        for f in formats:
            if not f.get("url"): continue
            candidates.append((rank(f), f))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for score, fmt in candidates:
            if not prefer_audio and score < 100: continue
            return fmt.get("url")

        return formats[0].get("url") if formats else None

    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-k", "1M", "--file-allocation=none"]
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            ydl_opts = {
                "format": fmt,
                "outtmpl": out_template,
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "force_ipv4": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except: pass

    # ---------- 3. Master Download ----------
    async def download(
        self,
        link: str,
        mystic, 
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        is_video = bool(video or songvideo)
        prepared = self._prepare_link(link, videoid)
        
        # 1. Custom Format (Button Selection) - Force Download
        if format_id:
            vid = str(int(time.time()))
            ram_path = os.path.join(DOWNLOAD_PATH, f"{vid}.%(ext)s")
            loop = asyncio.get_running_loop()
            
            def _dl_specific():
                try:
                    aria = ["-x", "16", "-k", "1M"]
                    opts = {
                        "format": (f"{format_id}+140" if songvideo else format_id),
                        "outtmpl": ram_path,
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "force_ipv4": True,
                        "external_downloader": "aria2c",
                        "external_downloader_args": aria,
                    }
                    if songaudio: opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
                    if songvideo: opts["merge_output_format"] = "mp4"
                    
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(prepared, download=True)
                        return ydl.prepare_filename(info)
                except: return None

            path = await loop.run_in_executor(self.pool, _dl_specific)
            # Fix mp3 extension mismatch
            if path and songaudio and not path.endswith(".mp3"):
                mp3 = os.path.splitext(path)[0] + ".mp3"
                if os.path.exists(mp3): path = mp3
            
            return (path, False) if path else (None, False)

        # 2. Smart Direct Stream (The Alexa Way)
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
            if direct:
                # Cache in background for next time
                vid = str(int(time.time()))
                out = os.path.join(DOWNLOAD_PATH, f"{vid}.%(ext)s")
                asyncio.get_running_loop().run_in_executor(self.pool, self._background_download, prepared, out, is_video)
                return direct, True
        except: pass

        # 3. Fallback RAM Download
        vid = str(int(time.time()))
        ram_base = os.path.join(DOWNLOAD_PATH, vid)
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
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                if not is_video: ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
                else: ydl_opts["merge_output_format"] = "mp4"
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    return ydl.prepare_filename(info)
            except: return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        
        # Extension fix for fallback
        if downloaded and not is_video and not downloaded.endswith(".mp3"):
             mp3 = os.path.splitext(downloaded)[0] + ".mp3"
             if os.path.exists(mp3): downloaded = mp3

        if downloaded and os.path.exists(downloaded):
            return downloaded, False

        return None, False

    # Playlist & Slider
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}'"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [k for k in out.decode().split("\n") if k]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        ytdl_opts = {"quiet": True, "cookiefile": get_cookie_file()}
        try:
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                r = ydl.extract_info(link, download=False)
                return [{
                    "format": f["format"],
                    "filesize": f.get("filesize"),
                    "format_id": f["format_id"],
                    "ext": f["ext"]
                } for f in r.get("formats", [])]
        except: return []

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            a = VideosSearch(link, limit=5)
            res = await a.next()
            if not res or not res.get("result"): return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]
        except: return "Error", "0", "", "error"

YouTube = YouTubeAPI()
