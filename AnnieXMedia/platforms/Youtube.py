# Authored By Certified Systems Architect
# Youtube.py: The Ultimate Backend Engine (2026 Stack Edition)
# Stack: uvloop + curl_cffi + Internal yt-dlp + Aria2c + RAM Disk

import asyncio
import os
import re
import logging
import time
import json
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# استيراد yt-dlp كـ مكتبة داخلية
import yt_dlp
try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    logging.error("curl_cffi not installed! Install it for max speed.")
    AsyncSession = None

from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch

# إعداد السجلات
logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

try:
    from AnnieXMedia.utils.formatters import time_to_seconds
except ImportError:
    def time_to_seconds(t): return 0

class Config:
    # استخدام الرام ديسك
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieEngine"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_engine")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 16 

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

# كاش للبيانات
_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_cache_lock = asyncio.Lock()
YOUTUBE_META_TTL = 3600

def get_cookie_file():
    possible_paths = [
        Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
        "assets/cookies.txt", "platforms/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.abspath(path)
    return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    # --- 1. دالة track (تمت إعادتها لإصلاح الخطأ) ---
    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        async with _cache_lock:
            if link in _cache:
                ts, val = _cache[link]
                if time.time() - ts < YOUTUBE_META_TTL:
                    # استرجاع البيانات المخزنة بنفس تنسيق track القديم
                    return val[0], val[1]

        try:
            results = VideosSearch(link, limit=1)
            res = await results.next()
            if not res or not res.get("result"):
                raise ValueError("No Result")
            data = res["result"][0]
            
            thumb = data["thumbnails"][0]["url"].split("?")[0]
            for t in data["thumbnails"]:
                if "maxres" in t["url"]: thumb = t["url"].split("?")[0]

            track_details = {
                "title": data["title"],
                "link": data["link"],
                "vidid": data["id"],
                "duration_min": data["duration"],
                "thumb": thumb,
            }
            
            # حفظ في الكاش بصيغة تتوافق مع details و track
            async with _cache_lock:
                _cache[link] = (time.time(), (track_details, data["id"]))
            
            return track_details, data["id"]
        except Exception:
            return {"title": "Unknown", "link": link, "vidid": "error", "duration_min": "0:00", "thumb": ""}, "error"

    # --- 2. دالة details (تعتمد على track) ---
    async def details(self, link: str, videoid: Union[bool, str] = None):
        d, i = await self.track(link, videoid)
        if i == "error": return None
        # تحويل البيانات للشكل اللي البوت متعود عليه
        return d["title"], d["duration_min"], time_to_seconds(d["duration_min"]), d["thumb"], i

    # --- 3. دوال مساعدة إضافية ---
    async def title(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("title")

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb")

    # --- 4. تحميل الصورة (سريع جداً) ---
    async def download_thumb(self, url):
        if not url: return None
        try:
            if AsyncSession:
                async with AsyncSession(impersonate="chrome110") as session:
                    resp = await session.get(url)
                    if resp.status_code == 200:
                        path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        with open(path, "wb") as f:
                            f.write(resp.content)
                        return path
            else:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                            with open(path, "wb") as f:
                                f.write(await resp.read())
                            return path
        except Exception as e:
            return None

    # --- 5. المحرك الداخلي (Internal Engine) ---
    def _engine_task(self, link, final_path, is_video):
        try:
            ydl_opts = {
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "force_ipv4": True,
                "remote_components": ["ejs:github"],
            }

            if is_video:
                # Video: Aria2c Brute Force
                ydl_opts.update({
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "external_downloader": "aria2c",
                    "external_downloader_args": [
                        "-x", "16", "-s", "16", "-j", "16", "-k", "1M", 
                        "--file-allocation=none", "--disable-ipv6=true"
                    ]
                })
            else:
                # Audio: Native Instant
                ydl_opts.update({
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
                
        except Exception as e:
            print(f"Engine Crash: {e}")

    # --- 6. دالة التحميل الرئيسية ---
    async def download(
        self,
        link: str,
        mystic, 
        video: bool = False,
        videoid: str = None,
        title: str = None,
        **kwargs 
    ) -> Tuple[Optional[str], bool]:
        
        if videoid: link = self.base + link
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass
        
        loop = asyncio.get_running_loop()
        vid_id = str(int(time.time()))
        ext = "mp4" if video else "m4a"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False

        await loop.run_in_executor(
            self.pool, 
            self._engine_task, 
            link, 
            ram_path, 
            video
        )

        if os.path.exists(ram_path):
            return ram_path, False 
        
        base = ram_path.rsplit(".", 1)[0]
        for check_ext in [".m4a", ".mp3", ".mp4", ".webm", ".mkv"]:
             if os.path.exists(base + check_ext):
                 return base + check_ext, False
        
        return None, False

    # دوال التوافق
    async def url(self, message: Message) -> Union[str, None]:
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.URL:
                    return message.text[entity.offset : entity.offset + entity.length]
        return None

    async def playlist(self, link, limit, user_id, videoid=None):
        if videoid: link = self.base + link
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}'"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [k for k in out.decode().split("\n") if k]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        ytdl_opts = {"quiet": True, "cookiefile": get_cookie_file()}
        loop = asyncio.get_running_loop()
        
        def _get_fmt():
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                try:
                    r = ydl.extract_info(link, download=False)
                    return [{
                        "format": f["format"],
                        "filesize": f.get("filesize"),
                        "format_id": f["format_id"],
                        "ext": f["ext"]
                    } for f in r.get("formats", [])]
                except: return []
        
        formats = await loop.run_in_executor(self.pool, _get_fmt)
        return formats, link

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
