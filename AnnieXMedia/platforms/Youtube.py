# file: AnnieXMedia/platforms/Youtube.py
# The Masterpiece: Python + C++ + Rust (via Libraries)
# Architecture: Hybrid FFI (Foreign Function Interface)

import asyncio
import ctypes
import json
import logging
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import yt_dlp

# --- [ 1. LOAD C++ CORE ] ---
# تحميل المحرك اللي كتبناه فوق
CORE_PATH = os.path.abspath("AnnieXMedia/platforms/youtube_core.so")
cpp_core = None

try:
    if os.path.exists(CORE_PATH):
        cpp_core = ctypes.CDLL(CORE_PATH)
        # تعريف دوال C++ للبايثون
        cpp_core.analyze_link_type.argtypes = [ctypes.c_char_p]
        cpp_core.analyze_link_type.restype = ctypes.c_int
        
        cpp_core.extract_video_id.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        cpp_core.extract_video_id.restype = None
        
        logging.info("✅ C++ Quantum Core Loaded Successfully!")
    else:
        logging.warning("⚠️ C++ Core not found! Falling back to Python Legacy Mode.")
except Exception as e:
    logging.error(f"❌ Failed to load C++ Core: {e}")

# --- [ 2. Rust-Powered JSON ] ---
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes): return _orjson.loads(b)
except ImportError:
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

# --- [ 3. Config ] ---
log = logging.getLogger("AnnieXMedia.YouTube")
MAX_WORKERS = 20
_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_connector = aiohttp.TCPConnector(limit=100)
_session = None

COOKIE_PATHS = ["AnnieXMedia/assets/cookies.txt", "cookies.txt"]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        if os.path.exists(p): return os.path.abspath(p)
    return None

class YouTubeAPI:
    def __init__(self):
        self.cookie = get_cookie_file()

    # ---------------------------------------------------
    # 🧬 HYBRID METHOD: Uses C++ for Logic, Python for Net
    # ---------------------------------------------------
    async def video(self, link: str, videoid: Union[bool, str] = None) -> Tuple[Dict[str, Any], str]:
        """
        The Ultimate Solver.
        1. Uses C++ to analyze link type instantly.
        2. Decides strategy (Live vs Video vs Search).
        3. Executes High-Speed Download/Stream.
        """
        # A. C++ Analysis (If available)
        link_type = 0
        if cpp_core and link:
            # Convert str to bytes for C++
            b_link = link.encode('utf-8')
            link_type = cpp_core.analyze_link_type(b_link)
            # Types: 0=Search, 1=Video, 2=Shorts, 3=Live
        
        # B. Metadata Fetching
        details, vid = await self.track(link, videoid)
        
        # C. Strategy Decision
        is_live = details.get("is_live") or link_type == 3
        
        # Priority 1: Direct Stream (For Live & Fast Play)
        try:
            # Live streams require specific HLS handling
            if is_live:
                stream = await self.get_direct_link(details['link'], prefer_audio=False)
                if stream: return details, stream
            
            # Normal videos try direct link first
            stream = await self.get_direct_link(details['link'], prefer_audio=True)
            if stream: return details, stream
        except: pass

        # Priority 2: High-Speed Download (Parallel)
        path, _ = await self.download(details['link'], video=True, videoid=vid)
        return details, path

    # ---------------------------------------------------
    # Standard Methods (Optimized)
    # ---------------------------------------------------
    async def track(self, link: str, videoid=None):
        # Normalize Link
        if videoid is True: videoid = None
        prepared = f"https://www.youtube.com/watch?v={videoid}" if videoid else link
        
        def _fetch():
            opts = {
                "quiet": True, "no_warnings": True, "skip_download": True,
                "cookiefile": self.cookie, "socket_timeout": 10,
                "extractor_args": {"youtube": {"player_client": ["web"], "player_skip": ["webpage", "configs", "js"]}}
            }
            # Auto-Search if C++ says it's not a URL (Type 0)
            if "http" not in prepared: opts["default_search"] = "ytsearch"
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(prepared, download=False)
                if "entries" in info: return info["entries"][0]
                return info

        info = await asyncio.get_running_loop().run_in_executor(_pool, _fetch)
        
        is_live = info.get("is_live") or info.get("was_live") or False
        thumb = (info.get("thumbnail") or "").split("?")[0]
        
        details = {
            "title": info.get("title", "Unknown"),
            "link": info.get("webpage_url", prepared),
            "vidid": info.get("id", ""),
            "duration_min": "Live" if is_live else info.get("duration_string"),
            "thumb": thumb,
            "is_live": is_live
        }
        return details, info.get("id", "")

    async def get_direct_link(self, link, prefer_audio=True):
        def _get():
            opts = {
                "quiet": True, "no_warnings": True, "skip_download": True,
                "cookiefile": self.cookie,
                "format": "bestaudio/best" if prefer_audio else "best[ext=mp4]/best",
                "extractor_args": {"youtube": {"player_client": ["web"], "player_skip": ["webpage", "configs", "js"]}}
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(link, download=False).get("url")
        
        return await asyncio.get_running_loop().run_in_executor(_pool, _get)

    async def download(self, link, mystic=None, video=False, videoid=None, **kwargs):
        vid = str(int(time.time()))
        
        # C++ Optimized ID Extraction
        if cpp_core and link:
            id_buf = ctypes.create_string_buffer(12) # 11 chars + null terminator
            cpp_core.extract_video_id(link.encode('utf-8'), id_buf)
            extracted_id = id_buf.value.decode('utf-8')
            if extracted_id != "00000000000":
                vid = extracted_id
        elif videoid:
            vid = videoid

        ram_path = f"/dev/shm/{vid}"
        
        def _dl():
            fmt = "best[ext=mp4]" if video else "bestaudio[ext=m4a]"
            opts = {
                "format": fmt, "outtmpl": f"{ram_path}.%(ext)s",
                "cookiefile": self.cookie, "quiet": True,
                "concurrent_fragment_downloads": 5,
                "extractor_args": {"youtube": {"player_client": ["web"], "player_skip": ["webpage", "configs", "js"]}}
            }
            if not video:
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
                opts["merge_output_format"] = "mp3" # Force clean MP3
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        path = await asyncio.get_running_loop().run_in_executor(_pool, _dl)
        
        # Audio Post-Processing Fix
        if not video and path and not path.endswith(".mp3"):
            mp3_path = os.path.splitext(path)[0] + ".mp3"
            if os.path.exists(mp3_path): return mp3_path, False
            
        return path, False

    # Interfaces
    async def url(self, message):
        if not message or not message.text: return None
        return message.text.split(" ")[0] if "http" in message.text else None

    async def title(self, link, videoid=None): 
        d, _ = await self.track(link, videoid); return d.get("title", "")
    async def duration(self, link, videoid=None): 
        d, _ = await self.track(link, videoid); return d.get("duration_min")
    async def thumbnail(self, link, videoid=None): 
        d, _ = await self.track(link, videoid); return d.get("thumb", "")
    async def details(self, link, videoid=None):
        d, v = await self.track(link, videoid)
        return d.get("title"), d.get("duration_min"), 0, d.get("thumb"), v

YouTube = YouTubeAPI()
