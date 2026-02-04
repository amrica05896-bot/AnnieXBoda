# file: AnnieXMedia/platforms/Youtube.py
# Author: Certified Fixes 2026 (optimized get_direct_link via yt_dlp API)
# Purpose: fast -g direct stream (via yt_dlp API) + background RAM caching + yt-dlp tuning

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

# Tunables
MAX_WORKERS = 12
YTDLP_TIMEOUT = 10  # for subprocess calls
YOUTUBE_META_TTL = 3600  # cache metadata for 1 hour

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
    """Run a subprocess and return (stdout, stderr) with a timeout."""
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
        self.listbase = "https://youtube.com/playlist?list="
        self._url_re = re.compile(r"(?:youtube\.com|youtu\.be)")
        self.pool = _pool

    # ----- prepare/normalize link -----
    def _prepare_link(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        if videoid:
            return self.base + str(videoid)
        if not link:
            return ""
        link = link.strip()
        if "youtu.be/" in link:
            return self.base + link.split("/")[-1].split("?")[0]
        if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
            return self.base + link.split("/")[-1].split("?")[0]
        return link.split("&")[0]

    # ----- extract URL from a Pyrogram Message -----
    async def url(self, message: Message) -> Optional[str]:
        """
        Return the URL string found in message entities or caption_entities
        or in replied-to message. Returns None if not found.
        """
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
        try:
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", [])
        except Exception:
            results = []

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

        # fallback to yt-dlp --dump-json (rare)
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
        """
        Use yt_dlp Python API to extract formats and choose a progressive/muxed URL fast.
        Returns a direct URL (string) or None.
        Strategy:
          1) Try yt_dlp API in threadpool (fast, no subprocess)
          2) If API returns no usable progressive HTTP URL, use subprocess -g as LAST RESORT (only once)
        """
        prepared = self._prepare_link(link)
        if not prepared:
            return None

        cookie = get_cookie_file()
        loop = asyncio.get_running_loop()

        def _extract_info():
            opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                # prefer HTTP progressive formats to avoid DASH/MPEG-TS complexities
                "format": (
                    "bestaudio[protocol^=http]/bestaudio"
                    if prefer_audio else
                    "best[protocol^=http]/best"
                ),
                "socket_timeout": 6,
                "extractor_args": {"youtube": {"player_client": ["web"], "player_skip": ["android", "android_tv", "ios"]}},
            }
            if cookie:
                opts["cookiefile"] = cookie
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=False)
                    return info
            except Exception as e:
                return {"_extract_err": str(e)}

        info = await loop.run_in_executor(self.pool, _extract_info)

        # If extractor errored, try subprocess -g fallback (rare)
        if not info or (isinstance(info, dict) and info.get("_extract_err")):
            log.debug("yt-dlp API extractor failed or returned no info: %s", info)
            # Last-resort fallback to -g (subprocess). Keep minimal flags and web client enforced.
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4"]
                if cookie:
                    cmd += ["--cookies", cookie]
                if prefer_audio:
                    cmd += ["-f", "bestaudio[ext=m4a]/bestaudio"]
                else:
                    cmd += ["-f", "best[ext=mp4]/best"]
                # ensure web client
                cmd += ["--extractor-args", "youtube:player_client=web", prepared]
                out, err = await _exec_proc(*cmd, timeout=8)
                if out:
                    return out.decode().splitlines()[0].strip()
            except Exception as e:
                log.debug("subprocess -g fallback failed: %s", e)
            return None

        # choose best candidate from formats
        formats = info.get("formats") or []
        candidates = []

        def rank(fmt: Dict) -> int:
            score = 0
            proto = (fmt.get("protocol") or "") or ""
            ext = (fmt.get("ext") or "").lower()
            vcodec = fmt.get("vcodec") or ""
            acodec = fmt.get("acodec") or ""
            # prefer https/http
            if proto.startswith("https"): score += 30
            if proto.startswith("http"): score += 20
            # prefer muxed (audio+video)
            if vcodec and vcodec != "none" and acodec and acodec != "none":
                score += 40
            # prefer audio-only when requested
            if prefer_audio and (acodec and acodec != "none"):
                score += 15
            # prefer common container types
            if ext in ("mp4",): score += 10
            if ext in ("m4a", "webm"): score += 8
            # bitrate/resolution proxy
            br = fmt.get("tbr") or fmt.get("abr") or 0
            try:
                score += int(br) // 100
            except Exception:
                pass
            return score

        for f in formats:
            if not f.get("url"):
                continue
            proto = (f.get("protocol") or "").lower()
            # accept typical progressive protocols; prefer http/https
            if proto.startswith(("https", "http", "m3u8")):
                candidates.append((rank(f), f))

        candidates.sort(key=lambda x: x[0], reverse=True)

        # pick a candidate that suits the request
        for score, fmt in candidates:
            url = fmt.get("url")
            if not url:
                continue
            if prefer_audio:
                if (fmt.get("acodec") or "") != "none":
                    return url
                continue
            else:
                # prefer muxed
                if (fmt.get("vcodec") or "") != "none" and (fmt.get("acodec") or "") != "none":
                    return url
                # accept high-quality audio-only as fallback for audio streaming
                if (fmt.get("acodec") or "") != "none" and fmt.get("ext") in ("m4a", "webm", "mp3"):
                    return url
                # accept progressive mp4
                if (fmt.get("ext") or "").lower() == "mp4":
                    return url

        # last resort: return first available url
        for f in formats:
            if f.get("url"):
                return f.get("url")

        return None

    # background downloader to RAM (blocking)
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

        # compute vid
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

        # 2) format_id specific download
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

        # 3) try direct link fast-path (yt_dlp API)
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception as e:
            log.debug("get_direct_link exception: %s", e)
            direct = None

        if direct:
            # schedule background cache after ~10s (non-blocking)
            def _delayed_cache():
                try:
                    time.sleep(10)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True

        # 4) fallback: download to RAM immediately
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
