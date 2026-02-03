# Authored By Certified Systems Architect
# Dedicated Song Downloader (Fixed & Optimized)
# Features:
#   - Audio: Alexa-Style Direct Link (Fastest) -> Fallback to RAM Download
#   - Video: Aria2c RAM Download (Safest for Telegram)
#   - Fixes: DOWNLOAD_FAILED error caused by extension mismatch

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
    MAX_WORKERS = 8 # زيادة عدد العمليات لسرعة أكبر

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

class SongDownloaderAPI:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        self.force_high_quality = False

    def enable_quality(self):
        self.force_high_quality = True

    def disable_quality(self):
        self.force_high_quality = False

    def get_cookie_file(self):
        paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for p in paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        return None

    # --- دالة سرعة أليكسا (Direct Link) ---
    async def get_direct_url(self, link, is_video):
        # الفيديو المباشر مشاكله كتير، نستخدمه للصوت بس عشان السرعة
        if is_video: return None
        
        loop = asyncio.get_running_loop()
        def _extract():
            try:
                # نطلب M4A مباشر (أسرع وأفضل جودة للصوت)
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

    # ==========================================================
    # MAIN DOWNLOAD FUNCTION
    # ==========================================================
    async def download(self, link: str, is_video: bool = False):
        """
        Returns: (path_or_url, is_direct_bool)
        """
        # 1. تنظيف الرابط
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        # 2. محاولة الرابط المباشر (للصوت فقط وفي الوضع السريع)
        if not is_video and not self.force_high_quality:
            direct_url = await self.get_direct_url(link, is_video)
            if direct_url:
                return direct_url, True # رابط مباشر (أليكسا ستايل)

        # 3. التحميل للرام (للفيديو أو كبديل للصوت)
        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()

        def _download():
            uid = str(int(time.time() * 1000))
            # هنا التعديل المهم: بنسيب yt-dlp يحدد الامتداد عشان الخطأ يختفي
            out_tmpl = os.path.join(Config.DOWNLOAD_PATH, f"{uid}.%(ext)s")
            
            # إعدادات Aria2c للسرعة القصوى
            aria_args = ["-x", "16", "-s", "16", "-k", "1M", "--file-allocation=none"]

            if is_video:
                if self.force_high_quality:
                    fmt = "bestvideo+bestaudio/best" # أعلى جودة دمج
                else:
                    # 480p سريع جداً
                    fmt = "best[height<=480][ext=mp4]/best[ext=mp4]"
            else:
                fmt = "bestaudio/best"

            ydl_opts = {
                "format": fmt,
                "outtmpl": out_tmpl,
                "quiet": True,
                "no_warnings": True,
                "geo_bypass": True,
                "force_ipv4": True,
                "nocheckcertificate": True,
                "cookiefile": cookies,
                "external_downloader": "aria2c",
                "external_downloader_args": aria_args,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web"] # الويب أسرع في التحميل
                    }
                },
            }

            # تحويل الصوت لـ MP3 فقط لو مش فيديو
            if not is_video:
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320" if self.force_high_quality else "128",
                }]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])

            # البحث عن الملف الناتج (لأننا مش عارفين الامتداد النهائي)
            # بندور على أي ملف يبدأ بـ uid
            for f in os.listdir(Config.DOWNLOAD_PATH):
                if f.startswith(uid):
                    return os.path.join(Config.DOWNLOAD_PATH, f)

            return None

        try:
            file_path = await loop.run_in_executor(self.pool, _download)
            if file_path:
                return file_path, False # ملف محلي
        except Exception as e:
            print(f"SongDownloader Error: {e}")

        return None, False

SongDownloader = SongDownloaderAPI()
