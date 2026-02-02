# Authored By Certified 
# Dedicated Song Downloader (Separated Logic)
# HYBRID ENGINE: Smart Direct Link -> Native RAM Fallback
# Fixes: "Requested format not available" & "WEBPAGE_MEDIA_EMPTY"

import asyncio
import os
import logging
import time
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    # مسار الرام للسرعة القصوى
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieSongDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_songs")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 4

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

class SongDownloaderAPI:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    def get_cookie_file(self):
        possible_paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for path in possible_paths:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return os.path.abspath(path)
        return None

    # دالة التحميل الرئيسية (تتخذ القرار تلقائياً)
    async def download(self, link: str, is_video: bool = False):
        """
        يرجع: (المسار_أو_الرابط, هل_هو_رابط_مباشر؟)
        """
        # تنظيف الرابط
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()
        
        # ------------------------------------------------------------------
        # STEP 1: المحاولة الذكية (Smart Instant Link)
        # ------------------------------------------------------------------
        # الفلتر الجديد: يطلب صوت نقي HTTP، وإذا لم يجد، يطلب فيديو 360p HTTP (لأنه أسرع وأضمن من DASH)
        print(f"🚀 Trying Smart Link for: {link}", flush=True)
        
        try:
            def _get_direct():
                if is_video:
                    # للفيديو: نطلب ملف MP4 واحد مباشر (بدون تقطيع DASH)
                    fmt = "best[ext=mp4][protocol^=http]"
                else:
                    # للصوت: نطلب M4A نقي، أو فيديو MP4 صغير (360p) يحتوي على صوت AAC
                    # هذا الفلتر يحل مشكلة "Requested format not available"
                    fmt = "bestaudio[ext=m4a][protocol^=http]/best[ext=mp4][height<=480][protocol^=http]/bestaudio[protocol^=http]"

                opts = {
                    "format": fmt,
                    "cookiefile": cookies,
                    "quiet": True,
                    "no_warnings": True,
                    "force_ipv4": True,
                    "geo_bypass": True,
                    "noplaylist": True,
                    "nocheckcertificate": True,
                    "remote_components": ["ejs:github"],
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # simulate=True تعني: هات الرابط بس ومتنزلش
                    info = ydl.extract_info(link, download=False)
                    return info.get("url")

            direct_url = await loop.run_in_executor(self.pool, _get_direct)
            
            if direct_url and "http" in direct_url:
                print("✅ Smart Link Found! Sending...", flush=True)
                return direct_url, True # رابط مباشر
                
        except Exception as e:
            print(f"⚠️ Smart Link Failed ({e}), Switching to RAM...", flush=True)

        # ------------------------------------------------------------------
        # STEP 2: التنزيل للرام (Fast Native Fallback)
        # ------------------------------------------------------------------
        try:
            def _download_native():
                vid_id = str(int(time.time()))
                ext = "mp4" if is_video else "mp3"
                final_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

                ydl_opts = {
                    "format": "bestaudio/best" if not is_video else "best[height<=720]",
                    "outtmpl": final_path,
                    "cookiefile": cookies,
                    "quiet": True,
                    "no_warnings": True,
                    "geo_bypass": True,
                    "force_ipv4": True,
                    "nocheckcertificate": True,
                    "remote_components": ["ejs:github"],
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                
                # تحويل إجباري لـ MP3 للصوتيات
                if not is_video:
                    ydl_opts["postprocessors"] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192'
                    }]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])
                
                # التحقق من الملف
                if os.path.exists(final_path): return final_path
                base = final_path.rsplit(".", 1)[0]
                for check_ext in [".mp3", ".m4a", ".mp4", ".webm"]:
                    if os.path.exists(base + check_ext): return base + check_ext
                
                return None

            file_path = await loop.run_in_executor(self.pool, _download_native)

            if file_path:
                print(f"💾 RAM Download Complete: {file_path}", flush=True)
                return file_path, False # ملف

        except Exception as e:
            print(f"❌ RAM Download Failed: {e}", flush=True)

        return None, False

SongDownloader = SongDownloaderAPI()
