# file: AnnieXMedia/platforms/Youtube.py
# Author: Certified Fixes 2026 (iOS Client + Speed Semaphore Edition)
# Purpose: Fix "Skipping client" errors, maintain 4K/HQ speed, prevent server crash

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

log = logging.getLogger("AnnieXMedia.YouTube")
log.setLevel(logging.INFO)

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
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"

def _to_seconds(t: Optional[str]) -> int:
    if not t:
        return 0
    try:
        parts = [int(p) for p in str(t).split(":")]
        s = 0
        for p in parts:
            s = s * 60 + p
        return s
    except Exception:
        return 0

def _now_key(q: str) -> str:
    return "q:" + (q or "")

# ---------- YouTubeAPI ----------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://www.youtube.com/playlist?list="
        self._url_re = re.compile(r"(?:youtube\.com|youtu\.be)")
        self.pool = _pool
        
        # ⚡ SEMAPHORE: Balance between SPEED and STABILITY
        # Allows 10 concurrent downloads (High Speed) but prevents infinite queuing (Crash prevention)
        self.sem = asyncio.Semaphore(10)

    # ----- prepare/normalize link -----
    def _prepare_link(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        if videoid:
            return self.base + str(videoid)
        if not link:
            return ""
        link = link.strip()
        
        # Clean old proxy links
        if "googleusercontent.com" in link:
            try:
                if "v=" in link:
                    return self.base + link.split("v=")[1].split("&")[0]
                elif "/0" in link or "/8" in link:
                    return self.base + link.split("/")[-1].split("?")[0]
            except:
                pass
                
        if "&" in link and "v=" in link:
            return link.split("&")[0]
            
        return link

    # ----- extract URL from a Pyrogram Message -----
    async def url(self, message: Message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None):
            msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    if ent.type == MessageEntityType.URL:
                        return text[ent.offset: ent.offset + ent.length].split("&si")[0]
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url.split("&si")[0]
                except: continue
        return None

    # ----- track/details (cache-friendly) -----
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

        try:
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", [])
        except: results = []

        if results:
            data = results[0]
            thumb = (data.get("thumbnails") or [{}])[-1].get("url", "")
            details = {
                "title": data.get("title", ""),
                "link": data.get("link", prepared),
                "vidid": data.get("id", ""),
                "duration_min": data.get("duration"),
                "thumb": thumb.split("?")[0],
                "cookiefile": get_cookie_file(),
            }
            async with _cache_lock:
                _cache[key] = (now, details, data.get("id", ""))
            return details, data.get("id", "")

        # Fallback to yt-dlp (iOS Client for Speed + Cookies)
        cookie = get_cookie_file()
        cmd = ["yt-dlp", "--dump-json", prepared]
        if cookie: cmd += ["--cookies", cookie]
        # 🔥 iOS Client: Supports Cookies, High Quality, and avoids 'Skipping Client' warning
        cmd += ["--extractor-args", "youtube:player_client=ios,web"]
        
        out, err = await _exec_proc(*cmd, timeout=15)
        if out:
            try:
                info = json.loads(out.decode(errors="ignore"))
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", ""),
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": info.get("duration"),
                    "thumb": thumb,
                    "cookiefile": cookie,
                }
                async with _cache_lock:
                    _cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except: pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": cookie}, ""

    async def details(self, link: str, videoid: Union[bool, str] = None) -> Tuple[str, Optional[str], int, str, str]:
        d, vid = await self.track(link, videoid)
        dur = d.get("duration_min")
        sec = int(_to_seconds(dur)) if dur else 0
        return d.get("title", ""), dur, sec, d.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("title", "")

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
                async with session.get(url, timeout=20) as resp:
                    if resp.status == 200:
                        path = os.path.join(DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        data = await resp.read()
                        with open(path, "wb") as f: f.write(data)
                        return path
        except: return None
        return None

    def ffmpeg_stream_args(self) -> List[str]:
        return ["-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5", "-fflags", "+nobuffer", "-flags", "low_delay"]

    async def formats(self, link: str, videoid: Union[bool, str] = None) -> Tuple[List[Dict], str]:
        prepared = self._prepare_link(link, videoid)
        ytdl_opts = {
            "quiet": True,
            # 🔥 Fix: Use iOS instead of Android (Android conflicts with Cookies)
            "extractor_args": {"youtube": {"player_client": ["ios", "web"]}}
        }
        if cf := get_cookie_file():
            ytdl_opts["cookiefile"] = cf
        out: List[Dict] = []
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
        except: pass
        return out, prepared

    # ---------- get_direct_link (Smart Fallback) ----------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = False) -> Optional[str]:
        """
        Fast path: tries to get a direct URL without downloading.
        Uses iOS client to maximize success rate with cookies.
        """
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
                # 🔥 FIX: iOS first, Web second. No Android.
                "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
                "socket_timeout": 15
            }
            if cookie: opts["cookiefile"] = cookie
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=False)
                    return info
            except Exception as e: return {"_extract_err": str(e)}

        # Use semaphore only for heavy downloads, direct link is light enough to pass
        info = await loop.run_in_executor(self.pool, _extract_info)
        
        # Fallback to subprocess
        if not info or isinstance(info, dict) and info.get("_extract_err"):
            try:
                cmd = ["yt-dlp", "-g", "--force-ipv4", "--no-warnings"]
                if cookie: cmd += ["--cookies", cookie]
                if prefer_audio:
                    cmd += ["-f", "bestaudio[ext=m4a]/bestaudio/best"]
                else:
                    cmd += ["-f", "best[ext=mp4]/best"]
                
                cmd += ["--extractor-args", "youtube:player_client=ios,web", prepared]
                
                out, err = await _exec_proc(*cmd, timeout=12)
                if out: return out.decode().splitlines()[0].strip()
            except: pass
            return None

        formats = info.get("formats") or []
        candidates = []

        def rank(fmt):
            score = 0
            proto = fmt.get("protocol", "") or ""
            ext = (fmt.get("ext") or "").lower()
            vcodec = fmt.get("vcodec") or ""
            acodec = fmt.get("acodec") or ""
            if proto.startswith("https"): score += 30
            if ext in ("mp4", "m4a"): score += 10
            if vcodec != "none" and acodec != "none": score += 40
            if prefer_audio and acodec != "none": score += 15
            try: score += int(fmt.get("tbr") or 0) // 100
            except: pass
            return score

        for f in formats:
            if not f.get("url"): continue
            if (f.get("protocol") or "").startswith(("http", "m3u8")):
                candidates.append((rank(f), f))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for score, fmt in candidates:
            url = fmt.get("url")
            if prefer_audio:
                if fmt.get("acodec") != "none": return url
            else:
                if fmt.get("vcodec") != "none" and fmt.get("acodec") != "none": return url
                if fmt.get("ext") == "mp4": return url
        
        if candidates: return candidates[0][1]["url"]
        return None

    # background downloader (RAM Cache)
    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            ydl_opts = {
                "format": fmt,
                "outtmpl": out_template,
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "force_ipv4": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
                # 🔥 FIX: iOS Client
                "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
                "prefer_ffmpeg": True,
                "writethumbnail": True,
                "addmetadata": True,
            }
            if not is_video:
                ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception as e:
            log.warning("background cache failed: %s", e)

    # ---------- download (Smart Config with Semaphore) ----------
    async def download(
        self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None, title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        is_video = bool(video or songvideo)
        prepared = self._prepare_link(link, videoid)
        try: vid = str(videoid) if videoid else str(int(time.time()))
        except: vid = str(int(time.time()))
        ram_base = os.path.join(DOWNLOAD_PATH, vid)

        # 1. RAM Cache Check
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False

        loop = asyncio.get_running_loop()
        
        # 2. Helper to run actual download
        def _dl_exec():
            try:
                # 🔥 Flexible Format: Fixes 'Requested format not available'
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "force_ipv4": True,
                    # 🔥 iOS + Web (No Android to avoid cookie skipping)
                    "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
                    "prefer_ffmpeg": True,
                }
                if not is_video:
                    ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                else:
                    ydl_opts["merge_output_format"] = "mp4"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    if not is_video and not path.endswith(".mp3"):
                        mp3 = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3): return mp3
                    return path
            except Exception as e:
                log.warning("download failed: %s", e)
                return None

        # 3. Execution with Semaphore (Speed with Safety)
        # Allows 10 concurrent downloads to keep it fast but safe
        async with self.sem:
            downloaded = await loop.run_in_executor(self.pool, _dl_exec)
            
        if downloaded and os.path.exists(downloaded): return downloaded, False

        # 4. Fallback to Direct Link if Download Failed
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
            if direct:
                # Schedule background cache
                def _delayed_cache():
                    try:
                        time.sleep(5)
                        out_tmpl = f"{ram_base}.%(ext)s"
                        self._background_download(prepared, out_tmpl, is_video)
                    except: pass
                loop.run_in_executor(self.pool, _delayed_cache)
                return direct, True
        except: pass

        return None, False

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        # 🔥 FIX: iOS client for playlist fetching
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--extractor-args 'youtube:player_client=ios,web' "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try:
            result = [key for key in out.decode().split("\n") if key]
        except: result = []
        return result

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
