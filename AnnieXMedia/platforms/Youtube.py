# file: AnnieXMedia/platforms/Youtube.py
# ➻ sᴏᴜʀᴄᴇ : بُودَا | ʙᴏᴅᴀ
# NUCLEAR EDITION: 16-Core Aria2c Download + Instant Direct Stream + RAM Disk + Full Format Support

import asyncio
import os
import re
import logging
import time
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from youtubesearchpython.aio import VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

# محاولة استيراد الدوال المساعدة
try:
    from AnnieXMedia.utils.formatters import time_to_seconds
    from AnnieXMedia import LOGGER
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    def LOGGER(name): return logging.getLogger(name)
    def time_to_seconds(t): return 0

# ---------------------- Configuration ----------------------

class Config:
    # استخدام الرام ديسك للسرعة القصوى
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    # استغلال الـ 16 كور بالكامل
    MAX_WORKERS = 16

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

_cache: Dict[str, Tuple[float, Tuple[Dict, str]]] = {}
_cache_lock = asyncio.Lock()
YOUTUBE_META_TTL = 3600

# ThreadPool للمعالجة المتوازية
_pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

def get_cookie_file() -> Optional[str]:
    possible_paths = [
        Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
        "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.abspath(path)
    return None

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        return errorz.decode("utf-8")
    return out.decode("utf-8")

# ---------------------- YouTube API Class ----------------------

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://www.youtube.com/playlist?list="
        self.pool = _pool

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

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        async with _cache_lock:
            if link in _cache:
                ts, (val, vid) = _cache[link]
                if time.time() - ts < YOUTUBE_META_TTL:
                    return val, vid

        try:
            results = VideosSearch(link, limit=1)
            res = await results.next()
            if not res or not res.get("result"):
                raise ValueError("No Result")
            data = res["result"][0]
            
            track_details = {
                "title": data["title"],
                "link": data["link"],
                "vidid": data["id"],
                "duration_min": data["duration"],
                "thumb": data["thumbnails"][0]["url"].split("?")[0],
                "cookiefile": get_cookie_file(),
            }
            async with _cache_lock:
                _cache[link] = (time.time(), (track_details, data["id"]))
            return track_details, data["id"]
        except Exception:
            return {"title": "Unknown", "link": link, "vidid": "error", "duration_min": "0:00", "thumb": ""}, "error"

    async def details(self, link: str, videoid: Union[bool, str] = None):
        d, i = await self.track(link, videoid)
        if i == "error": return None
        return d["title"], d["duration_min"], time_to_seconds(d["duration_min"]), d["thumb"], i

    async def title(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("title")

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb")

    # 🔥 التحميل الخلفي (للكاش فقط) 🔥
    def _background_download(self, link, final_path, is_video):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
            
            ydl_opts = {
                "format": fmt,
                "outtmpl": final_path,
                "cookiefile": get_cookie_file(),
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria2_args,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            if not is_video:
                 ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception:
            pass

    # 🔥 دالة التحميل الرئيسية (شاملة كل الحالات + السرعة القصوى) 🔥
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
        
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()

        # استخراج المعرف
        try:
            if "v=" in link: vid_id = link.split("v=")[1].split("&")[0]
            elif "youtu.be/" in link: vid_id = link.split("youtu.be/")[1].split("?")[0]
            else: vid_id = str(int(time.time()))
        except: vid_id = str(int(time.time()))

        # تحديد المسار في الرام
        # لو فيه title جاي (زي تحميل الأغاني) بنستخدمه، لو لا بنستخدم الـ ID
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title) if title else vid_id
        
        if songaudio:
            ext = "mp3"
        elif songvideo or video:
            ext = "mp4"
        else:
            ext = "m4a"
            
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")
        final_filename = os.path.join(Config.DOWNLOAD_PATH, f"{safe_title}.{ext}")

        # 1. فحص الكاش (RAM Cache Check) - لو الملف موجود وجاهز
        # بنشيك على الاسمين (بالـ ID وبالـ Title)
        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False
        if os.path.exists(final_filename) and os.path.getsize(final_filename) > 1024:
            return final_filename, False

        # 2. الحالة الخاصة: تحميل بـ Format معين أو SongAudio/SongVideo
        # في الحالة دي لازم تحميل فعلي (Blocking) بس هنستخدم Aria2c عشان يبقى طيارة
        if songaudio or songvideo or format_id:
            print(f"📥 Processing Specific Download: {safe_title}", flush=True)
            
            def _specific_download():
                aria2_args = ["-x", "16", "-s", "16", "-k", "1M", "--disable-ipv6=true"]
                
                # إعدادات الـ Format
                if songvideo:
                    fmt = f"{format_id}+140" # دمج الفيديو المختار مع صوت m4a
                elif songaudio:
                    fmt = format_id # تحميل الصوت فقط
                elif format_id:
                    fmt = format_id # صيغة محددة
                else:
                    fmt = "bestaudio/best"

                ydl_opts = {
                    "format": fmt,
                    "outtmpl": final_filename, # نستخدم الاسم المخصص هنا
                    "cookiefile": get_cookie_file(),
                    "geo_bypass": True,
                    "nocheckcertificate": True,
                    "quiet": True,
                    "external_downloader": "aria2c",
                    "external_downloader_args": aria2_args,
                    "extractor_args": {"youtube": {"player_client": ["web"]}},
                }

                if songvideo:
                     ydl_opts["merge_output_format"] = "mp4"
                
                if songaudio:
                    ydl_opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }]
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([link])
                    
                    # التأكد من وجود الملف (ممكن الامتداد يتغير بعد التحويل)
                    if os.path.exists(final_filename): return final_filename
                    
                    # محاولة البحث عن الملف بامتداد mp3 لو كان songaudio
                    base_name = os.path.splitext(final_filename)[0]
                    if os.path.exists(base_name + ".mp3"): return base_name + ".mp3"
                    
                    return None
                except Exception as e:
                    print(f"Error in specific download: {e}")
                    return None

            downloaded = await loop.run_in_executor(self.pool, _specific_download)
            return downloaded, False

        # 3. الحالة العامة (Play/Stream): محاولة الرابط المباشر الأول (Direct Link)
        # دي اللي بتخلي البوت سريع جداً في التشغيل العادي
        print(f"🚀 Fetching Direct Link for: {vid_id}", flush=True)
        try:
            cmd = ["yt-dlp", "-g", "--force-ipv4"]
            if get_cookie_file(): cmd.extend(["--cookies", get_cookie_file()])
            
            if video:
                cmd.extend(["-f", "best[height<=720]"])
            else:
                cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio"])
            
            cmd.extend(["--extractor-args", "youtube:player_client=web", link])

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if stdout:
                direct_link = stdout.decode().split("\n")[0].strip()
                # تشغيل التحميل في الخلفية للكاش المستقبلي
                loop.run_in_executor(self.pool, self._background_download, link, ram_path, video)
                return direct_link, True
        except Exception:
            pass

        # 4. Fallback: لو الرابط المباشر فشل، نحمل عادي بس بسرعة
        def _fallback_download():
            try:
                aria2_args = ["-x", "16", "-s", "16", "-k", "1M"]
                fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]" if video else "bestaudio[ext=m4a]"
                
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": ram_path,
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "external_downloader": "aria2c",
                    "external_downloader_args": aria2_args,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])
                return ram_path
            except: return None

        print("⚠️ Direct Link Failed, Fallback to Download...", flush=True)
        downloaded_file = await loop.run_in_executor(self.pool, _fallback_download)
        if downloaded_file:
            return downloaded_file, False
        
        return None, False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
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
        ytdl_opts = {"quiet": True, "cookiefile": get_cookie_file()}
        
        def _get_fmts():
            with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                try:
                    r = ydl.extract_info(link, download=False)
                    return r.get("formats", [])
                except: return []

        loop = asyncio.get_running_loop()
        raw_formats = await loop.run_in_executor(self.pool, _get_fmts)
        
        formats_available = []
        for format in raw_formats:
            try:
                formats_available.append({
                    "format": format["format"],
                    "filesize": format.get("filesize") or format.get("filesize_approx"),
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
            res = await a.next()
            if not res or not res.get("result"): return "Error", "0", "", "error"
            r = res["result"][query_type] if query_type < len(res["result"]) else res["result"][0]
            return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]
        except: return "Error", "0", "", "error"

YouTube = YouTubeAPI()
