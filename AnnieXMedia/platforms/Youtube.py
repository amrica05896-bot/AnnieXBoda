# Authored By Certified 
# Fixed for platforms/Youtube.py
# NUCLEAR EDITION: 16-Core Aria2c + Smart Format Merge
# FEATURES: Anti-Throttle, URL Sanitizer, Thumb Fix, IPv4 Force
# NOTE: removed 'android' and 'ios' player_client usages — using 'web' only

import asyncio
import os
import re
import logging
import aiohttp
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import time
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch

try:
    from AnnieXMedia.utils.formatters import time_to_seconds
    from AnnieXMedia import LOGGER
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    def LOGGER(name): return logging.getLogger(name)
    def time_to_seconds(t): return 0

# ---------------- Config ----------------
class Config:
    # استخدام الرام (Shm) للسرعة القصوى
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 16

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_cache_lock = asyncio.Lock()
YOUTUBE_META_TTL = 3600

# ---------------- Helpers ----------------
def get_cookie_file():
    possible_paths = [
        Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
        "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
    ]
    for path in possible_paths:
        try:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return os.path.abspath(path)
        except Exception:
            continue
    return None

# ✅ تعريف Decorator الناقص
def asyncify(func):
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper

# ---------------- YouTube API ----------------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://www.youtube.com/playlist?list="
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset: break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None if offset in (None,) else text[offset : offset + length]

    # ✅ دالة Track (مهمة للبحث وتوافق song.py)
    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        async with _cache_lock:
            if link in _cache:
                ts, val = _cache[link]
                if time.time() - ts < YOUTUBE_META_TTL:
                    return val[0], val[1]

        try:
            results = VideosSearch(link, limit=1)
            try:
                res = await results.next()
            except Exception:
                # fallback to property if library behaves differently
                try:
                    res = await results.result()
                except Exception:
                    res = {}
            if not res or not res.get("result"):
                raise ValueError("No Result")
            data = res["result"][0]
            
            thumb = data["thumbnails"][0]["url"].split("?")[0] if data.get("thumbnails") else ""
            
            track_details = {
                "title": data["title"],
                "link": data["link"],
                "vidid": data["id"],
                "duration_min": data["duration"],
                "thumb": thumb,
                "cookiefile": get_cookie_file(),
            }
            async with _cache_lock:
                _cache[link] = (time.time(), (track_details, data["id"]))
            return track_details, data["id"]
        except Exception:
            return {"title": "Unknown", "link": link, "vidid": "error", "duration_min": "0:00", "thumb": ""}, "error"

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        # تنظيف الرابط الوهمي
        if "googleusercontent.com" in link:
            try:
                vid_id = link.split("youtube.com/")[-1]
                vid_id = re.sub(r'^\d+', '', vid_id)
                link = f"https://www.youtube.com/watch?v={vid_id}"
            except: pass

        d, i = await self.track(link, videoid)
        if i == "error": return None
        
        # تحويل الوقت
        duration_sec = 0
        if d.get("duration_min"):
             try: duration_sec = int(time_to_seconds(d["duration_min"]))
             except: pass
             
        return d["title"], d["duration_min"], duration_sec, d["thumb"], i

    async def title(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("title")

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb")

    # ✅ دالة تحميل الصور (مطلوبة لملف song.py)
    async def download_thumb(self, url):
        if not url: return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        path = os.path.join(Config.DOWNLOAD_PATH, f"thumb_{int(time.time())}.jpg")
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
        except: return None
        return None

    # 🔥 التحميل الخلفي (Aria2c + فك الخنق) — player_client: ['web'] فقط
    def _background_download(self, link, final_path, is_video):
        try:
            aria2_args = [
                "-x", "16", "-s", "16", "-j", "16", "-k", "1M",
                "--file-allocation=none", "--disable-ipv6=true"
            ]
            
            # إزالة [ext=mp4] لتجنب الأخطاء، نعتمد على الدمج
            fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]" if is_video else "bestaudio/best"
            
            ydl_opts = {
                "format": fmt,
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "force_ipv4": True, # إجبار IPv4
                
                # استخدام web فقط (حذف android/ios)
                "extractor_args": {"youtube": {"player_client": ["web"]}},
                "remote_components": ["ejs:github"], # لحل ألغاز JS
                
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
            }
            
            if is_video:
                ydl_opts["merge_output_format"] = "mp4" # تحويل أي صيغة إلى mp4
            else:
                ydl_opts["postprocessors"] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception:
            pass

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        # 1. تنظيف الرابط
        if "googleusercontent.com" in link:
            try:
                real_id = link.split("youtube.com/")[-1]
                if real_id and real_id[0].isdigit() and len(real_id) > 11:
                    real_id = real_id[1:]
                link = f"https://www.youtube.com/watch?v={real_id}"
            except: pass
        
        if videoid: link = f"https://www.youtube.com/watch?v={videoid}"

        loop = asyncio.get_running_loop()

        # توليد ID ومسار
        try:
            if "v=" in link: vid_id = link.split("v=")[1].split("&")[0]
            else: vid_id = str(int(time.time()))
        except: vid_id = str(int(time.time()))

        ext = "mp4" if (video or songvideo) else "mp3"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}") 

        # 2. تحميل محدد الجودة (أزرار)
        if format_id:
            def _specific_download():
                try:
                    aria2_args = ["-x", "16", "-k", "1M", "--disable-ipv6=true"]
                    ydl_opts = {
                        "format": f"{format_id}+140" if songvideo else format_id,
                        "outtmpl": f"{ram_path}.%(ext)s",
                        "cookiefile": get_cookie_file(),
                        "quiet": True,
                        "force_ipv4": True,
                        # web only here too
                        "extractor_args": {"youtube": {"player_client": ["web"]}},
                        "external_downloader": "aria2c",
                        "external_downloader_args": aria2_args,
                    }
                    if songaudio:
                        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3"}]
                    elif songvideo:
                        ydl_opts["merge_output_format"] = "mp4"

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(link, download=True)
                        return ydl.prepare_filename(info)
                except: return None
            
            dl_path = await loop.run_in_executor(self.pool, _specific_download)
            return dl_path, False

        # 3. البث المباشر (Direct Stream) — استخدام web فقط
        try:
            cmd = [
                "yt-dlp", "-g",
                "--cookies", get_cookie_file() or "",
                "--force-ipv4",
                "--extractor-args", "youtube:player_client=web",
            ]
            
            if video:
                cmd.extend(["-f", "best[height<=720]"])
            else:
                cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio"])
            
            cmd.append(link)

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if stdout:
                direct_link = stdout.decode().split("\n")[0].strip()
                # تشغيل التحميل في الخلفية
                loop.run_in_executor(self.pool, self._background_download, link, f"{ram_path}.%(ext)s", video)
                return direct_link, True
        except:
            pass

        # 4. Fallback (التحميل العادي)
        def _fallback_download():
            try:
                # فلتر ذكي يقبل أي صيغة ثم يحولها
                fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]" if video else "bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_path}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "force_ipv4": True,
                    "remote_components": ["ejs:github"],
                    # web only
                    "extractor_args": {"youtube": {"player_client": ["web"]}}
                }
                
                if video:
                    ydl_opts["merge_output_format"] = "mp4"
                else:
                    ydl_opts["postprocessors"] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    expected_path = ydl.prepare_filename(info)
                    
                    if video and expected_path.endswith(".webm"):
                         return expected_path
                    if not video:
                        return expected_path.rsplit(".", 1)[0] + ".mp3"
                    return expected_path

            except Exception as e: 
                print(f"Fallback Error: {e}")
                return None

        downloaded_file = await loop.run_in_executor(self.pool, _fallback_download)
        if downloaded_file and os.path.exists(downloaded_file):
            return downloaded_file, False
        
        return None, False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--force-ipv4 "
            f"--extractor-args 'youtube:player_client=web' "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try: result = [key for key in out.decode().split("\n") if key]
        except: result = []
        return result

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        ytdl_opts = {"quiet": True, "cookiefile": get_cookie_file(), "force_ipv4": True}
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            formats_available = []
            try:
                r = ydl.extract_info(link, download=False)
                for format in r.get("formats", []):
                    formats_available.append({
                        "format": format["format"],
                        "filesize": format.get("filesize"),
                        "format_id": format["format_id"],
                        "ext": format["ext"],
                        "yturl": link,
                    })
            except: pass
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            a = VideosSearch(link, limit=5)
            try: res = await a.next()
            except: res = a.result()
            
            if not res or not res.get("result"): return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            thumb = r["thumbnails"][0]["url"].split("?")[0] if r.get("thumbnails") else ""
            return r["title"], r["duration"], thumb, r["id"]
        except: return "Error", "0", "", "error"

YouTube = YouTubeAPI()
