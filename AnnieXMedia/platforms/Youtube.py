# file: AnnieXMedia/platforms/Youtube.py
# Author: Certified Fixes 2026 (Ultra-fast tuned copy)
# Purpose: fast -g direct stream (via yt_dlp API) + background RAM caching + yt-dlp tuning
# Notes:
#  - direct link cache to avoid re-parsing formats for repeated requests
#  - prefer progressive muxed formats for immediate playback in calls
#  - limit formats scanned for performance
#  - head-check for link validity before returning direct link
#  - background RAM caching with aria2c (non-blocking)
#  - safe fallbacks to yt-dlp -g subprocess extraction

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
YTDLP_TIMEOUT = 12
YOUTUBE_META_TTL = 3600
DIRECT_LINK_TTL = 300      # cache direct links for 5 minutes
FORMAT_SCAN_LIMIT = 30     # scan up to top N candidate formats for ranking

_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_cache: Dict[str, Tuple[float, Dict, str]] = {}
_direct_cache: Dict[str, Tuple[float, str]] = {}
_cache_lock = asyncio.Lock()
_direct_lock = asyncio.Lock()

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
    except Exception:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"error"

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

async def _head_ok(url: str, timeout: int = 4) -> bool:
    # quick HEAD/GET fallback to check url liveliness
    if not url:
        return False
    try:
        async with aiohttp.ClientSession() as sess:
            # try HEAD first
            try:
                async with sess.head(url, timeout=timeout, allow_redirects=True) as resp:
                    if resp.status == 200:
                        return True
                    # some servers block HEAD; try GET small range
            except Exception:
                pass
            try:
                headers = {"Range": "bytes=0-1023"}
                async with sess.get(url, headers=headers, timeout=timeout, allow_redirects=True) as resp:
                    return resp.status in (200, 206)
            except Exception:
                return False
    except Exception:
        return False

# ---------- YouTubeAPI ----------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self._url_re = re.compile(r"(?:youtube\.com|youtu\.be)")
        self.pool = _pool

    # ----- prepare/normalize link -----
    def _prepare_link(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        try:
            if videoid:
                return self.base + str(videoid)
            if not link:
                return ""
            link = str(link).strip()
            if "youtu.be/" in link:
                return self.base + link.split("/")[-1].split("?")[0]
            if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
                return self.base + link.split("/")[-1].split("?")[0]
            return link.split("&")[0]
        except Exception:
            return ""

    # ----- extract URL from a Pyrogram Message -----
    async def url(self, message: Message) -> Optional[str]:
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
                    if ent.type == MessageEntityType.URL:
                        return text[ent.offset: ent.offset + ent.length].split("&si")[0]
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url.split("&si")[0]
                except Exception:
                    continue
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

        # try youtubesearchpython first (fast)
        results = []
        try:
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", [])
        except Exception:
            results = []

        if results:
            try:
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
            except Exception:
                pass

        # fallback to yt-dlp --dump-json (safe)
        cookie = get_cookie_file()
        cmd = ["yt-dlp"]
        if cookie:
            cmd += ["--cookies", cookie]
        cmd += ["--dump-json", prepared]
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
            except Exception:
                pass

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": cookie}, ""

    async def details(self, link: str, videoid: Union[bool, str] = None) -> Tuple[str, Optional[str], int, str, str]:
        d, vid = await self.track(link, videoid)
        if vid == "":
            raise ValueError("Video not found")
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
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=20) as resp:
                    if resp.status == 200:
                        path = os.path.join(DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        data = await resp.read()
                        with open(path, "wb") as f:
                            f.write(data)
                        return path
        except Exception:
            return None
        return None

    # return ffmpeg input args recommended for low-latency streaming
    def ffmpeg_stream_args(self) -> List[str]:
        return [
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-fflags", "+nobuffer",
            "-flags", "low_delay",
        ]

    # formats (yt-dlp extract_info)
    async def formats(self, link: str, videoid: Union[bool, str] = None) -> Tuple[List[Dict], str]:
        prepared = link if not videoid else (self.base + str(videoid))
        ytdl_opts = {"quiet": True}
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
        except Exception:
            pass
        return out, prepared

    # ---------- get_direct_link using yt_dlp API (fast) ----------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = False) -> Optional[str]:
        prepared = self._prepare_link(link)
        if not prepared:
            return None

        now = time.time()
        # check direct cache first
        async with _direct_lock:
            if prepared in _direct_cache:
                ts, url = _direct_cache[prepared]
                if now - ts < DIRECT_LINK_TTL:
                    # verify quickly that url still works (non-blocking check)
                    ok = await _head_ok(url, timeout=2)
                    if ok:
                        return url
                    else:
                        # stale: drop cache
                        _direct_cache.pop(prepared, None)

        cookie = get_cookie_file()
        loop = asyncio.get_running_loop()

        # try to extract via yt-dlp python API (fast)
        def _extract_info():
            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "best",
                "noplaylist": True,
                "socket_timeout": 8,
            }
            if cookie:
                opts["cookiefile"] = cookie
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(prepared, download=False)
            except Exception as e:
                return {"_extract_err": str(e)}

        info = await loop.run_in_executor(self.pool, _extract_info)

        # fallback to subprocess -g if API failed
        if not info or (isinstance(info, dict) and info.get("_extract_err")):
            try:
                cmd = ["yt-dlp", "-g", "--force-ipv4", "--no-warnings"]
                if cookie:
                    cmd += ["--cookies", cookie]
                if prefer_audio:
                    cmd += ["-f", "bestaudio[ext=m4a]/bestaudio"]
                else:
                    cmd += ["-f", "best[ext=mp4]/best"]
                cmd += ["--extractor-args", "youtube:player_client=web", prepared]
                out, err = await _exec_proc(*cmd, timeout=10)
                if out:
                    candidate = out.decode().splitlines()[0].strip()
                    if await _head_ok(candidate, timeout=3):
                        async with _direct_lock:
                            _direct_cache[prepared] = (time.time(), candidate)
                        return candidate
            except Exception:
                pass
            return None

        # pick and rank formats quickly
        formats = info.get("formats") or []
        candidates: List[Tuple[int, Dict]] = []

        def rank(fmt: Dict) -> int:
            score = 0
            proto = (fmt.get("protocol") or "").lower()
            ext = (fmt.get("ext") or "").lower()
            vcodec = fmt.get("vcodec") or ""
            acodec = fmt.get("acodec") or ""
            # prefer https/http
            if proto.startswith("https"): score += 30
            if proto.startswith("http"): score += 20
            # prefer mp4/m4a/webm
            if ext == "mp4": score += 12
            elif ext in ("m4a", "webm"): score += 8
            # prefer muxed (have both codecs) for video playback
            if vcodec and vcodec != "none" and acodec and acodec != "none":
                score += 40
            # prefer audio-only for prefer_audio
            if prefer_audio and (acodec and acodec != "none"):
                score += 15
            # bitrate/resolution boost
            br = fmt.get("tbr") or fmt.get("abr") or 0
            try:
                score += int(br) // 100
            except Exception:
                pass
            # deprioritize DASH-only fragmented
            if "dash" in proto and (vcodec == "none" or acodec == "none"):
                score -= 50
            return score

        # filter to useful protocols and non-empty urls
        good_formats = [f for f in formats if f.get("url") and (f.get("protocol") or "").lower().startswith(("http", "https", "m3u8", "mms"))]
        # limit scanning size for speed
        if len(good_formats) > FORMAT_SCAN_LIMIT:
            good_formats = good_formats[:FORMAT_SCAN_LIMIT]

        for f in good_formats:
            candidates.append((rank(f), f))
        candidates.sort(key=lambda x: x[0], reverse=True)

        # validate top candidates quickly
        for score, fmt in candidates:
            if score < 0:
                continue
            url = fmt.get("url")
            if not url:
                continue
            # if prefer_audio ensure audio exists
            if prefer_audio:
                ac = fmt.get("acodec") or ""
                if ac == "none":
                    continue
            else:
                # prefer muxed (both audio & video)
                v = fmt.get("vcodec") or ""
                a = fmt.get("acodec") or ""
                if not (v != "none" and a != "none"):
                    # accept progressive mp4/m4a if fallback
                    if (fmt.get("ext") or "").lower() not in ("mp4", "m4a"):
                        continue
            # quick head check to ensure valid
            ok = await _head_ok(url, timeout=2)
            if ok:
                async with _direct_lock:
                    _direct_cache[prepared] = (time.time(), url)
                return url

        # last resort: try any format url
        for f in formats:
            url = f.get("url")
            if url and await _head_ok(url, timeout=2):
                async with _direct_lock:
                    _direct_cache[prepared] = (time.time(), url)
                return url

        return None

    # background downloader to RAM (blocking)
    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-j", "8", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            ydl_opts = {
                "format": fmt,
                "outtmpl": out_template,
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "force_ipv4": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
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

    # ---------- download (primary) ----------
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
        """
        Return (path_or_direct_url_or_None, is_direct_flag)
        """
        is_video = bool(video or songvideo)
        prepared = self._prepare_link(link, videoid)

        # compute vid id (for RAM filename)
        try:
            if videoid:
                vid = str(videoid)
            elif "v=" in prepared:
                vid = prepared.split("v=")[1].split("&")[0]
            elif "youtu.be/" in prepared:
                vid = prepared.split("youtu.be/")[1].split("?")[0]
            else:
                vid = str(int(time.time()))
        except Exception:
            vid = str(int(time.time()))

        ram_base = os.path.join(DOWNLOAD_PATH, vid)

        # 1) check RAM cache
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            try:
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False
            except Exception:
                continue

        loop = asyncio.get_running_loop()

        # 2) format_id specific download (requested by user via buttons)
        if format_id:
            def _specific():
                try:
                    aria2_args = ["-x", "16", "-k", "1M", "--disable-ipv6=true"]
                    opts = {
                        "format": (f"{format_id}+140" if songvideo else format_id),
                        "outtmpl": f"{ram_base}.%(ext)s",
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "force_ipv4": True,
                        "extractor_args": {"youtube": {"player_client": ["web"]}},
                        "external_downloader": "aria2c",
                        "external_downloader_args": aria2_args,
                    }
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

        # 3) try direct link fast-path (cached & validated)
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception:
            direct = None

        if direct:
            # schedule background cache after ~8s (non-blocking)
            def _delayed_cache():
                try:
                    time.sleep(8)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True

        # 4) fallback: download to RAM immediately (blocking in threadpool)
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
                    "prefer_ffmpeg": True,
                }
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
            except Exception as e:
                log.warning("fallback download failed: %s", e)
                return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded):
            return downloaded, False

        return None, False

    # playlist & slider helpers
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try:
            result = [key for key in out.decode().split("\n") if key]
        except Exception:
            result = []
        return result

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            a = VideosSearch(link, limit=5)
            res = await a.next()
            if not res or not res.get("result"): return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]
        except Exception:
            return "Error", "0", "", "error"

# exported instance
YouTube = YouTubeAPI()
