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
        self.force_high_quality = False
        self.playlist_limit = 10

    def set_limit(self, limit: int):
        self.playlist_limit = int(limit)
        LOGGER("SongDownloader").info(f"Playlist Limit Set to: {self.playlist_limit}")

    def open_limit(self):
        self.playlist_limit = 0 
        LOGGER("SongDownloader").info("Playlist Limit: OPEN (Unlimited)")

    def reset_limit(self):
        self.playlist_limit = 10
        LOGGER("SongDownloader").info("Playlist Limit: Reset to Default (10)")

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

    # تم تعطيل دالة get_direct_url لأن تليجرام يرفض الروابط المباشرة ليوتيوب
    
    async def download(self, link: str, is_video: bool = False):
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        if not link.startswith(("http", "www")):
            link = f"ytsearch1:{link}"

        # تم مسح شرط استدعاء الرابط المباشر لإجبار البرنامج على تحميل الملف محلياً لتفادي الأخطاء.

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()
        
        if is_video:
            if self.force_high_quality:
                fmt = "bestvideo+bestaudio/best"
            else:
                fmt = "best[ext=mp4][height<=480]/best[ext=mp4][height<=360]/best[ext=mp4]"
        else:
            fmt = "bestaudio[ext=m4a]/bestaudio/best"

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
                "noplaylist": False, 
                "ignoreerrors": True,
                "concurrent_fragment_downloads": 5, 
                "buffersize": 1024 * 1024,
                "retries": 10,
                "trim_file_name": 50,
                # استخدام عملاء لضمان التحميل السليم
                "extractor_args": {"youtube": {"player_client": ["android", "mweb", "web"]}},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            
            if "list=" in link and self.playlist_limit > 0:
                ydl_opts["playlistend"] = self.playlist_limit

            if is_video and self.force_high_quality:
                ydl_opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    if 'entries' in info:
                        entries = list(info['entries'])
                        valid_entries = [e for e in entries if e]
                        if valid_entries:
                            return ydl.prepare_filename(valid_entries[0])
                    return ydl.prepare_filename(info)
            except Exception as e:
                LOGGER("SongDownloader").error(f"Download Error: {e}")
                pass
            return None

        try:
            file_path = await loop.run_in_executor(self.pool, _download_native)
            if file_path and os.path.exists(file_path):
                # نُرجع False للمتغير الثاني لأن التحميل أصبح محلياً بالكامل وليس رابط مباشر
                return file_path, False 
        except Exception:
            pass

        return None, False

SongDownloader = SongDownloaderAPI()
