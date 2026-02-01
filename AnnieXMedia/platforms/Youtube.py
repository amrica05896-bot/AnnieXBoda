# Authored By Certified Coders © 2026
# System: YouTubeAPI | NUCLEAR HYBRID | py_yt Edition
# Features:
# 1. Search: py_yt (Fastest Scraping)
# 2. Stream: -g flag (Instant Start)
# 3. Mode: Android (No Cookies) -> Fallback to Web (With Cookies)
# 4. Download: Aria2c (IPv4 Force, No SSL Check)

import asyncio
import os
import re
import logging
import time
import yt_dlp
from typing import Union, List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# ✅ استخدام py_yt بدلاً من المكتبة القديمة
from py_yt import VideosSearch
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

try:
    from AnnieXMedia.utils.formatters import time_to_seconds
    from AnnieXMedia import LOGGER
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    def LOGGER(name): return logging.getLogger(name)
    def time_to_seconds(t): return 0

class Config:
    # استخدام الرامات للتخزين المؤقت (سرعة جنونية)
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads")
    
    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 16 # استغلال المعالج بالكامل

if not os.path.exists(Config.DOWNLOAD_PATH):
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)

# كاش داخلي لتسريع البحث المتكرر
_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_cache_lock = asyncio.Lock()
YOUTUBE_META_TTL = 3600

def get_cookie_file():
    possible_paths = [
        Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
        "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.abspath(path)
    return None

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

    # ✅ دالة البحث الجديدة باستخدام py_yt (معدلة لتعمل Async)
    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        link = link.split("&")[0]

        # فحص الكاش أولاً
        async with _cache_lock:
            if link in _cache:
                ts, val = _cache[link]
                if time.time() - ts < YOUTUBE_META_TTL:
                    return val[0], val[1]

        loop = asyncio.get_running_loop()

        def _py_yt_search():
            try:
                # py_yt search returns a Result object directly
                search = VideosSearch(link, limit=1)
                result = search.result()
                if not result or not result.get("result"):
                    return None
                return result["result"][0]
            except:
                return None

        try:
            # تشغيل py_yt في الخلفية عشان متهنجش البوت
            data = await loop.run_in_executor(self.pool, _py_yt_search)
            
            if not data:
                raise ValueError("No Result")
            
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

    # 🔥 التحميل الخلفي (Aria2c Nuclear)
    # يستخدم فقط إذا فشل البث المباشر
    def _background_download(self, link, final_path, is_video):
        try:
            aria2_args = [
                "-x", "16", "-s", "16", "-j", "16", "-k", "1M",
                "--file-allocation=none",
                "--disable-ipv6=true",        # منع مشاكل الشبكة
                "--check-certificate=false",  # منع SSL Errors
                "--async-dns=false"
            ]
            
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
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception:
            pass

    # 🔥 الدالة الجوكر (Stream & Download) 🔥
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

        try:
            if "v=" in link: vid_id = link.split("v=")[1].split("&")[0]
            else: vid_id = str(int(time.time()))
        except: vid_id = str(int(time.time()))

        ext = "mp4" if video else "m4a"
        ram_path = os.path.join(Config.DOWNLOAD_PATH, f"{vid_id}.{ext}")

        # 1. فحص الكاش (لو الملف متحمل جاهز)
        if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
            return ram_path, False

        # 2. محاولة البث المباشر (Direct Stream)
        # ⚠️ الخطة أ: أندرويد بدون كوكيز (أسرع وأقل مشاكل)
        print(f"🚀 Try 1: Android (No Cookies) for {vid_id}", flush=True)
        
        cmd_android = [
            "yt-dlp", "-g",
            "--extractor-args", "youtube:player_client=android", # أندرويد
            "--no-warnings", "--quiet"
            # لاحظ: مفيش --cookies هنا
        ]
        if video: cmd_android.extend(["-f", "best[height<=720]"])
        else: cmd_android.extend(["-f", "bestaudio[ext=m4a]/bestaudio"])
        cmd_android.append(link)

        process = await asyncio.create_subprocess_exec(
            *cmd_android, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()

        if stdout:
            direct_link = stdout.decode().split("\n")[0].strip()
            # تشغيل التحميل في الخلفية للكاش المستقبلي
            loop.run_in_executor(self.pool, self._background_download, link, ram_path, video)
            return direct_link, True

        # ⚠️ الخطة ب: ويب مع كوكيز (لو الأندرويد فشل)
        print(f"⚠️ Try 2: Web + Cookies for {vid_id}", flush=True)
        
        cmd_web = [
            "yt-dlp", "-g",
            "--cookies", get_cookie_file() or "", # هنا نستخدم الكوكيز
            "--no-warnings", "--quiet"
        ]
        if video: cmd_web.extend(["-f", "best[height<=720]"])
        else: cmd_web.extend(["-f", "bestaudio[ext=m4a]/bestaudio"])
        cmd_web.append(link)

        process = await asyncio.create_subprocess_exec(
            *cmd_web, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if stdout:
            direct_link = stdout.decode().split("\n")[0].strip()
            loop.run_in_executor(self.pool, self._background_download, link, ram_path, video)
            return direct_link, True
        
        # 3. الخطة ج: التحميل الكامل (Fallback) لو البث فشل تماماً
        print(f"❌ Stream Failed. Downloading...", flush=True)
        loop.run_in_executor(self.pool, self._background_download, link, ram_path, video)
        
        # ننتظر قليلاً حتى يبدأ التحميل
        for _ in range(10):
            if os.path.exists(ram_path) and os.path.getsize(ram_path) > 1024:
                return ram_path, False
            await asyncio.sleep(1)

        return None, False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split
