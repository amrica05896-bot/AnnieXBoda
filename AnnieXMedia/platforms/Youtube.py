# Authored By Certified Systems Architect
# Youtube.py: Dedicated Engine for MUSIC PLAYER (/play, /vplay)
# NUCLEAR EDITION: 16-Core Aria2c + Native Low-Latency + RAM Disk

import asyncio
import os
import re
import logging
import aiohttp
import time
import yt_dlp
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
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
    # --- تحسين التخزين (Storage Optimization) ---
    # نستخدم الرام ديسك (/dev/shm) لتخزين ملفات التشغيل المؤقتة
    # هذا يمنع التقطيع (Buffering) تماماً لأن سرعة الرام أسرع 100 مرة من الهارد
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnniePlayerCache"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_player")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    # استغلال الـ 16 كور في المعالجة
    MAX_WORKERS = 16

# التأكد من وجود مسار الكاش
if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

# نظام كاش ذكي
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
        self.listbase = "https://www.youtube.com/playlist?list="
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    # --- دوال البحث والمعلومات (Metadata) ---

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
            res = await results.next()
            if not res or not res.get("result"):
                raise ValueError("No Result")
            data = res["result"][0]
            
            # جلب أعلى جودة للصورة
            thumb = data["thumbnails"][0]["url"].split("?")[0]
            
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
    
    async def download_thumb(self, url):
        """تحميل الصورة للرام لاستخدامها في البلاير"""
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

    # --- 🔥 المحرك النووي (Hybrid Player Engine) 🔥 ---
    # يقرر بذكاء: هل نستخدم Native (للصوت) أم Aria2 (للفيديو)؟
    
    def _player_download_task(self, link, final_path, is_video):
        try:
            # إعدادات 2026: تخطي الحظر، تسريع IPv4، انتحال Android
            ydl_opts = {
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "force_ipv4": True, # تفادي مشاكل IPv6 في الداتا سنتر
                "remote_components": ["ejs:github"], # حل ألغاز JS
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            if is_video:
                # --- وضع الفيديو (/vplay) ---
                # نستخدم Aria2c بـ 16 اتصال لأن الفيديو حجمه كبير وبيحتاج سرعة نقل عالية
                ydl_opts.update({
                    "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
                    "external_downloader": "aria2c",
                    "external_downloader_args": [
                        "-x", "16", "-s", "16", "-j", "16", "-k", "1M", 
                        "--file-allocation=none", "--disable-ipv6=true"
                    ]
                })
            else:
                # --- وضع الصوت (/play) ---
                # نستخدم Native Downloader لأنه أسرع في "بداية" التحميل (Start Latency)
                # Aria2c بياخد وقت (Overhead) عشان يجمع الاتصالات، وده بيأخر تشغيل الأغاني الصغيرة
                ydl_opts.update({
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                    # لا نحول لـ MP3 هنا.. الـ m4a أسرع والـ PyTgCalls بيشغله عادي جداً
                })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
                
        except Exception as e:
            print(f"Player Download Error: {e}")

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
        if videoid: link = self.base + link
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass
             
        loop = asyncio.get_running_loop()
        
        # 2. توليد معرف فريد
        try:
            if "v=" in link: vid_id = link.split("v=")[1].split("&")[0]
            else: vid_id = str(int(time.time()))
        except: vid_id = str(int(time.time()))

        # تحديد المسار (تفضيل m4a للصوت لأنه أسرع بدون تحويل)
        ext = "mp4" if (video or songvideo) else "m4a"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

        # 3. فحص الكاش (هل الملف موجود في الرام؟)
        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False

        # 4. تشغيل المحرك الهجين
        is_video_mode = bool(video or songvideo)
        
        # تنفيذ التحميل في خيوط منفصلة لعدم تعطيل البوت
        await loop.run_in_executor(
            self.pool, 
            self._player_download_task, 
            link, 
            ram_path, 
            is_video_mode
        )

        # 5. التحقق والعودة
        # نرجع دائماً False (ملف) لأن تشغيل الملف من الرام أفضل بمراحل من تشغيل رابط مباشر يقطع
        if os.path.exists(ram_path):
            return ram_path, False
        
        # فحص الامتدادات البديلة (احتياطي)
        base = ram_path.rsplit(".", 1)[0]
        for check_ext in [".m4a", ".webm", ".mp4", ".mp3", ".mkv"]:
             if os.path.exists(base + check_ext):
                 return base + check_ext, False
        
        return None, False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
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
            res = await a.next()
            if not res or not res.get("result"): return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]
        except: return "Error", "0", "", "error"

YouTube = YouTubeAPI()
