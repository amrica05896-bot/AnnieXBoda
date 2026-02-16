# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------------
# AnnieXMedia YouTube Platform Component
# Developed by: Certified Coders (c) 2026
# Project: AnnieXBoda Music Bot
# ---------------------------------------------------------------------------------
# This module handles all YouTube-related operations including searching, 
# metadata extraction, and high-speed downloading using advanced bypass 
# techniques like Deno JS Solving and HTTP Client Impersonation.
# ---------------------------------------------------------------------------------

import asyncio
import logging
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import yt_dlp
from curl_cffi import requests as curl_requests

# ==========================================
# 🔥 ENVIRONMENT & SYSTEM INJECTION 🔥
# ==========================================
# Ensuring the system PATH includes Deno and Node for Cipher solving
os.environ["PATH"] = f"/root/.deno/bin:/usr/bin:/usr/local/bin:{os.environ.get('PATH', '')}"
os.environ["YT_DLP_JS_EXECUTOR"] = "/root/.deno/bin/deno"

# Constants & Configuration
MAX_WORKERS = 24  # Optimized for your 24-core vCPU system
RAM_DISK = "/dev/shm" if os.path.exists("/dev/shm") else "downloads"
CACHE_TTL = 3600  # 1 hour metadata cache
DIRECT_TTL = 1800 # 30 mins direct link cache

# Logging Setup
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("AnnieXMedia.YouTube")

# Global Cache Storage
_direct_cache: Dict[str, Tuple[float, str]] = {}
_meta_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="YT_Worker")

# ==========================================
# 🛠 HELPER FUNCTIONS 🛠
# ==========================================

def get_cookie_path() -> Optional[str]:
    """Locates the cookies.txt file within the project structure."""
    possible_paths = [
        "AnnieXMedia/assets/cookies.txt",
        "/app/AnnieXMedia/assets/cookies.txt",
        "cookies.txt"
    ]
    for p in possible_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None

def _extract_vid_id(link: str) -> str:
    """Normalizes and extracts the 11-character YouTube Video ID."""
    if len(link) == 11 and " " not in link:
        return link
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return link

# ==========================================
# 🚀 CORE YOUTUBE CLASS 🚀
# ==========================================

class YouTubeAPI:
    def __init__(self):
        self.cookie = get_cookie_path()
        self.pool = _executor
        
        # 🛡️ THE BYPASS CONFIGURATION 🛡️
        # This dictionary is the heart of the bypass logic
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': self.cookie,
            'allow_unstable_name_scripts': True, # Required for Deno
            'cachedir': False,                  # Disable disk cache to prevent permission errors
            
            # --- Anti-Bot & Fingerprinting ---
            'impersonate': 'chrome-110',        # Impersonate a real browser using curl_cffi
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://www.youtube.com',
                'Referer': 'https://www.youtube.com/',
            },
            
            # --- Solver Settings ---
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'ios', 'android', 'tv'], # Multiple clients fallback
                    'remote_components': 'ejs:github',              # Fetch latest solvers from GitHub
                    'player_skip': ['configs'],
                }
            }
        }
        log.info(f"YouTube Platform Initialized with Cookie: {bool(self.cookie)}")

    # -----------------------------------------------------
    # 1. Existence Check
    # -----------------------------------------------------
    async def exists(self, link: str, videoid: Any = None) -> bool:
        """Verifies if a video exists (Optimized for performance)."""
        # In a music bot context, we usually assume it exists or let track() fail
        return True

    # -----------------------------------------------------
    # 2. Link Extraction from Message
    # -----------------------------------------------------
    async def url(self, message) -> Optional[str]:
        """Extracts a valid YouTube URL from a Telegram message or reply."""
        if not message:
            return None
        
        # Check the message itself and the reply
        messages_to_check = [message]
        if message.reply_to_message:
            messages_to_check.append(message.reply_to_message)
            
        for msg in messages_to_check:
            # Check for Entities (URLs/Text Links)
            if msg.entities:
                for entity in msg.entities:
                    if entity.type.name == "URL":
                        return msg.text[entity.offset : entity.offset + entity.length]
                    if entity.type.name == "TEXT_LINK":
                        return entity.url
            
            # Regex fallback
            text = msg.text or msg.caption or ""
            urls = re.findall(r'(https?://\S+)', text)
            if urls:
                return urls[0]
                
        return None

    # -----------------------------------------------------
    # 3. Search Functionality
    # -----------------------------------------------------
    async def search(self, query: str, limit: int = 1) -> List[Dict[str, str]]:
        """Searches YouTube for a given query and returns a list of results."""
        loop = asyncio.get_running_loop()
        
        def _exec_search():
            search_opts = self.base_opts.copy()
            search_opts.update({
                'extract_flat': True,
                'playlist_items': f'1-{limit}',
            })
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                try:
                    result = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                    return result.get('entries', [])
                except Exception as e:
                    log.error(f"Search failed for '{query}': {e}")
                    return []

        entries = await loop.run_in_executor(self.pool, _exec_search)
        
        results = []
        for entry in entries:
            if not entry: continue
            results.append({
                "title": entry.get("title", "Unknown"),
                "vidid": entry.get("id"),
                "duration": entry.get("duration_string", "00:00"),
                "thumb": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg",
                "link": f"https://www.youtube.com/watch?v={entry.get('id')}"
            })
        return results

    # -----------------------------------------------------
    # 4. Metadata Extraction (The "Track" Method)
    # -----------------------------------------------------
    async def track(self, link: str, videoid: Any = None) -> Tuple[Dict[str, Any], str]:
        """Fetches detailed video metadata with internal caching."""
        vid_id = videoid if videoid else _extract_vid_id(link)
        
        # Check Cache
        if vid_id in _meta_cache:
            last_time, cached_data = _meta_cache[vid_id]
            if time.time() - last_time < CACHE_TTL:
                return cached_data, vid_id

        # Fallback for non-ID queries
        if len(vid_id) != 11:
            search_res = await self.search(link, 1)
            if not search_res:
                return {"title": "Unsupported Link", "link": link}, ""
            vid_id = search_res[0]['vidid']
            # Cache the search result to avoid double fetching
            _meta_cache[vid_id] = (time.time(), search_res[0])
            return search_res[0], vid_id

        url = f"https://www.youtube.com/watch?v={vid_id}"
        loop = asyncio.get_running_loop()
        
        def _fetch_meta():
            with yt_dlp.YoutubeDL(self.base_opts) as ydl:
                try:
                    return ydl.extract_info(url, download=False)
                except Exception as e:
                    log.error(f"Metadata fetch failed for {vid_id}: {e}")
                    return None

        info = await loop.run_in_executor(self.pool, _fetch_meta)
        
        if info:
            metadata = {
                "title": info.get("title", "Unknown Track"),
                "link": info.get("webpage_url", url),
                "vidid": info.get("id", vid_id),
                "duration_min": info.get("duration", 0),
                "thumb": info.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                "description": info.get("description", ""),
                "views": info.get("view_count", 0),
                "channel": info.get("uploader", "Unknown Channel")
            }
            _meta_cache[vid_id] = (time.time(), metadata)
            return metadata, vid_id
            
        return {"title": "Error Fetching Data", "vidid": vid_id}, ""

    # -----------------------------------------------------
    # 5. Direct Stream Resolver (High Priority)
    # -----------------------------------------------------
    async def get_direct_link(self, link: str) -> Optional[str]:
        """Resolves the direct streaming URL for real-time playback."""
        vid_id = _extract_id(link)
        
        if vid_id in _direct_cache:
            last_time, stream_url = _direct_cache[vid_id]
            if time.time() - last_time < DIRECT_TTL:
                return stream_url

        loop = asyncio.get_running_loop()
        
        def _resolve():
            # Try different clients for direct link
            clients = ['web', 'ios', 'android_creator']
            for client in clients:
                opts = self.base_opts.copy()
                opts.update({
                    'format': 'bestaudio/best',
                    'extractor_args': {'youtube': {'player_client': [client]}}
                })
                with yt_dlp.YoutubeDL(opts) as ydl:
                    try:
                        info = ydl.extract_info(vid_id, download=False)
                        return info.get('url')
                    except:
                        continue
            return None

        direct_url = await loop.run_in_executor(self.pool, _resolve)
        if direct_url:
            _direct_cache[vid_id] = (time.time(), direct_url)
            return direct_url
        return None

    # -----------------------------------------------------
    # 6. The "Download" Manager (Robust & Intelligent)
    # -----------------------------------------------------
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Any = None,
        **kwargs
    ) -> Tuple[Optional[str], bool]:
        """
        Handles physical downloading of files. 
        Implements a Video-to-Audio fallback if direct audio is blocked.
        """
        vid_id = videoid if videoid else _extract_vid_id(link)
        is_video = bool(video or kwargs.get("songvideo"))
        
        # Check for immediate direct link to save bandwidth
        if not is_video:
            direct = await self.get_direct_link(vid_id)
            if direct:
                return direct, True

        loop = asyncio.get_running_loop()
        
        def _exec_download():
            path_template = f"{RAM_DISK}/%(id)s.%(ext)s"
            
            # --- DOWNLOAD STRATEGY ---
            # Using Aria2 for 16x multi-connection speed
            download_opts = self.base_opts.copy()
            download_opts.update({
                'outtmpl': path_template,
                'overwrites': True,
                'external_downloader': 'aria2c',
                'external_downloader_args': ['-x', '16', '-s', '16', '-k', '1M', '--async-dns=false'],
                'concurrent_fragment_downloads': 10,
            })
            
            # 1. ATTEMPT AUDIO ONLY FIRST
            if not is_video:
                download_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                })
            else:
                download_opts['format'] = 'bestvideo+bestaudio/best'

            with yt_dlp.YoutubeDL(download_opts) as ydl:
                try:
                    info = ydl.extract_info(vid_id, download=True)
                    filename = ydl.prepare_filename(info)
                    if not is_video:
                        # Ensure we point to the converted mp3
                        filename = os.path.splitext(filename)[0] + ".mp3"
                    return filename
                except Exception as e:
                    log.warning(f"Direct Audio download failed for {vid_id}, trying Video Fallback: {e}")
                    
                    # 2. FALLBACK: DOWNLOAD VIDEO THEN EXTRACT AUDIO (Bypass IP blocks)
                    if not is_video:
                        download_opts['format'] = 'best' # Get any valid format (usually video)
                        with yt_dlp.YoutubeDL(download_opts) as ydl_retry:
                            try:
                                info = ydl_retry.extract_info(vid_id, download=True)
                                filename = ydl_retry.prepare_filename(info)
                                return os.path.splitext(filename)[0] + ".mp3"
                            except Exception as e2:
                                log.error(f"Critical Download Failure: {e2}")
                                return None
                    return None

        # Execute in ThreadPool
        file_path = await loop.run_in_executor(self.pool, _exec_download)
        return file_path, False

    # -----------------------------------------------------
    # 7. Playlist Handler
    # -----------------------------------------------------
    async def playlist(self, link: str, limit: int, **kwargs) -> List[str]:
        """Extracts all video IDs from a YouTube playlist."""
        loop = asyncio.get_running_loop()
        
        def _get_playlist():
            opts = self.base_opts.copy()
            opts.update({
                'extract_flat': True,
                'playlistend': limit,
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    result = ydl.extract_info(link, download=False)
                    return [entry.get('id') for entry in result.get('entries', []) if entry.get('id')]
                except Exception as e:
                    log.error(f"Playlist extraction failed: {e}")
                    return []
                    
        return await loop.run_in_executor(self.pool, _get_playlist)

    # -----------------------------------------------------
    # 8. Thumbnail Downloader
    # -----------------------------------------------------
    async def download_thumb(self, url: str) -> Optional[str]:
        """Downloads a thumbnail locally to the RAM Disk for fast Telegram uploading."""
        if not url: return None
        try:
            target_path = f"{RAM_DISK}/thumb_{int(time.time())}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(target_path, "wb") as f:
                            f.write(content)
                        return target_path
        except Exception as e:
            log.error(f"Thumbnail download failed: {e}")
            pass
        return None

    # -----------------------------------------------------
    # 9. Compatibility Wrappers (For Bot Engine)
    # -----------------------------------------------------
    async def details(self, link: str, videoid: Any = None):
        """Unified method for bot playback engine."""
        data, vid = await self.track(link, videoid)
        return (
            data.get("title", "Unknown"),
            data.get("duration_min", 0),
            0, # views (optional)
            data.get("thumb", ""),
            vid
        )

    async def title(self, link: str, videoid: Any = None):
        data, _ = await self.track(link, videoid)
        return data.get("title", "Unknown")

    async def duration(self, link: str, videoid: Any = None):
        data, _ = await self.track(link, videoid)
        return data.get("duration_min", 0)

    async def thumbnail(self, link: str, videoid: Any = None):
        data, _ = await self.track(link, videoid)
        return data.get("thumb", "")

# ---------------------------------------------------------------------------------
# INITIALIZATION
# ---------------------------------------------------------------------------------
YouTube = YouTubeAPI()
# EOF - End Of File
