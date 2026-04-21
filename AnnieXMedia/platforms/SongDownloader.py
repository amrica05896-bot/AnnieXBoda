# Authored By Certified Systems Architect
# Zero-Latency Downloader (Dynamic Clients: tv_embedded / android + IPv4 Forced)

import asyncio
import os
import logging
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

try:
    # تم التعديل إلى aio لضمان التوافق مع الإصدار الحديث
    from youtubesearchpython.aio import VideosSearch
    HAS_SEARCH = True
except ImportError:
    HAS_SEARCH = False

logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieSongDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_songs")
    
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
    def open_limit(self):
        self.playlist_limit = 0 
    def reset_limit(self):
        self.playlist_limit = 10
    def enable_quality(self):
        self.force_high_quality = True
    def disable_quality(self):
        self.force_high_quality = False
    
    async def download(self, link: str, is_video: bool = False):
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        # البحث السريع
        if not link.startswith(("http", "www")) and HAS_SEARCH:
            try:
                search = VideosSearch(link, limit=1)
                result = await search.next()
                if result and "result" in result and len(result["result"]) > 0:
                    vid = result["result"][0]["id"]
                    link = f"https://www.youtube.com/watch?v={vid}"
                else:
                    link = f"ytsearch1:{link}"
            except:
                link = f"ytsearch1:{link}"

        loop = asyncio.get_running_loop()
        
        # 🎯 الذكاء في اختيار العميل بناءً على نتيجة الكونسول
        if is_video:
            # tv_embedded: الأسرع في جلب الـ HQ (2.69s) وبدون أخطاء
            target_clients = ["tv_embedded"]
            if self.force_high_quality:
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            else:
                fmt = "b[ext=mp4][height<=480]/b[ext=mp4][height<=360]/b[ext=mp4]/best"
        else:
            # android: الأسرع على الإطلاق (1.13s) للصوتيات
            target_clients = ["android"]
            fmt = "ba[ext=m4a]/ba/b"

        def _download_native():
            out_tmpl = os.path.join(Config.DOWNLOAD_PATH, "%(title)s.%(ext)s")

            ydl_opts = {
                "format": fmt,
                "outtmpl": out_tmpl,
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                "cookiefile": None, 
                
                "force_ipv4": True,
                "source_address": "0.0.0.0",
                "geo_bypass": False, 
                
                "js_runtimes": {"node": {}},
                "remote_components": ["ejs:github"],
                
                # توجيه العميل الفائز فقط لعدم إهدار الوقت
                "extractor_args": {
                    "youtube": {
                        "player_client": target_clients
                    }
                },
                
                "concurrent_fragment_downloads": 10,  
                "http_chunk_size": 10485760,         
                "buffersize": 1024 * 1024 * 5,       
                "retries": 15,                       
                
                "noplaylist": False, 
                "ignoreerrors": True,
                "trim_file_name": 50,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            }
            
            if "list=" in link and self.playlist_limit > 0:
                ydl_opts["playlistend"] = self.playlist_limit
            
            if is_video and self.force_high_quality:
                ydl_opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    if not info: return None
                        
                    if 'entries' in info:
                        entries = [e for e in info['entries'] if e]
                        if entries: return ydl.prepare_filename(entries[0])
                    return ydl.prepare_filename(info)
            except Exception as e:
                LOGGER("SongDownloader").error(f"Download Error: {e}")
            return None

        try:
            file_path = await loop.run_in_executor(self.pool, _download_native)
            if file_path and os.path.exists(file_path):
                return file_path, False 
        except Exception:
            pass

        return None, False

SongDownloader = SongDownloaderAPI()
