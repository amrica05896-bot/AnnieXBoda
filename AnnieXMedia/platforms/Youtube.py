# Authored By Certified Coders © 2026
# System: YouTubeAPI | Fixed Search Logic
# Fix: Removed Android client from Search Fallback (Causes conflict with cookies)
# Result: Search will always return results now.

import asyncio
import os
import re
import logging
import yt_dlp
from typing import Union, Tuple, Optional
from py_yt import VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from yt_dlp import YoutubeDL

try:
    from async_lru import alru_cache
except ImportError:
    def alru_cache(maxsize=128):
        def decorator(func):
            return func
        return decorator

try:
    from AnnieXMedia.utils.formatters import time_to_seconds, seconds_to_min
    from AnnieXMedia import LOGGER
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    def LOGGER(name): return logging.getLogger(name)
    def time_to_seconds(t): return 0
    def seconds_to_min(s): return str(s)

class Config:
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

def cookies():
    possible_paths = [
        Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
        "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.abspath(path)
    return None

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")

def asyncify(func):
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://www.youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    @asyncify
    def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset: break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None if offset in (None,) else text[offset : offset + length]

    @alru_cache(maxsize=500)
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        search = VideosSearch(link, limit=1)
        res = await asyncio.to_thread(search.result)
        
        if not res or not res.get("result"):
            return None

        result = res["result"][0]
        title = result["title"]
        duration_min = result["duration"]
        thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        vidid = result["id"]
        
        if str(duration_min) == "None":
            duration_sec = 0
        else:
            duration_sec = int(time_to_seconds(duration_min))
            
        return title, duration_min, duration_sec, thumbnail, vidid

    @alru_cache(maxsize=500)
    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            search = VideosSearch(link, limit=1)
            res = await asyncio.to_thread(search.result)
            
            if not res or not res.get("result"):
                raise ValueError("No result")

            result = res["result"][0]
            track_details = {
                "title": result["title"],
                "link": result["link"],
                "vidid": result["id"],
                "duration_min": result["duration"],
                "thumb": result["thumbnails"][0]["url"].split("?")[0],
            }
            return track_details, result["id"]
        except Exception:
            return await self._track_fallback(link)

    @asyncify
    def _track_fallback(self, q):
        # ✅ FIX: إزالة 'player_client': ['android'] من هنا
        # البحث العادي (Web) هو الأضمن لإيجاد النتائج
        options = {
            "format": "best",
            "noplaylist": True,
            "quiet": True,
            "extract_flat": "in_playlist",
            "cookiefile": cookies(),
            "remote_components": ["ejs:github"],
        }
        with YoutubeDL(options) as ydl:
            # استخدام ytsearch العادي
            info_dict = ydl.extract_info(f"ytsearch: {q}", download=False)
            if not info_dict.get("entries"):
                raise ValueError("No entries found")
            
            details = info_dict.get("entries")[0]
            info = {
                "title": details.get("title", "Unknown"),
                "link": details.get("url", f"https://www.youtube.com/watch?v={details['id']}"),
                "vidid": details["id"],
                "duration_min": (
                    seconds_to_min(details.get("duration", 0)) if details.get("duration") else "0:00"
                ),
                "thumb": details.get("thumbnails", [{}])[0].get("url", ""),
            }
            return info, details["id"]

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
        
        if videoid: link = self.base + link
        
        @asyncify
        def audio_dl():
            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": os.path.join(Config.DOWNLOAD_PATH, "%(id)s.%(ext)s"),
                "geo_bypass": True,
                "noplaylist": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookies(),
                "remote_components": ["ejs:github"],
            }
            with YoutubeDL(ydl_opts) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join(Config.DOWNLOAD_PATH, f"{info['id']}.{info['ext']}")
                if os.path.exists(xyz): return xyz
                x.download([link])
                return xyz

        @asyncify
        def video_dl():
            ydl_opts = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": os.path.join(Config.DOWNLOAD_PATH, "%(id)s.%(ext)s"),
                "geo_bypass": True,
                "noplaylist": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookies(),
                "remote_components": ["ejs:github"],
            }
            with YoutubeDL(ydl_opts) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join(Config.DOWNLOAD_PATH, f"{info['id']}.{info['ext']}")
                if os.path.exists(xyz): return xyz
                x.download([link])
                return xyz

        @asyncify
        def song_video_dl():
            ydl_opts = {
                "format": f"{format_id}+140",
                "outtmpl": os.path.join(Config.DOWNLOAD_PATH, f"%(id)s_{format_id}.%(ext)s"),
                "geo_bypass": True,
                "noplaylist": True,
                "nocheckcertificate": True,
                "quiet": True,
                "cookiefile": cookies(),
                "remote_components": ["ejs:github"],
            }
            with YoutubeDL(ydl_opts) as x:
                info = x.extract_info(link)
                filename = f"{info['id']}_{format_id}.mp4"
                return os.path.join(Config.DOWNLOAD_PATH, filename)

        @asyncify
        def song_audio_dl():
            ydl_opts = {
                "format": format_id,
                "outtmpl": os.path.join(Config.DOWNLOAD_PATH, f"%(id)s_{format_id}.%(ext)s"),
                "geo_bypass": True,
                "noplaylist": True,
                "nocheckcertificate": True,
                "quiet": True,
                "postprocessors": [{"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "192"}],
                "cookiefile": cookies(),
                "remote_components": ["ejs:github"],
            }
            with YoutubeDL(ydl_opts) as x:
                info = x.extract_info(link)
                filename = f"{info['id']}_{format_id}.mp3"
                return os.path.join(Config.DOWNLOAD_PATH, filename)

        if songvideo:
            return await song_video_dl(), False
        elif songaudio:
            return await song_audio_dl(), False
        elif video:
            downloaded_file = await video_dl()
            return downloaded_file, False
        else:
            # 🔥 البث المباشر (أندرويد سريع بدون كوكيز)
            try:
                cmd = [
                    "yt-dlp",
                    "-g",
                    "--extractor-args", "youtube:player_client=android", # هنا مفيش كوكيز، الأندرويد يشتغل تمام
                    "--remote-components", "ejs:github",
                    "-f", "bestaudio[ext=m4a]/bestaudio/best",
                    link
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if stdout:
                    direct_link = stdout.decode().split("\n")[0].strip()
                    return direct_link, True
                else:
                    return await audio_dl(), False
            except:
                return await audio_dl(), False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--extractor-args 'youtube:player_client=android' "
            f"--remote-components ejs:github "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        out = await shell_cmd(cmd)
        try: result = [key for key in out.split("\n") if key]
        except: result = []
        return result

    async def title(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("title")

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb")

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            search = VideosSearch(link, limit=5)
            res = await asyncio.to_thread(search.result)
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]
        except: return "Error", "0", "", "error"

    # دالة formats القديمة (مهمة لأزرار التحميل)
    @asyncify
    def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        ytdl_opts = {"quiet": True, "cookiefile": cookies()}
        with YoutubeDL(ytdl_opts) as ydl:
            formats_available = []
            try:
                r = ydl.extract_info(link, download=False)
                for format in r.get("formats", []):
                    formats_available.append({
                        "format": format["format"],
                        "filesize": format.get("filesize"),
                        "format_id": format["format_id"],
                        "ext": format["ext"],
                        "format_note": format.get("format_note", ""),
                        "yturl": link,
                    })
            except: pass
        return formats_available, link

YouTube = YouTubeAPI()
