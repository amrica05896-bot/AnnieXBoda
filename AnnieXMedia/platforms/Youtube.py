# تم التطوير بواسطة مهندس أنظمة معتمد
# Youtube.py: المحرك الخلفي الأقوى (إصدار 2026)
# التقنيات: uvloop + curl_cffi + Internal yt-dlp + Aria2c + RAM Disk

import asyncio
import os
import re
import logging
import time
import json
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# استيراد yt-dlp كـ مكتبة داخلية (لإلغاء وقت الإقلاع)
import yt_dlp

# محاولة استيراد curl_cffi للسرعة القصوى في جلب الصور
try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    logging.error("curl_cffi مش موجودة! سطبها عشان تاخد أقصى سرعة.")
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
    # ⚡ استخدام الرام ديسك إجباري ⚡
    # بنرمي الملفات في الرام (/dev/shm) عشان سرعة الكتابة تكون خرافية
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieEngine"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_engine")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    # استغلال الـ 16 كور بتوع السيرفر
    MAX_WORKERS = 16 

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

# نظام كاش (Cache) عشان منطلبش نفس المعلومة مرتين من يوتيوب
_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_cache_lock = asyncio.Lock()
YOUTUBE_META_TTL = 3600

def get_cookie_file():
    """دالة لجلب ملف الكوكيز بأمان"""
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
        # مجمع الخيوط (ThreadPool) عشان يشيل الحمل عن البوت الرئيسي
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    # --- 1. البحث وجلب البيانات (Metadata) ---
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        # فحص الكاش الأول (للسرعة)
        async with _cache_lock:
            if link in _cache:
                ts, val = _cache[link]
                if time.time() - ts < YOUTUBE_META_TTL:
                    return val[0], val[1]

        try:
            results = VideosSearch(link, limit=1)
            res = await results.next()
            if not res or not res.get("result"): return None
            data = res["result"][0]
            
            # جلب الصورة بأعلى دقة ممكنة
            thumb = data["thumbnails"][0]["url"].split("?")[0]
            for t in data["thumbnails"]:
                if "maxres" in t["url"]: thumb = t["url"].split("?")[0]

            duration_sec = time_to_seconds(data["duration"])
            
            track_details = {
                "title": data["title"],
                "link": data["link"],
                "vidid": data["id"],
                "duration_min": data["duration"],
                "duration_sec": duration_sec,
                "thumb": thumb,
            }
            
            # حفظ في الكاش للمرة الجاية
            async with _cache_lock:
                _cache[link] = (time.time(), (track_details["title"], track_details["duration_min"], duration_sec, thumb, track_details["vidid"]))
            
            return track_details["title"], track_details["duration_min"], duration_sec, thumb, track_details["vidid"]
        except:
            return None

    # --- 2. تحميل الصورة باستخدام curl_cffi (التقنية الجديدة) ---
    async def download_thumb(self, url):
        if not url: return None
        try:
            # هنا بنستخدم curl_cffi عشان نخدع السيرفر إننا متصفح كروم
            # ده بيمنع أي حظر وبيخلي التحميل طلقة
            if AsyncSession:
                async with AsyncSession(impersonate="chrome110") as session:
                    resp = await session.get(url)
                    if resp.status_code == 200:
                        path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        with open(path, "wb") as f:
                            f.write(resp.content)
                        return path
            else:
                # خطة بديلة لو curl_cffi مش موجودة
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                            with open(path, "wb") as f:
                                f.write(await resp.read())
                            return path
        except Exception as e:
            print(f"Thumb Error: {e}")
            return None

    # --- 3. المنطق الداخلي للمحرك (Internal Engine Logic) ---
    def _engine_task(self, link, final_path, is_video):
        try:
            # إعدادات ثابتة (إجبار IPv4 وحل ألغاز JS)
            ydl_opts = {
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "force_ipv4": True, # مهم جداً في الداتا سنتر لتجنب الحظر
                "remote_components": ["ejs:github"], # الاعتماد على Deno/Node من الدوكر
            }

            if is_video:
                # 🔥 وضع الفيديو: استخدام Aria2c (بقوة 16 ماسورة) 🔥
                # هنا بنستدعي Aria2c عشان يفتح 16 اتصال ويملأ الـ Bandwidth كله
                ydl_opts.update({
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "external_downloader": "aria2c",
                    "external_downloader_args": [
                        "-x", "16", "-s", "16", "-j", "16", "-k", "1M", 
                        "--file-allocation=none", "--disable-ipv6=true"
                    ]
                })
            else:
                # ⚡ وضع الصوت: استخدام التحميل الداخلي (Native) ⚡
                # هنا لغينا Aria2c واستخدمنا Native لأنه بيبدأ في "لحظة"
                # مش محتاجين نفتح اتصالات كتير لملف صوتي صغير
                ydl_opts.update({
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                })

            # 🛑 السر هنا: استخدام الكلاس مباشرة داخل البروسيس
            # ده بيلغي وقت الإقلاع اللي كان بيضيع في subprocess.run
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
                
        except Exception as e:
            print(f"Engine Crash: {e}")

    # --- 4. دالة التحميل الرئيسية ---
    async def download(
        self,
        link: str,
        mystic, 
        video: bool = False,
        videoid: str = None,
        title: str = None,
        **kwargs 
    ) -> Tuple[Optional[str], bool]:
        
        # تنظيف الرابط
        if videoid: link = self.base + link
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass
        
        loop = asyncio.get_running_loop()
        vid_id = str(int(time.time()))
        ext = "mp4" if video else "m4a"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

        # 1. فحص الكاش في الرام (هل الملف موجود؟)
        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False

        # 2. تشغيل المحرك الداخلي
        # استخدام run_in_executor عشان yt-dlp كود Blocking
        # بس بما إنه Internal Call مش System Call، هيكون سريع جداً
        await loop.run_in_executor(
            self.pool, 
            self._engine_task, 
            link, 
            ram_path, 
            video
        )

        # 3. التحقق من النتيجة
        if os.path.exists(ram_path):
            return ram_path, False 
        
        # فحص الامتدادات البديلة (احتياطي)
        base = ram_path.rsplit(".", 1)[0]
        for check_ext in [".m4a", ".mp3", ".mp4", ".webm", ".mkv"]:
             if os.path.exists(base + check_ext):
                 return base + check_ext, False
        
        return None, False

    # دوال التوافق مع البوت
    async def url(self, message: Message) -> Union[str, None]:
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.URL:
                    return message.text[entity.offset : entity.offset + entity.length]
        return None

    async def playlist(self, link, limit, user_id, videoid=None):
        if videoid: link = self.base + link
        # هنا بنستخدم subprocess لأنه خفيف جداً في جلب الـ IDs بس
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}'"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [k for k in out.decode().split("\n") if k]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        # استخدام Internal Class للجلب السريع للصيغ
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

YouTube = YouTubeAPI()
