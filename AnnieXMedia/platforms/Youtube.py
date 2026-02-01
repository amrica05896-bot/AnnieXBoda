# Authored By Certified 
# Fixed for platforms/Youtube.py
# NUCLEAR EDITION: 16-Core Aria2c + iOS Spoofing + Smart Format Merge
# FIX: Added missing 'asyncify' decorator definition

import asyncio
import os
import re
import logging
import aiohttp
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

# ✅ الدالة التي كانت ناقصة وتسببت في الخطأ
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

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        # تنظيف الروابط الوهمية
        if "googleusercontent.com" in link:
            try:
                vid_id = link.split("youtube.com/")[-1]
                vid_id = re.sub(r'^\d+', '', vid_id)
                link = f"https://www.youtube.com/watch?v={vid_id}"
            except: pass

        try:
            results = VideosSearch(link, limit=1)
            try: res = await results.next()
            except: res = results.result()

            if not res or not res.get("result"): return None
            data = res["result"][0]
            
            thumb = data["thumbnails"][0]["url"].split("?")[0] if data.get("thumbnails") else ""
            vidid = data["id"]
            
            # حساب المدة بالثواني
            duration_text = data.get("duration", "0")
            duration_sec = int(time_to_seconds(duration_text)) if duration_text else 0
            
            return data["title"], duration_text, duration_sec, thumb, vidid
        except: return None

    # تحميل الصورة (لحل مشكلة Errno 2)
    async def download_thumb(self, url):
        if not url: return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
        except: return None
        return None

    # 🔥 التحميل الخلفي (مع Aria2c + iOS + دمج الصيغ) 🔥
    def _background_download(self, link, final_path, is_video):
        try:
            aria2_args = [
                "-x", "16", "-s", "16", "-j", "16", "-k", "1M",
                "--file-allocation=none", "--disable-ipv6=true"
            ]
            
            # إزالة [ext=mp4] لتجنب خطأ التنسيق، نعتمد على الدمج
            fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]" if is_video else "bestaudio/best"
            
            ydl_opts = {
                "format": fmt,
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
            }
            
            if is_video:
                ydl_opts["merge_output_format"] = "mp4" # تحويل أي صيغة لـ mp4
            else:
                ydl_opts["postprocessors"] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]

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
        
        # 1. تنظيف الرابط
        if "googleusercontent.com" in link:
            try:
                real_id = link.split("youtube.com/")[-1]
                if real_id[0].isdigit() and len(real_id) > 11: real_id = real_id[1:]
                link = f"https://www.youtube.com/watch?v={real_id}"
            except: pass
        
        if videoid: link = f"https://www.youtube.com/watch?v={videoid}"

        loop = asyncio.get_running_loop()

        # توليد ID ومسار
        try:
            if "v=" in link: vid_id = link.split("v=")[1].split("&")[0]
            else: vid_id = str(int(time.time()))
        except: vid_id = str(int(time.time()))

        ext = "mp4" if (video or songvideo) else "mp3"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}") 

        # 2. تحميل محدد الجودة (أزرار)
        if format_id:
            def _specific_download():
                try:
                    aria2_args = ["-x", "16", "-k", "1M", "--disable-ipv6=true"]
                    ydl_opts = {
                        "format": f"{format_id}+140" if songvideo else format_id,
                        "outtmpl": f"{ram_path}.%(ext)s",
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
                        "external_downloader": "aria2c",
                        "external_downloader_args": aria2_args,
                    }
                    if songaudio:
                        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3"}]
                    elif songvideo:
                        ydl_opts["merge_output_format"] = "mp4"

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(link, download=True)
                        return ydl.prepare_filename(info)
                except: return None
            
            dl_path = await loop.run_in_executor(self.pool, _specific_download)
            return dl_path, False

        # 3. البث المباشر (Direct Stream)
        try:
            cmd = [
                "yt-dlp", "-g",
                "--cookies", get_cookie_file() or "",
                "--extractor-args", "youtube:player_client=ios",
            ]
            
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
                # تشغيل التحميل في الخلفية
                loop.run_in_executor(self.pool, self._background_download, link, f"{ram_path}.%(ext)s", video)
                return direct_link, True
        except:
            pass

        # 4. Fallback (التحميل العادي)
        def _fallback_download():
            try:
                # فلتر مرن يقبل أي صيغة ثم يحولها
                fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]" if video else "bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_path}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "extractor_args": {"youtube": {"player_client": ["ios", "web"]}}
                }
                
                if video:
                    ydl_opts["merge_output_format"] = "mp4"
                else:
                    ydl_opts["postprocessors"] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    expected_path = ydl.prepare_filename(info)
                    
                    if video and expected_path.endswith(".webm"):
                         return expected_path
                    if not video:
                        return expected_path.rsplit(".", 1)[0] + ".mp3"
                    return expected_path

            except Exception as e: 
                print(f"Fallback Error: {e}")
                return None

        downloaded_file = await loop.run_in_executor(self.pool, _fallback_download)
        if downloaded_file and os.path.exists(downloaded_file):
            return downloaded_file, False
        
        return None, False

    @asyncify
    def formats(self, link: str, videoid: Union[bool, str] = None):
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
                        "format_note": format.get("format_note", ""),
                        "yturl": link,
                    })
            except: pass
        return formats_available, link

YouTube = YouTubeAPI()
