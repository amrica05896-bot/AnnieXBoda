# Authored By Certified 
# Dedicated Song Downloader for song.py
# HYBRID ENGINE: Direct Link (First) -> Native RAM Download (Fallback)
# SECURITY: Enforces 'cookies.txt' and 'ejs:github' (JS Solver) in ALL stages.

import asyncio
import os
import logging
import time
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# إعداد اللوجر
logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    # استخدام الرام للتخزين المؤقت
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

    # ✅ دالة البحث عن الكوكيز بذكاء
    def get_cookie_file(self):
        possible_paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for path in possible_paths:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return os.path.abspath(path)
        return None

    async def download(self, link: str, is_video: bool = False):
        """
        يرجع: (المسار_أو_الرابط, هل_هو_رابط_مباشر؟)
        """
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()
        
        # طباعة للتأكد من الكونسول
        if cookies: print(f"🍪 SongDownloader using cookies: {cookies}", flush=True)
        else: print(f"⚠️ SongDownloader: No cookies found!", flush=True)

        # ------------------------------------------------------------------
        # STEP 1: الرابط المباشر (Instant Direct Link)
        # ------------------------------------------------------------------
        print(f"🚀 Trying Instant Link (with JS Solver) for: {link}", flush=True)
        
        try:
            def _get_direct():
                # إعدادات صارمة للرابط المباشر
                fmt = "bestaudio[protocol^=http][protocol!*=dash]" if not is_video else "best[protocol^=http][protocol!*=dash]"
                opts = {
                    "format": fmt,
                    "cookiefile": cookies,  # ✅ تفعيل الكوكيز
                    "quiet": True,
                    "no_warnings": True,
                    "force_ipv4": True,
                    "geo_bypass": True,
                    "noplaylist": True,
                    "nocheckcertificate": True,
                    
                    # ✅ تفعيل مفكك الجافا سكريبت (أهم سطر)
                    "remote_components": ["ejs:github"], 
                    "extractor_args": {"youtube": {"player_client": ["web"]}}, # استخدام Web لضمان عمل الكوكيز
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    return info.get("url")

            direct_url = await loop.run_in_executor(self.pool, _get_direct)
            
            if direct_url and "http" in direct_url:
                print("✅ Instant Link Secured via Cookies & JS!", flush=True)
                return direct_url, True # True = رابط مباشر
                
        except Exception as e:
            print(f"⚠️ Direct Link Failed ({e}), Switching to RAM...", flush=True)

        # ------------------------------------------------------------------
        # STEP 2: التحميل للرام (Native RAM Download)
        # ------------------------------------------------------------------
        try:
            def _download_native():
                vid_id = str(int(time.time()))
                ext = "mp4" if is_video else "mp3"
                final_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

                ydl_opts = {
                    "format": "bestaudio/best" if not is_video else "best[height<=720]",
                    "outtmpl": final_path,
                    "cookiefile": cookies, # ✅ تفعيل الكوكيز
                    "quiet": True,
                    "no_warnings": True,
                    "geo_bypass": True,
                    "force_ipv4": True,
                    "nocheckcertificate": True,
                    
                    # ✅ تفعيل مفكك الجافا سكريبت هنا أيضاً
                    "remote_components": ["ejs:github"],
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                
                if not is_video:
                    ydl_opts["postprocessors"] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192'
                    }]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])
                
                if os.path.exists(final_path): return final_path
                
                # التحقق من الامتدادات البديلة
                base = final_path.rsplit(".", 1)[0]
                for check_ext in [".mp3", ".m4a", ".mp4", ".webm"]:
                    if os.path.exists(base + check_ext): return base + check_ext
                
                return None

            file_path = await loop.run_in_executor(self.pool, _download_native)

            if file_path:
                print(f"💾 RAM Download Complete: {file_path}", flush=True)
                return file_path, False # False = ملف

        except Exception as e:
            print(f"❌ RAM Download Failed: {e}", flush=True)

        return None, False

SongDownloader = SongDownloaderAPI()
