# Authored By Certified 
# Fixed for platforms/Youtube.py
# NUCLEAR EDITION: 16-Core Aria2c Download + Instant Direct Stream + RAM Disk
# FIX: Sanitize URL before passing to yt-dlp

import asyncio
import os
import re
import logging
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import time
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch

try:
    from AnnieXMedia.utils.formatters import time_to_seconds
    from AnnieXMedia import LOGGER
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    def LOGGER(name): return logging.getLogger(name)
    def time_to_seconds(t): return 0

class Config:
    # استخدام الرام (Shm) للسرعة القصوى
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 16

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_cache_lock = asyncio.Lock()
YOUTUBE_META_TTL = 3600

def get_cookie_file():
    possible_paths = [
        Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
        "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.abspath(path)
    return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://www.youtube.com/playlist?list="
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
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

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        async with _cache_lock:
            if link in _cache:
                ts, val = _cache[link]
                if time.time() - ts < YOUTUBE_META_TTL:
                    return val[0], val[1]

        try:
            results = VideosSearch(link, limit=1)
            try: res = await results.next()
            except: res = results.result()

            if not res or not res.get("result"):
                raise ValueError("No Result")
            data = res["result"][0]
            
            thumb = data["thumbnails"][0]["url"].split("?")[0] if data.get("thumbnails") else ""
            
            track_details = {
                "title": data["title"],
                "link": data["link"],
                "vidid": data["id"],
                "duration_min": data["duration"],
                "thumb": thumb,
                "cookiefile": get_cookie_file(),
            }
            async with _cache_lock:
                _cache[link] = (time.time(), (track_details, data["id"]))
            return track_details, data["id"]
        except Exception:
            return {"title": "Unknown", "link": link, "vidid": "error", "duration_min": "0:00", "thumb": ""}, "error"

    async def details(self, link: str, videoid: Union[bool, str] = None):
        d, i = await self.track(link, videoid)
        if i == "error": return None
        return d["title"], d["duration_min"], time_to_seconds(d["duration_min"]), d["thumb"], i

    async def title(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("title")

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb")

    def _background_download(self, link, final_path, is_video):
        try:
            aria2_args = [
                "-x", "16", "-s", "16", "-j", "16", "-k", "1M",
                "--file-allocation=none", "--disable-ipv6=true"
            ]
            
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            
            ydl_opts = {
                "format": fmt,
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception:
            pass

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
        
        # ✅ FIX: إصلاح مشكلة الرابط الوهمي googleusercontent
        # إذا كان الرابط وهمي، نستخرج الـ ID ونحوله لرابط يوتيوب حقيقي
        if "googleusercontent.com" in link:
            try:
                # الرابط يكون في الغالب .../youtube.com/1[VID_ID]
                # الرقم 1 أو 5 هو الـ prefix، نحذفه ونأخذ الـ ID
                vid_part = link.split("youtube.com/")[-1]
                # إزالة الرقم الأول (1 أو 2 أو 5)
                real_vid_id = vid_part[1:] if vid_part[0].isdigit() else vid_part
                link = f"https://www.youtube.com/watch?v={real_vid_id}"
            except:
                pass # لو فشل التحويل، نتركه كما هو ونأمل خيرًا

        if videoid: 
            link = f"https://www.youtube.com/watch?v={videoid}"

        loop = asyncio.get_running_loop()

        # توليد ID للملف
        try:
            if "v=" in link: vid_id = link.split("v=")[1].split("&")[0]
            else: vid_id = str(int(time.time()))
        except: vid_id = str(int(time.time()))

        ext = "mp4" if (video or songvideo) else "m4a"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

        # 1. فحص الكاش
        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False

        # 2. تحديد الجودة (إذا طلب المستخدم جودة محددة عبر format_id)
        if format_id:
            # تحميل مباشر بالجودة المطلوبة (بدون بث مباشر لتفادي المشاكل مع الصيغ المحددة)
            def _specific_download():
                try:
                    ydl_opts = {
                        "format": f"{format_id}+140" if songvideo else format_id,
                        "outtmpl": ram_path,
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "external_downloader": "aria2c",
                        "external_downloader_args": ["-x", "16", "-k", "1M"],
                    }
                    if songaudio:
                        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3"}]
                        ram_path_mp3 = ram_path.replace(".m4a", ".mp3")
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([link])
                        return ram_path_mp3
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([link])
                    return ram_path
                except: return None
            
            dl_path = await loop.run_in_executor(self.pool, _specific_download)
            return dl_path, False

        # 3. البث المباشر (للحالات العامة)
        try:
            cmd = ["yt-dlp", "-g", "--cookies", get_cookie_file() or ""]
            if video:
                cmd.extend(["-f", "best[height<=720]"])
            else:
                cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio"])
            
            cmd.append(link)

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if stdout:
                direct_link = stdout.decode().split("\n")[0].strip()
                # بدء التحميل في الخلفية للكاش
                loop.run_in_executor(self.pool, self._background_download, link, ram_path, video)
                return direct_link, True
        except:
            pass

        # Fallback (التحميل العادي)
        def _fallback_download():
            try:
                fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if video else "bestaudio[ext=m4a]"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": ram_path,
                    "cookiefile": get_cookie_file(),
                    "quiet": True
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])
                return ram_path
            except: return None

        downloaded_file = await loop.run_in_executor(self.pool, _fallback_download)
        if downloaded_file:
            return downloaded_file, False
        
        return None, False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try: result = [key for key in out.decode().split("\n") if key]
        except: result = []
        return result

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        ytdl_opts = {"quiet": True, "cookiefile": get_cookie_file()}
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            formats_available = []
            try:
                r = ydl.extract_info(link, download=False)
                for format in r.get("formats", []):
                    formats_available.append({
                        "format": format["format"],
                        "filesize": format.get("filesize"),
                        "format_id": format["format_id"],
                        "ext": format["ext"],
                        "yturl": link,
                    })
            except: pass
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            a = VideosSearch(link, limit=5)
            try: res = await a.next()
            except: res = a.result()
            
            if not res or not res.get("result"): return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            thumb = r["thumbnails"][0]["url"].split("?")[0] if r.get("thumbnails") else ""
            return r["title"], r["duration"], thumb, r["id"]
        except: return "Error", "0", "", "error"

YouTube = YouTubeAPI()
