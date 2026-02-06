# Authored By Certified Systems Architect
# Dedicated Song Downloader (Quality Control + Playlist Limit)
# Optimized for Fly.io 16-Core Environment

import asyncio
import os
import logging
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    # ⚡ استخدام الرامات للسرعة القصوى
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieSongDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_songs")

    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 16  # استغلال الـ 16 كور بالكامل

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

class SongDownloaderAPI:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        
        # 🛑 متغير الجودة (زي ما طلبت عشان ميتشالش) 🛑
        # False = وضع السرعة (480p)
        # True = وضع الجودة العالية (Best Video + Best Audio)
        self.force_high_quality = False
        
        # 🛑 متغير حد البلاي ليست (الجديد) 🛑
        # 10 = الافتراضي
        # 0 = مفتوح (Unlimited)
        self.playlist_limit = 10 

    # --- 1. دوال التحكم في الليميت (للبلاي ليست) ---
    def set_limit(self, limit: int):
        """تعيين حد مخصص"""
        self.playlist_limit = int(limit)
        LOGGER("SongDownloader").info(f"Playlist Limit Set to: {self.playlist_limit}")

    def open_limit(self):
        """فتح الحد (تحميل القائمة كاملة)"""
        self.playlist_limit = 0 
        LOGGER("SongDownloader").info("Playlist Limit: OPEN (Unlimited)")

    def reset_limit(self):
        """إعادة التعيين للوضع الافتراضي (10)"""
        self.playlist_limit = 10
        LOGGER("SongDownloader").info("Playlist Limit: Reset to Default (10)")

    # --- 2. دوال التحكم في الجودة ---
    def enable_quality(self):
        self.force_high_quality = True
        LOGGER("SongDownloader").info("High Quality Mode: ACTIVATED")

    def disable_quality(self):
        self.force_high_quality = False
        LOGGER("SongDownloader").info("Speed Mode: ACTIVATED")

    # --- دوال مساعدة ---
    def get_cookie_file(self):
        paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "/app/cookies.txt"
        ]
        for p in paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        return None

    def _sanitize_input(self, link):
        # لو مش رابط، خليه بحث يوتيوب "ytsearch1"
        if not link.startswith(("http", "www")):
            return f"ytsearch1:{link}"
        return link

    # --- 3. فحص الروابط المباشرة (Direct Url) ---
    async def get_direct_url(self, link, is_video):
        if is_video: return None
        
        # لو الرابط بلاي ليست، الغي الرابط المباشر وادخل في التحميل العادي
        if "list=" in link: return None

        link = self._sanitize_input(link)
        loop = asyncio.get_running_loop()
        
        def _extract():
            try:
                opts = {
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                    "cookiefile": self.get_cookie_file(),
                    "quiet": True,
                    "no_warnings": True,
                    "force_ipv4": True,
                    "geo_bypass": True,
                    "default_search": "ytsearch1",
                    "noplaylist": True, 
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    if 'entries' in info: info = info['entries'][0]
                    return info.get("url")
            except: return None
        return await loop.run_in_executor(self.pool, _extract)

    # --- 4. محرك التحميل الرئيسي ---
    async def download(self, link: str, is_video: bool = False):
        # تصحيح روابط جوجل
        if "googleusercontent.com" in link and "v=" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass
        
        # تجهيز الرابط (بحث أو مباشر)
        if "list=" not in link:
            link = self._sanitize_input(link)

        # محاولة الرابط المباشر (للصوت فقط، بدون جودة عالية، وبدون بلاي ليست)
        if not is_video and not self.force_high_quality and "list=" not in link:
            direct_url = await self.get_direct_url(link, is_video)
            if direct_url: return direct_url, True

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()

        # 🛑 تطبيق منطق الجودة هنا 🛑
        if is_video:
            if self.force_high_quality:
                # وضع الجودة العالية (بطيء بس صورة نضيفة)
                fmt = "bestvideo+bestaudio/best"
            else:
                # وضع السرعة (أسرع، جودة 480p)
                fmt = "best[ext=mp4][height<=480]/best[ext=mp4][height<=360]/best[ext=mp4]"
        else:
            fmt = "bestaudio[ext=m4a]/bestaudio"

        def _download_native():
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
                "default_search": "ytsearch1", # يحل مشكلة البحث
                
                # 🛑 إعدادات البلاي ليست 🛑
                "noplaylist": False,     
                "ignoreerrors": True,    
                
                # إعدادات السرعة
                "concurrent_fragment_downloads": 8,
                "buffersize": 16 * 1024 * 1024,
                "retries": 5,
                "trim_file_name": 50,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            }
            
            # 🔥 تطبيق منطق الليميت (Limit Logic) 🔥
            if "list=" in link:
                if self.playlist_limit > 0:
                    # لو فيه رقم (مثلاً 10)، حمل لحد 10 وقف
                    ydl_opts["playlistend"] = self.playlist_limit 
                # لو self.playlist_limit بصفر، مش هنحط الشرط ده، فهيحمل القائمة كلها

            # لو فيديو وجودة عالية، ادمج الصوت مع الصورة
            if is_video and self.force_high_quality:
                ydl_opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    
                    if 'entries' in info:
                        # في حالة البلاي ليست أو البحث، نرجع أول ملف جاهز
                        # (ملاحظة: الكود ده مصمم يرجع مسار واحد للعمليات المتتالية)
                        entries = list(info['entries'])
                        if entries:
                            valid_entries = [e for e in entries if e]
                            if valid_entries:
                                return ydl.prepare_filename(valid_entries[0])
                    
                    return ydl.prepare_filename(info)
            except Exception as e:
                LOGGER("DownloadNative").error(f"Failed: {e}")
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
