# Authored By Certified Systems Architect
# Dedicated Song Downloader (Default: Speed Mode 🚀)
# Logic: Starts with Quality = False (Speed). Only switches to True via Command.

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
        
        # 🛑 هنا التعديل: القيمة الافتراضية False (وضع السرعة)
        # لن تتغير هذه القيمة إلا بأمر منك
        self.force_high_quality = False

    def enable_quality(self):
        self.force_high_quality = True
        LOGGER("SongDownloader").info("🚀 High Quality Mode: ACTIVATED")

    def disable_quality(self):
        self.force_high_quality = False
        LOGGER("SongDownloader").info("✈️ Speed Mode: ACTIVATED")

    def get_cookie_file(self):
        paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for p in paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        return None

    # --- 1. سرعة الصوت (Direct Link) ---
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

    # --- 2. المحرك الرئيسي ---
    async def download(self, link: str, is_video: bool = False):
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        # لو الوضع False (سرعة) والصوت مطلوب -> استخدم الرابط المباشر فوراً
        if not is_video and not self.force_high_quality:
            direct_url = await self.get_direct_url(link, is_video)
            if direct_url: return direct_url, True

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()

        # ========================================================
        # 🎛️ منطق اختيار الجودة (Quality Logic)
        # ========================================================
        
        if self.force_high_quality:
            # ✅ (True) وضع الجودة العالية (فقط عند طلبك)
            # دمج أفضل فيديو وصوت + 320kbps
            video_fmt = "bestvideo+bestaudio/best"
            audio_q = "320"
        else:
            # 🚀 (False - Default) وضع السرعة الافتراضي
            # 1. 480p جاهز (أسرع) -> 2. 360p جاهز -> 3. 720p جاهز -> 4. أي MP4
            video_fmt = (
                "best[ext=mp4][height<=480]/"
                "best[ext=mp4][height<=360]/"
                "best[ext=mp4][height<=720]/"
                "best[ext=mp4]/"
                "best"
            )
            # صوت 128kbps خفيف وسريع
            audio_q = "128"

        # ========================================================

        def _download_native():
            uid = str(int(time.time() * 1000))
            out_tmpl = os.path.join(Config.DOWNLOAD_PATH, f"{uid}.%(ext)s")

            if is_video:
                fmt = video_fmt
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
                
                # إعدادات السرعة (Native Tuning)
                "concurrent_fragment_downloads": 5, 
                "buffersize": 1024 * 1024,
                "http_chunk_size": 10485760,
                "retries": 10,
                
                "extractor_args": {
                    "youtube": {
                        "player_client": ["web"], 
                        "skip": ["dash", "hls"]
                    }
                }
            }

            if not is_video:
                ydl_opts["postprocessors"] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': audio_q, # هنا بيطبق الجودة المختارة
                }]

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])
            except Exception:
                pass

            for f in os.listdir(Config.DOWNLOAD_PATH):
                if f.startswith(uid):
                    return os.path.join(Config.DOWNLOAD_PATH, f)
            return None

        try:
            file_path = await loop.run_in_executor(self.pool, _download_native)
            if file_path:
                return file_path, False
        except Exception:
            pass

        return None, False

SongDownloader = SongDownloaderAPI()
