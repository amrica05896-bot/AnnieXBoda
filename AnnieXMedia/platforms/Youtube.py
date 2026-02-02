# Authored By Certified Systems Architect
# Youtube.py: The Ultimate Backend Engine (2026 Stack Edition)
# Stack: uvloop + curl_cffi + Internal yt-dlp + RAM Disk

import asyncio
import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Union, List, Dict, Tuple, Optional

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch

# محاولة تفعيل curl_cffi للسرعة القصوى
try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL = True
except ImportError:
    HAS_CURL = False
    logging.warning("curl_cffi not installed! Falling back to slower methods.")

# إعداد السجلات
logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

try:
    from AnnieXMedia.utils.formatters import time_to_seconds
except ImportError:
    def time_to_seconds(t): return 0

class Config:
    # الكشف عن الرام ديسك للاستغلال الفوري للـ 100 جيجا
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieEngine"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_engine")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    # زيادة عدد العمال ليستغل الـ 16 نواة بالكامل
    MAX_WORKERS = 32 

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

# كاش سريع جداً بدون أقفال (No Locks)
_cache: Dict[str, Tuple[float, Dict, str]] = {}
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

    # --- 1. دالة Track (سريعة وبدون انتظار) ---
    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        # فحص الكاش مباشرة (بدون Lock)
        if link in _cache:
            ts, data, vid = _cache[link]
            if time.time() - ts < YOUTUBE_META_TTL:
                return data, vid

        try:
            results = VideosSearch(link, limit=1)
            res = (await results.next())["result"]
            if not res:
                raise ValueError("No Result")
            data = res[0]
            
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
            
            # تحديث الكاش
            _cache[link] = (time.time(), track_details, data["id"])
            
            return track_details, data["id"]
        except Exception:
            return {"title": "Unknown", "link": link, "vidid": "error", "duration_min": "0:00", "thumb": ""}, "error"

    # --- 2. Wrapper للدوال القديمة ---
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

    # --- 3. تحميل الصور (استخدام curl_cffi) ---
    async def download_thumb(self, url):
        if not url: return None
        path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
        
        # الطريقة الأولى: curl_cffi (الأسرع)
        if HAS_CURL:
            try:
                async with AsyncSession(impersonate="chrome110") as session:
                    resp = await session.get(url)
                    if resp.status_code == 200:
                        with open(path, "wb") as f: f.write(resp.content)
                        return path
            except Exception: pass
        
        # الطريقة الثانية: aiohttp (بديل سريع)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f: f.write(await resp.read())
                        return path
        except: pass
        return None

    # --- 4. محرك التحميل الداخلي (القلب النابض) ---
    def _engine_task(self, link, final_path, is_video):
        try:
            ydl_opts = {
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "source_address": "0.0.0.0",
                # تحسينات الشبكة
                "concurrent_fragment_downloads": 10,
                "buffersize": 1024 * 64,
                "retries": 3,
                "socket_timeout": 10,
            }

            if is_video:
                # للفيديو: استخدم Aria2c للاستفادة من السرعة في الملفات الكبيرة
                ydl_opts.update({
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "external_downloader": "aria2c",
                    "external_downloader_args": [
                        "-x", "16", "-s", "16", "-j", "16", "-k", "1M", 
                        "--file-allocation=none", "--disable-ipv6=true"
                    ]
                })
            else:
                # للصوت: استخدم التحميل المباشر (Native) لبدء التشغيل الفوري
                # حذفنا Aria2c من هنا لأنها تضيف تأخير ثانيتين في البداية
                ydl_opts.update({
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
                
        except Exception as e:
            print(f"Engine Crash: {e}")

    # --- 5. دالة Download الرئيسية ---
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

        # فحص سريع إذا الملف موجود
        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False

        # إرسال المهمة للـ ThreadPool (لعدم تعطيل البوت)
        await loop.run_in_executor(
            self.pool, 
            self._engine_task, 
            link, 
            ram_path, 
            video
        )

        if os.path.exists(ram_path):
            return ram_path, False 
        
        # بحث احتياطي عن الامتدادات الأخرى
        base = ram_path.rsplit(".", 1)[0]
        for check_ext in [".m4a", ".mp3", ".mp4", ".webm", ".mkv"]:
             if os.path.exists(base + check_ext):
                 return base + check_ext, False
        
        return None, False

    # --- 6. دوال التوافق ---
    async def url(self, message: Message) -> Union[str, None]:
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.URL:
                    return message.text[entity.offset : entity.offset + entity.length]
        return None

    async def playlist(self, link, limit, user_id, videoid=None):
        if videoid: link = self.base + link
        # استخدام Shell Process لأنه أسرع في جلب قوائم التشغيل الكبيرة
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
