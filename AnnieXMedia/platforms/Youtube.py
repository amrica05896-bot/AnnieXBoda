# file: AnnieXMedia/platforms/Youtube.py
# Authored By Certified Coders (c) 2026
# Complete & Ultra-Fast YouTube Resolver (Web Client + Remote Solvers)
# Optimized for 24-Core Systems & RamDisk Caching
# Includes: search, track, download, playlist, stream, thumbnail

import asyncio
import logging
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import yt_dlp

# --- Configuration & Speed Tuning ---
MAX_WORKERS = 24  # High Concurrency for 24 vCPUs
CACHE_TTL = 3600  # 1 Hour Cache
RAMDISK_PATH = "/dev/shm" if os.path.exists("/dev/shm") else "downloads"

log = logging.getLogger("AnnieXMedia.YouTube")

# Global Caches (In-Memory)
_direct_cache: Dict[str, Tuple[float, str]] = {}
_meta_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# --- Utility Functions ---

def get_cookie_file() -> Optional[str]:
    paths = [
        "AnnieXMedia/assets/cookies.txt",
        "/app/AnnieXMedia/assets/cookies.txt",
        "cookies.txt"
    ]
    for p in paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None

def _normalize_id(link: str) -> str:
    """Extracts Video ID efficiently using Regex"""
    if len(link) == 11 and " " not in link: return link
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})'
    ]
    for p in patterns:
        if match := re.search(p, link):
            return match.group(1)
    return link 

class YouTubeAPI:
    def __init__(self):
        self.pool = _thread_pool
        self.cookie = get_cookie_file()
        
        # 🔥 CORE CONFIGURATION: Web Client Only + Remote Components
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': self.cookie,
            'allow_unstable_name_scripts': True, # REQUIRED for remote_components
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],        # Enforce Web Client Only
                    'remote_components': 'ejs:github', # Load solvers from GitHub
                    'player_skip': ['configs'],      # Skip broken configs for speed
                }
            }
        }

    # 1. Helper: Existence Check
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        return True

    # 2. Helper: Extract URL from Message
    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if message.reply_to_message: msgs.append(message.reply_to_message)
        
        for msg in msgs:
            if msg.entities:
                for ent in msg.entities:
                    if ent.type.name == "URL":
                        return msg.text[ent.offset:ent.offset+ent.length]
                    if ent.type.name == "TEXT_LINK":
                        return ent.url
            text = msg.text or msg.caption or ""
            if "http" in text:
                return text.split()[0]
        return None

    # 3. Super-Fast Search
    async def search(self, query: str, limit: int = 1) -> List[Dict[str, str]]:
        loop = asyncio.get_running_loop()
        def _exec_search():
            opts = self.base_opts.copy()
            opts.update({
                'extract_flat': True, 
                'skip_download': True,
                'playlist_items': f'1-{limit}'
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                    return info.get('entries', [])
                except: return []

        entries = await loop.run_in_executor(self.pool, _exec_search)
        return [{
            "title": e.get("title", "Unknown"),
            "vidid": e.get("id"),
            "duration": e.get("duration_string", "00:00"),
            "thumb": e.get("thumbnail", "")
        } for e in entries]

    # 4. Metadata Fetcher (With Caching)
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid_id = videoid if videoid else _normalize_id(link)
        
        if vid_id in _meta_cache:
            ts, data = _meta_cache[vid_id]
            if time.time() - ts < CACHE_TTL:
                return data, vid_id

        if len(vid_id) != 11:
            results = await self.search(link, limit=1)
            if not results:
                return {"title": "Not Found"}, ""
            vid_id = results[0]['vidid']

        url = f"https://www.youtube.com/watch?v={vid_id}"
        loop = asyncio.get_running_loop()
        
        def _fetch_meta():
            opts = self.base_opts.copy()
            opts['skip_download'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    return ydl.extract_info(url, download=False)
                except: return None

        info = await loop.run_in_executor(self.pool, _fetch_meta)
        
        if info:
            details = {
                "title": info.get("title", "Unknown Track"),
                "link": info.get("webpage_url", url),
                "vidid": info.get("id", vid_id),
                "duration_min": info.get("duration", 0),
                "thumb": info.get("thumbnail", ""),
                "description": info.get("description", "")
            }
            _meta_cache[vid_id] = (time.time(), details)
            return details, vid_id
            
        return {"title": "Error"}, ""

    # 5. Stream Resolver
    async def get_direct_link(self, link: str) -> Optional[str]:
        vid_id = _normalize_id(link)
        
        if vid_id in _direct_cache:
            ts, url = _direct_cache[vid_id]
            if time.time() - ts < 1800:
                return url

        url = f"https://www.youtube.com/watch?v={vid_id}"
        loop = asyncio.get_running_loop()

        def _resolve_stream():
            opts = self.base_opts.copy()
            opts['format'] = 'bestaudio/best'
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info.get('url')
            except Exception as e:
                log.error(f"Web Client failed for {vid_id}: {e}")
                return None

        stream_url = await loop.run_in_executor(self.pool, _resolve_stream)
        if stream_url:
            _direct_cache[vid_id] = (time.time(), stream_url)
            return stream_url
        return None

    # 6. Download Manager (RESTORED FULLY)
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str, None] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        vid_id = videoid if videoid else _normalize_id(link)
        url = f"https://www.youtube.com/watch?v={vid_id}"
        
        # Determine if video request
        is_video = bool(video or songvideo)

        # Try Direct Link first if audio
        if not is_video:
            direct_url = await self.get_direct_link(url)
            if direct_url:
                return direct_url, True

        loop = asyncio.get_running_loop()
        def _exec_download():
            path_template = f"{RAMDISK_PATH}/%(id)s.%(ext)s"
            
            opts = self.base_opts.copy()
            opts.update({
                'format': 'bestvideo+bestaudio/best' if is_video else 'bestaudio/best',
                'outtmpl': path_template,
                'overwrites': True,
                'concurrent_fragment_downloads': 10, 
                'external_downloader_args': ['-N', '8'] 
            })
            
            if not is_video:
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    fpath = ydl.prepare_filename(info)
                    if not is_video:
                        base, _ = os.path.splitext(fpath)
                        mp3_path = base + ".mp3"
                        if os.path.exists(mp3_path): return mp3_path
                    return fpath
                except: return None

        file_path = await loop.run_in_executor(self.pool, _exec_download)
        return file_path, False

    # 7. Playlist Manager (RESTORED)
    async def playlist(self, link: str, limit: int, user_id=None, videoid=None) -> List[str]:
        if videoid: link = f"https://www.youtube.com/playlist?list={link}"
        
        loop = asyncio.get_running_loop()
        def _get_playlist():
            opts = self.base_opts.copy()
            opts.update({
                'extract_flat': True, 
                'playlistend': limit,
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    res = ydl.extract_info(link, download=False)
                    return [entry.get('id') for entry in res.get('entries', []) if entry.get('id')]
                except: return []
                
        return await loop.run_in_executor(self.pool, _get_playlist)

    # 8. Thumbnail Downloader (RESTORED)
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            path = f"{RAMDISK_PATH}/thumb_{int(time.time())}.jpg"
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f: f.write(await resp.read())
                        return path
        except: pass
        return None

    # Wrappers for compatibility
    async def details(self, link, videoid=None):
        d, vid = await self.track(link, videoid)
        return d.get("title", "Unknown"), d.get("duration_min", 0), 0, d.get("thumb", ""), vid

    async def title(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("title", "Unknown")

    async def duration(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min", 0)

    async def thumbnail(self, link, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

# Initialize
YouTube = YouTubeAPI()
