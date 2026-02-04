# Authored By Certified Systems Architect
# Dedicated Song Downloader (Dynamic Quality Control 🚀)
# Default State: Speed Mode (480p/360p).
# Switch State: High Quality (4K/1080p) only via command.

import asyncio
import os
import logging
import time
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieSongDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_songs")

    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 10 

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

class SongDownloaderAPI:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        
        # 🛑 المفتاح الرئيسي 🛑
        # False = البوت هيفتح وهو شغال علي 480p/360p (الوضع السريع)
        # لن يتغير إلا لما تكتب أمر "ارفع الجودة"
        self.force_high_quality = False

    def enable_quality(self):
        self.force_high_quality = True
        LOGGER("SongDownloader").info("High Quality Mode (Max Res): ACTIVATED")

    def disable_quality(self):
        self.force_high_quality = False
        LOGGER("SongDownloader").info("Speed Mode (480p): ACTIVATED")

    def get_cookie_file(self):
        paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for p in paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        return None

    # --- 1. فحص الروابط المباشرة (للصوت فقط لتسريع الأداء) ---
    async def get_direct_url(self, link, is_video):
        if is_video: return None
        loop = asyncio.get_running_loop()
        def _extract():
            try:
                opts = {
                    "format": "bestaudio[ext=m4a][protocol^=http]",
                    "cookiefile": self.get_cookie_file(),
                    "quiet": True,
                    "no_warnings": True,
                    "force_ipv4": True,
                    "geo_bypass": True,
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    return info.get("url")
            except: return None
        return await loop.run_in_executor(self.pool, _extract)

    # --- 2. محرك التحميل ---
    async def download(self, link: str, is_video: bool = False):
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        # لو الفيديو مطلوب (False) والجودة مقفولة (False) -> حاول تجيب رابط مباشر للصوت
        if not is_video and not self.force_high_quality:
            direct_url = await self.get_direct_url(link, is_video)
            if direct_url: return direct_url, True

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()

        # ========================================================
        # 🎛️ التحكم في الجودة (القلب النابض)
        # ========================================================
        
        if is_video:
            if self.force_high_quality:
                # ✅ (لما تفعل الأمر): هات أقصى جودة (4K/2K/1080p) وادمج الصوت
                fmt = "bestvideo+bestaudio/best"
            else:
                # 🚀 (الوضع الافتراضي): هات 480p أو 360p جاهز (بدون دمج)
                fmt = "best[ext=mp4][height<=480]/best[ext=mp4][height<=360]/best[ext=mp4]"
        else:
            # 🎵 للصوت: دايماً m4a عشان السرعة (إلا لو حبيت تغيرها)
            fmt = "bestaudio[ext=m4a]"

        # ========================================================

        def _download_native():
            # حفظ الملف باسم الأغنية الحقيقي
            out_tmpl = os.path.join(Config.DOWNLOAD_PATH, "%(title)s.%(ext)s")

            ydl_opts = {
                "format": fmt,
                "outtmpl": out_tmpl,
                "quiet": True,
                "no_warnings": True,
                "geo_bypass": True,
                "force_ipv4": True,
                "nocheckcertificate": True,
                "cookiefile": cookies,
                
                # إعدادات السرعة
                "concurrent_fragment_downloads": 5, 
                "buffersize": 1024 * 1024,
                "retries": 10,
                "trim_file_name": 50, # قص الاسم الطويل
                
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            # 🔥 لو الجودة مفعلة وفيديو: ادمجهم في MP4 🔥
            if is_video and self.force_high_quality:
                ydl_opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    return ydl.prepare_filename(info)
            except Exception:
                pass
            return None

        try:
            file_path = await loop.run_in_executor(self.pool, _download_native)
            if file_path and os.path.exists(file_path):
                return file_path, False
        except Exception:
            pass

        return None, False

SongDownloader = SongDownloaderAPI()
