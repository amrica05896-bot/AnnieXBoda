# file: AnnieXMedia/platforms/Youtube.py
# Authored: Certified Systems (2026)
# Unified Youtube backend: fast -g direct stream + background RAM cache + cookie support

import asyncio
import contextlib
import json
import os
import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
import aiohttp
from youtubesearchpython.aio import VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

# ---------- Configuration ----------
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
YTDLP_TIMEOUT = 12     # seconds for -g command
YOUTUBE_META_TTL = 3600

_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_cache: Dict[str, Tuple[float, Dict, str]] = {}
_cache_lock = asyncio.Lock()

logger = logging.getLogger("AnnieXMedia.Youtube")
logging.basicConfig(level=logging.ERROR)


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


# ---------- YouTube API ----------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self._url_re = re.compile(r"(?:youtube\.com|youtu\.be)")
        self.pool = _pool

    # extract URL from Pyrogram Message
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

    async def exists(self, link: str, videoid: Union[bool, str, None] = None) -> bool:
        if videoid:
            link = self.base + str(videoid)
        return bool(self._url_re.search(str(link)))

    # track/details via VideosSearch with a fallback to yt-dlp --dump-json
    async def track(self, link: str, videoid: Union[bool, str] = None) -> Tuple[Dict, str]:
        prepared = self._prepare_link(link, videoid)
        key = f"q:{prepared}"
        now = time.time()

        async with _cache_lock:
            if key in _cache:
                ts, val, vid = _cache[key]
                if now - ts < YOUTUBE_META_TTL:
                    return val, vid
                _cache.pop(key, None)

        # try youtubesearchpython
        try:
            res = await VideosSearch(prepared, limit=1).next()
            results = res.get("result", []) if isinstance(res, dict) else []
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

        # fallback: yt-dlp --dump-json
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

    # download thumbnail (curl_cffi optional fallback to aiohttp)
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url:
            return None
        path = os.path.join(DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
        # try aiohttp (fast enough)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=20) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        with open(path, "wb") as f:
                            f.write(data)
                        return path
        except Exception:
            return None
        return None

    # formats: uses yt_dlp to list formats
    async def formats(self, link: str, videoid: Union[bool, str] = None) -> Tuple[List[Dict], str]:
        prepared = link if not videoid else (self.base + str(videoid))
        ytdl_opts = {"quiet": True}
        if cf := get_cookie_file():
            ytdl_opts["cookiefile"] = cf
        out: List[Dict] = []
        loop = asyncio.get_running_loop()

        def _get_formats():
            try:
                with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=False)
                    fmts = []
                    for fmt in info.get("formats", []):
                        fmts.append({
                            "format": fmt.get("format"),
                            "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                            "format_id": str(fmt.get("format_id")),
                            "ext": fmt.get("ext"),
                            "format_note": fmt.get("format_note", "")
                        })
                    return fmts
            except Exception:
                return []
        out = await loop.run_in_executor(self.pool, _get_formats)
        return out, prepared

    # slider: multi-result search
    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None) -> Tuple[str, str, str, str]:
        prepared = link if not videoid else (self.base + str(videoid))
        try:
            a = VideosSearch(prepared, limit=5)
            res = await a.next()
            results = res.get("result", [])
            if not results:
                return "Error", "0", "", "error"
            r = results[query_type] if query_type < len(results) else results[0]
            thumb = (r.get("thumbnails") or [{}])[-1].get("url", "")
            return r.get("title", ""), r.get("duration", ""), thumb.split("?")[0], r.get("id", "")
        except Exception:
            return "Error", "0", "", "error"

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

    # ---------- get_direct_link using yt-dlp -g (fast) ----------
    async def get_direct_link(self, link: str, *, prefer_audio: bool = False) -> Optional[str]:
        prepared = self._prepare_link(link)
        if not prepared:
            return None
        cookie = get_cookie_file()
        # build command: yt-dlp -g --force-ipv4 --extractor-args youtube:player_client=web -f ...
        cmd = ["yt-dlp", "-g", "--force-ipv4"]
        if cookie:
            cmd += ["--cookies", cookie]
        # preferred format: audio-first for calls
        if prefer_audio:
            cmd += ["-f", "bestaudio[ext=m4a]/bestaudio"]
        else:
            # video streams that are likely multiplexed; fallback selection helps reduce missing formats
            cmd += ["-f", "bestaudio[ext=m4a]/best[ext=mp4]/best"]
        cmd += ["--extractor-args", "youtube:player_client=web", prepared]
        out, err = await _exec_proc(*cmd, timeout=YTDLP_TIMEOUT)
        if out:
            try:
                return out.decode().splitlines()[0].strip()
            except Exception:
                return None
        return None

    # background download to RAM (blocking; runs in executor)
    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            fmt = "bestaudio[ext=m4a]/best" if not is_video else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
            ydl_opts = {
                "format": fmt,
                "outtmpl": out_template,
                "cookiefile": get_cookie_file(),
                "quiet": True,
                "force_ipv4": True,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
                "prefer_ffmpeg": True,
                "writethumbnail": True,
                "addmetadata": True,
                # network tuning
                "concurrent_fragment_downloads": 8,
                "buffersize": "64K",
                "socket_timeout": 30,
                "retries": 3,
                "fragment_retries": 3,
            }
            # use aria2c for large video files if available
            ydl_opts.update({
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
            })
            if not is_video:
                ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception as e:
            logger.debug(f"background_download error: {e}")

    # helper to get ffmpeg input args for pytgcalls/stream (adds reconnect params)
    def get_ffmpeg_input_args(self, url: str) -> List[str]:
        # these options are suitable for ffmpeg input to reduce latency and auto-reconnect
        args = [
            "-hide_banner", "-loglevel", "warning",
            "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-i", url
        ]
        return args

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
        Returns: (path_or_direct_url_or_None, direct_flag_bool)
        direct_flag True => returned value is a direct URL (good for streaming/pytgcalls)
        direct_flag False => returned value is a local file path (downloaded)
        """
        is_video = bool(video or songvideo)
        prepared = self._prepare_link(link, videoid)
        if not prepared:
            return None, False

        # compute vid id
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

        # 1) check RAM cache quickly
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            try:
                if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                    return cand, False
            except Exception:
                continue

        loop = asyncio.get_running_loop()

        # 2) if format_id provided -> download specific format (blocking in executor)
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

        # 3) try direct link fast-path
        try:
            direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        except Exception:
            direct = None

        if direct:
            # schedule background cache after 10 seconds
            def _delayed_cache():
                try:
                    time.sleep(10)
                    out_template = f"{ram_base}.%(ext)s"
                    self._background_download(prepared, out_template, is_video)
                except Exception:
                    pass
            loop.run_in_executor(self.pool, _delayed_cache)
            return direct, True

        # 4) fallback: download to RAM immediately (blocking in executor)
        def _fallback():
            try:
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
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
                    ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
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
                logger.debug(f"fallback download error: {e}")
                return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded):
            return downloaded, False

        return None, False


# exported instance
YouTube = YouTubeAPI()
