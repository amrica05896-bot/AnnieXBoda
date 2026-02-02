# Authored By Certified Systems Architect
# Dedicated Song Downloader (Separated Logic)
# Features: 
#   - Standard Mode: Video <= 480p | Audio = 128kbps (Fastest)
#   - High Quality Mode: Video = Max Res | Audio = 320kbps (Best)
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
        # حالة الجودة الافتراضية: مقفولة (Standard: 480p/128k)
        self.force_high_quality = False

    def enable_quality(self):
        """تفعيل الجودة العالية (Unlimited)"""
        self.force_high_quality = True

    def disable_quality(self):
        """قفل الجودة العالية (العودة لـ 480p/128k)"""
        self.force_high_quality = False

    def get_cookie_file(self):
        possible_paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for path in possible_paths:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return os.path.abspath(path)
        return None

    # دالة التحميل الرئيسية
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
        # يتم تنفيذ هذه الخطوة فقط إذا كانت "الجودة العالية مغلقة"
        # لأننا نريد سرعة، وروابط 360p/480p المباشرة ممتازة هنا
        
        if not self.force_high_quality:
            print(f"🚀 Trying Smart Link for: {link}", flush=True)
            try:
                def _get_direct():
                    if is_video:
                        # للفيديو: نطلب ملف MP4 مباشر بشرط ألا يتعدى 480p
                        fmt = "best[height<=480][ext=mp4][protocol^=http]"
                    else:
                        # للصوت: نطلب M4A نقي أو فيديو صغير جداً
                        fmt = "bestaudio[ext=m4a][protocol^=http]/best[height<=360][ext=mp4][protocol^=http]"

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
                        info = ydl.extract_info(link, download=False)
                        return info.get("url")

                direct_url = await loop.run_in_executor(self.pool, _get_direct)
                
                if direct_url and "http" in direct_url:
                    print("✅ Smart Link Found! Sending...", flush=True)
                    return direct_url, True # رابط مباشر
                    
            except Exception as e:
                print(f"⚠️ Smart Link Failed ({e}), Switching to RAM...", flush=True)
        else:
            print("💎 High Quality Enabled: Skipping Direct Link to force Max Quality Download...", flush=True)

        # ------------------------------------------------------------------
        # STEP 2: التنزيل للرام (Fast Native Fallback / High Quality Engine)
        # ------------------------------------------------------------------
        try:
            def _download_native():
                vid_id = str(int(time.time()))
                ext = "mp4" if is_video else "mp3"
                final_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

                # إعدادات الجودة بناءً على الحالة
                if self.force_high_quality:
                    # === وضع الجودة العالية (High Quality) ===
                    if is_video:
                        # دمج أفضل فيديو مع أفضل صوت (يصل لـ 4K)
                        fmt = "bestvideo+bestaudio/best" 
                    else:
                        # أفضل صوت متاح
                        fmt = "bestaudio/best"
                    
                    audio_quality = '320' # 320kbps
                    
                else:
                    # === وضع الجودة الطبيعية (Standard Speed) ===
                    if is_video:
                        # حد أقصى 480p، لو مفيش هات 360p
                        fmt = "best[height<=480][ext=mp4]/best[height<=360][ext=mp4]/best[ext=mp4]"
                    else:
                        # صوت عادي
                        fmt = "bestaudio/best"
                    
                    audio_quality = '128' # 128kbps (خفيف وسريع)

                ydl_opts = {
                    "format": fmt,
                    "outtmpl": final_path,
                    "cookiefile": cookies,
                    "quiet": True,
                    "no_warnings": True,
                    "geo_bypass": True,
                    "force_ipv4": True,
                    "nocheckcertificate": True,
                    "remote_components": ["ejs:github"],
                    # في الجودة العالية نستخدم Android لتجنب الخنق في الملفات الكبيرة
                    "extractor_args": {"youtube": {"player_client": ["android", "web"]}} if self.force_high_quality else {"youtube": {"player_client": ["web"]}},
                }
                
                # إعدادات معالجة الصوت (التحويل لـ MP3)
                if not is_video:
                    ydl_opts["postprocessors"] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': audio_quality
                    }]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])
                
                # التحقق من الملف
                if os.path.exists(final_path): return final_path
                base = final_path.rsplit(".", 1)[0]
                for check_ext in [".mp3", ".m4a", ".mp4", ".webm", ".mkv"]:
                    if os.path.exists(base + check_ext): return base + check_ext
                
                return None

            file_path = await loop.run_in_executor(self.pool, _download_native)

            if file_path:
                print(f"💾 RAM Download Complete (HQ={self.force_high_quality}): {file_path}", flush=True)
                return file_path, False # ملف

        except Exception as e:
            print(f"❌ RAM Download Failed: {e}", flush=True)

        return None, False

SongDownloader = SongDownloaderAPI()
