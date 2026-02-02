file: AnnieXMedia/platforms/Youtube.py

Authored By Certified Coders © 2026

System: Unified Youtube platform for AnnieXMedia

NUCLEAR EDITION: 16-Core Aria2c Download + Instant Direct Stream + RAM Disk

FEATURES: -g direct stream (yt-dlp) + --force-ipv4 + background RAM cache after 10s

web-only player_client, thumb downloader, formats, slider, track/details, url extractor

import asyncio import contextlib import json import os import re import time from typing import Dict, List, Optional, Tuple, Union from concurrent.futures import ThreadPoolExecutor

import aiohttp import yt_dlp from youtubesearchpython.aio import VideosSearch from pyrogram.enums import MessageEntityType from pyrogram.types import Message

---------------------- Configuration ----------------------

if os.path.exists("/dev/shm"): DOWNLOAD_PATH = "/dev/shm/AnnieDownloads" else: DOWNLOAD_PATH = os.path.abspath("downloads") os.makedirs(DOWNLOAD_PATH, exist_ok=True)

COOKIE_PATH_CANDIDATES = [ "AnnieXMedia/assets/cookies.txt", "cookies.txt", "AnnieXMedia/cookies.txt", "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt", ]

MAX_WORKERS = 16 YTDLP_TIMEOUT = 20 YOUTUBE_META_TTL = 3600

_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS) _cache: Dict[str, Tuple[float, Tuple[Dict, str]]] = {} _cache_lock = asyncio.Lock()

---------------------- Helpers ----------------------

def get_cookie_file() -> Optional[str]: for p in COOKIE_PATH_CANDIDATES: try: if os.path.exists(p) and os.path.getsize(p) > 0: return os.path.abspath(p) except Exception: continue return None

async def _exec_proc(*args: str, timeout: int = YTDLP_TIMEOUT) -> Tuple[bytes, bytes]: proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE) try: return await asyncio.wait_for(proc.communicate(), timeout=timeout) except asyncio.TimeoutError: with contextlib.suppress(Exception): proc.kill() return b"", b"timeout"

def _to_seconds(t: Optional[str]) -> int: if not t: return 0 try: parts = [int(p) for p in str(t).split(":")] s = 0 for p in parts: s = s * 60 + p return s except Exception: return 0

---------------------- YouTubeAPI ----------------------

class YouTubeAPI: def init(self): self.base = "https://www.youtube.com/watch?v=" self.listbase = "https://youtube.com/playlist?list=" self._url_re = re.compile(r"(?:youtube.com|youtu.be)") self.pool = _pool

# extract URL from pyrogram Message (entities / text_link)
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

# check if the link is youtube like
async def exists(self, link: str, videoid: Union[bool, str, None] = None) -> bool:
    if videoid:
        link = self.base + str(videoid)
    return bool(self._url_re.search(str(link)))

# track: returns details dict and vid id (used by details/title/etc.)
async def track(self, link: str, videoid: Union[bool, str] = None) -> Tuple[Dict, str]:
    prepared = self._prepare_link(link, videoid)
    key = f"q:{prepared}"
    now = time.time()

    async with _cache_lock:
        if key in _cache:
            ts, (val, vid) = _cache[key]
            if now - ts < YOUTUBE_META_TTL:
                return val, vid
            _cache.pop(key, None)

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
            _cache[key] = (now, (details, data.get("id", "")))
        return details, data.get("id", "")

    # fallback to yt-dlp --dump-json
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
                _cache[key] = (now, (details, info.get("id", "")))
            return details, info.get("id", "")
        except Exception:
            pass

    return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": "", "cookiefile": cookie}, ""

# details: returns tuple used by song.py
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

# download thumbnail and save locally (used by song.py)
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

# formats: list available formats (used by callback handler)
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

# slider: search many results (used by song.py)
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
    if prefer_audio:
        cmd += ["-f", "bestaudio[ext=m4a]/bestaudio"]
    else:
        cmd += ["-f", "best[height<=720]/best"]
    # ensure web client only (avoid android/iOS cookie issues)
    cmd += ["--extractor-args", "youtube:player_client=web", prepared]
    out, err = await _exec_proc(*cmd, timeout=12)
    if out:
        try:
            return out.decode().splitlines()[0].strip()
        except Exception:
            return None
    return None

# background download to RAM (blocking; intended to run in executor)
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
    except Exception:
        # best-effort background cache; swallow exceptions
        return

# ---------- download (primary function used by song.py) ----------
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
    Unified download function used by song.py.
    Returns: (path_or_direct_url_or_None, direct_flag_bool)
     - direct_flag True => returned value is a direct URL (suitable for streaming/pytgcalls)
     - direct_flag False => returned value is a local file path (downloaded)
    Behavior:
     1) If file exists in RAM cache -> return (local_path, False)
     2) If direct link available via yt-dlp -g -> return (direct_url, True)
        and schedule background download_to_ram after 10s
     3) If format_id provided -> download specific format to RAM and return (local_path, False)
     4) Fallback: download best audio/video to RAM and return (local_path, False)
    """
    is_video = bool(video or songvideo)
    prepared = self._prepare_link(link, videoid)

    # compute vid id and ram base
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

    # 1) check RAM cache for common extensions
    for ext in (".mp4", ".m4a", ".mp3", ".webm"):
        cand = f"{ram_base}{ext}"
        try:
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False
        except Exception:
            continue

    loop = asyncio.get_running_loop()

    # 2) if format_id is given -> download that specific format (blocking in executor)
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

    # 3) try direct link fast-path (yt-dlp -g)
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
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
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
        except Exception:
            return None

    downloaded = await loop.run_in_executor(self.pool, _fallback)
    if downloaded and os.path.exists(downloaded):
        return downloaded, False

    return None, False

exported instance for imports

YouTube = YouTubeAPI()
