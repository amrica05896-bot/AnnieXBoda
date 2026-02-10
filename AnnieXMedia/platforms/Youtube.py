# file: AnnieXMedia/platforms/Youtube.py
# Authored By Certified Coders © 2026
# TitanOS Nuclear Engine: Professional Multi-Threaded Resolver
# Full Version: Metadata + Streaming + Downloader + Slider + Playlist

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiofiles
import aiohttp
import yt_dlp
from pyrogram.types import Message

# إعداد اللوجر الاحترافي
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# إعدادات المحرك النووي (Performance Tuning)
MAX_WORKERS = 40
MAX_CONCURRENT_EXTRACTS = 15
YTDLP_SOCKET_TIMEOUT = 10
PROBE_TIMEOUT = 1.5
CACHE_TTL = 3600
AIO_CONN_LIMIT = 100
DOWNLOAD_BASE = "/dev/shm" if os.path.exists("/dev/shm") else "downloads"

# محرك معالجة JSON سريع
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes): return _orjson.loads(b)
except:
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

# رؤوس استعلامات ويب احترافية (تطابق الكوكيز المكتبية)
WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # أنظمة الكاش (RAM Cache)
        self._direct_cache: Dict[str, Tuple[float, str]] = {}
        self._meta_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=360)
            self._session = aiohttp.ClientSession(connector=connector, raise_for_status=False)
        return self._session

    def get_cookie_file(self) -> Optional[str]:
        paths = [
            "AnnieXMedia/assets/cookies.txt",
            "cookies.txt",
            "assets/cookies.txt",
            "/app/cookies.txt",
            "platforms/cookies.txt"
        ]
        for p in paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        return None

    def _normalize_link(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        if videoid: return self.base + str(videoid)
        if not link: return ""
        link = link.strip()
        if "youtu.be/" in link:
            return self.base + link.split("/")[-1].split("?")[0]
        if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
            return self.base + link.split("/")[-1].split("?")[0]
        return link.split("&")[0]

    async def _exec_proc(self, *args: str, timeout: int = 15) -> Tuple[bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return out, err
        except asyncio.TimeoutError:
            with contextlib.suppress(Exception): proc.kill()
            return b"", b"timeout"

    async def _probe_url(self, url: str) -> bool:
        """مسبار ذكي للتأكد من استقرار الرابط قبل تمريره للمكتبة"""
        try:
            sess = await self._ensure_session()
            async with sess.head(url, headers=WEB_HEADERS, timeout=PROBE_TIMEOUT) as r:
                return r.status < 400
        except:
            try:
                async with sess.get(url, headers={**WEB_HEADERS, "Range": "bytes=0-1"}, timeout=PROBE_TIMEOUT) as r:
                    return r.status in (200, 206)
            except: return False

    # --- [ الدوال الأساسية للميتاداتا ] ---

    async def details(self, link: str, videoid: bool = False) -> Tuple[str, str, int, str, str]:
        prepared = self._normalize_link(link, videoid)
        if prepared in self._meta_cache:
            t, data = self._meta_cache[prepared]
            if time.time() - t < CACHE_TTL:
                return data['title'], data['dur_min'], data['dur_sec'], data['thumb'], data['id']

        def _extract():
            opts = {
                "quiet": True, "no_warnings": True, "cookiefile": self.get_cookie_file(),
                "skip_download": True, "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(prepared if "http" in prepared else f"ytsearch1:{prepared}", download=False)

        async with self.sema:
            info = await self.loop.run_in_executor(self.pool, _extract)
            if 'entries' in info: info = info['entries'][0]

        vidid = info.get("id")
        title = info.get("title", "Unknown")
        duration_sec = int(info.get("duration", 0))
        duration_min = f"{duration_sec // 60:02d}:{duration_sec % 60:02d}"
        thumbnail = f"https://img.youtube.com/vi/{vidid}/maxresdefault.jpg"

        self._meta_cache[prepared] = (time.time(), {
            'title': title, 'dur_min': duration_min, 'dur_sec': duration_sec, 'thumb': thumbnail, 'id': vidid
        })
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: bool = False) -> str:
        d = await self.details(link, videoid)
        return d[0]

    async def duration(self, link: str, videoid: bool = False) -> str:
        d = await self.details(link, videoid)
        return d[1]

    async def thumbnail(self, link: str, videoid: bool = False) -> str:
        d = await self.details(link, videoid)
        return d[3]

    # --- [ دوال البث والتحميل ] ---

    async def get_direct_link(self, link: str, video: bool = False) -> Optional[str]:
        prepared = self._normalize_link(link)
        key = f"{prepared}_{'v' if video else 'a'}"
        if key in self._direct_cache:
            t, url = self._direct_cache[prepared]
            if time.time() - t < CACHE_TTL: return url

        def _extract():
            # استخراج الروابط مع تفضيل صيغ الويب لضمان التوافق مع الكوكيز
            fmt = "best[ext=mp4]/best" if video else "bestaudio[ext=m4a]/best"
            opts = {
                "format": fmt, "quiet": True, "no_warnings": True, "cookiefile": self.get_cookie_file(),
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(prepared, download=False).get("url")

        try:
            direct_url = await self.loop.run_in_executor(self.pool, _extract)
            if direct_url and await self._probe_url(direct_url):
                self._direct_cache[key] = (time.time(), direct_url)
                return direct_url
        except: pass
        return None

    async def download(
        self, link: str, mystic: Any, video: bool = False, videoid: bool = False,
        songaudio: bool = False, songvideo: bool = False, format_id: str = None, title: str = None
    ) -> Tuple[Optional[str], bool]:
        
        prepared = self._normalize_link(link, videoid)
        is_video = bool(video or songvideo)
        
        # 1. نظام "التمرير الفوري" للبث المباشر
        if not songaudio and not songvideo:
            direct = await self.get_direct_link(prepared, is_video)
            if direct: return direct, True

        # 2. نظام التحميل الأصلي (Native) المسرع
        if mystic: await mystic.edit_text("⚡ جاري استخلاص الملف عبر المحرك النووي...")
        
        vid = prepared.split("v=")[-1]
        out_tmpl = os.path.join(DOWNLOAD_BASE, f"{vid}.%(ext)s")
        final_path = os.path.join(DOWNLOAD_BASE, f"{vid}.{'mp4' if is_video else 'm4a'}")

        if os.path.exists(final_path): return final_path, False

        opts = {
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/best",
            "outtmpl": out_tmpl, "quiet": True, "no_warnings": True, "cookiefile": self.get_cookie_file(),
            "concurrent_fragment_downloads": 10, # تحميل بـ 10 خيوط متوازية (Native)
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        }

        def _run_dl():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([prepared])
            return final_path

        try:
            path = await self.loop.run_in_executor(self.pool, _run_dl)
            return path, False
        except Exception as e:
            log.error(f"DL Error: {e}")
            return None, False

    # --- [ دوال البحث والـ Sliders ] ---

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        def _search():
            opts = {
                "quiet": True, "cookiefile": self.get_cookie_file(), "extract_flat": True,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(f"ytsearch{limit}:{query}", download=False).get('entries', [])

        entries = await self.loop.run_in_executor(self.pool, _search)
        return [{"title": e.get("title", "Unknown"), "vidid": e.get("id", ""), 
                 "duration": f"{int(e.get('duration', 0)) // 60:02d}:{int(e.get('duration', 0)) % 60:02d}"} 
                for e in entries if e]

    async def slider(self, query: str, query_type: int) -> Tuple[str, str, str, str]:
        """دالة الـ Slider المسؤولة عن التنقل بين نتائج البحث في كيبورد البوت"""
        results = await self.search(query, limit=10)
        if not results: return "None", "00:00", "", ""
        
        target = results[query_type]
        title = target["title"]
        duration = target["duration"]
        vidid = target["vidid"]
        thumbnail = f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg"
        return title, duration, thumbnail, vidid

    # --- [ دوال مساعدة إضافية ] ---

    async def playlist(self, link: str, limit: int, user_id: int = None, videoid: bool = False) -> List[str]:
        prepared = self._normalize_link(link, videoid)
        def _ids():
            opts = {"quiet": True, "extract_flat": True, "playlistend": limit, "cookiefile": self.get_cookie_file()}
            with yt_dlp.YoutubeDL(opts) as ydl:
                return [e['id'] for e in ydl.extract_info(prepared, download=False).get('entries', []) if e]
        return await self.loop.run_in_executor(self.pool, _ids)

    async def download_thumb(self, url: str) -> Optional[str]:
        path = os.path.join(DOWNLOAD_BASE, f"thumb_{int(time.time())}.jpg")
        async with await self._ensure_session() as sess:
            async with sess.get(url) as r:
                if r.status == 200:
                    async with aiofiles.open(path, "wb") as f:
                        await f.write(await r.read())
                    return path
        return None

    async def url(self, message: Message) -> Optional[str]:
        text = message.text or message.caption or ""
        ents = (message.entities or message.caption_entities or [])
        for en in ents:
            if en.type == "url":
                u = text[en.offset:en.offset + en.length]
                if self.is_valid(u): return u
        return None

    @staticmethod
    def is_valid(link: str) -> bool:
        return bool(re.search(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+', str(link)))

# تصدير نسخة المحرك النهائية الكاملة
YouTube = YouTubeAPI()
