# Authored By Certified Systems Architect
# Dedicated Song Downloader (MAX SPEED 🚀 + IPv4 Forced + Node.js Decryption)
# Optimization: Telegram Friendly Formats (M4A/MP4) & No-Cookie Policy

import asyncio
import os
import logging
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# استيراد مكتبة البحث السريع لتجنب بطء yt-dlp في مرحلة الـ Extraction
try:
    from youtubesearchpython.__future__ import VideosSearch
    HAS_SEARCH = True
except ImportError:
    HAS_SEARCH = False

logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    # استخدام الرام ديسك لو متاح لتسريع العمليات
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
        # تصحيح روابط جوجل لو وجدت
        if "googleusercontent.com" in link:
             try: link = f"https://www.youtube.com/watch?v={link.split('v=')[1]}"
             except: pass

        # 🚀 المرحلة 1: البحث السريع (لو المدخل مش رابط)
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
        
        # 🎛️ المرحلة 2: تحديد الصيغ (M4A للصوت / MP4 للفيديو)
        if is_video:
            if self.force_high_quality:
                # دمج أفضل فيديو mp4 مع أفضل صوت m4a
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            else:
                # جودة متوسطة سريعة للموبايل
                fmt = "b[ext=mp4][height<=480]/b[ext=mp4][height<=360]/b[ext=mp4]/best"
        else:
            # صوت فقط بصيغة m4a المفضلة لتليجرام
            fmt = "ba[ext=m4a]/ba/b"

        def _download_native():
            out_tmpl = os.path.join(Config.DOWNLOAD_PATH, "%(title)s.%(ext)s")

            ydl_opts = {
                "format": fmt,
                "outtmpl": out_tmpl,
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                
                # 🚫 تجاهل الكوكيز تماماً لضمان عمل عميل الأندرويد بسرعة
                "cookiefile": None,
                
                # ⚡ 3. قتل تأخير الدقيقة (إجبار IPv4)
                "force_ipv4": True,
                "source_address": "0.0.0.0",
                "geo_bypass": False, 
                
                # 🔴 4. فك تشفير يوتيوب (Node.js + EJS)
                "js_runtimes": {"node": {}},
                "remote_components": ["ejs:github"],
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web", "mweb"]
                    }
                },
                
                # 🚀 5. إعدادات السحب المتوازي (Native Chunking)
                "concurrent_fragment_downloads": 10,  # 10 خطوط تحميل
                "http_chunk_size": 10485760,         # قطع 10 ميجا
                "buffersize": 1024 * 1024 * 5,       # بافر 5 ميجا للكتابة
                "retries": 15,                       # محاولات لو السيرفر هنج
                
                "noplaylist": False, 
                "ignoreerrors": True,
                "trim_file_name": 50,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            }
            
            # معالجة قوائم التشغيل
            if "list=" in link and self.playlist_limit > 0:
                ydl_opts["playlistend"] = self.playlist_limit
            
            # دمج الفيديو في mp4 لو كان عالي الجودة
            if is_video and self.force_high_quality:
                ydl_opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    
                    # حماية من خطأ NoneType
                    if not info:
                        return None
                        
                    if 'entries' in info:
                        entries = [e for e in info['entries'] if e]
                        if entries:
                            return ydl.prepare_filename(entries[0])
                    return ydl.prepare_filename(info)
            except Exception as e:
                LOGGER("SongDownloader").error(f"Download Error: {e}")
            return None

        try:
            # تنفيذ التحميل في Thread منفصل عشان ميعطلش البوت
            file_path = await loop.run_in_executor(self.pool, _download_native)
            if file_path and os.path.exists(file_path):
                return file_path, False 
        except Exception:
            pass

        return None, False

# إنشاء نسخة مفردة لاستخدامها في كل مكان
SongDownloader = SongDownloaderAPI()
