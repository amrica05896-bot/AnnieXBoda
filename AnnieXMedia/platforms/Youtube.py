# file: AnnieXMedia/platforms/Youtube.py
# 🚀 Built strictly on 'pytubefix' Official Docs (2026)
# 🛑 NO yt-dlp, NO Local Downloads, Live Stream Only (Zero OOM)

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

import aiohttp
from pytubefix import YouTube, Search, Playlist
from pytubefix.exceptions import PytubeFixError

# Logging Setup
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# Caching to avoid redundant YouTube requests (Saves CPU & Time)
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

META_CACHE_TTL = 3600  # 1 Hour
CACHE_DEFAULT_TTL = 21600  # 6 Hours for stream URLs

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid:
        return f"https://www.youtube.com/watch?v={videoid}"
    if not link:
        return ""
    link = link.strip()
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self._aio_session: Optional[aiohttp.ClientSession] = None

    async def _ensure_aio_session(self) -> aiohttp.ClientSession:
        if self._aio_session is None or self._aio_session.closed:
            self._aio_session = aiohttp.ClientSession()
        return self._aio_session

    async def url(self, message) -> Optional[str]:
        """Extract URL from a pyrogram Message-like object."""
        if not message:
            return None
        msgs = [message]
        if getattr(message, "reply_to_message", None):
            msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    t = getattr(ent, "type", None)
                    off = getattr(ent, "offset", None)
                    ln = getattr(ent, "length", None)
                    if t == "url" and off is not None and ln is not None:
                        return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u:
                        return u.split("&si")[0]
                except Exception:
                    continue
        return None

    def _sec_to_str(self, sec: int) -> str:
        if not sec: return "0:00"
        m = sec // 60
        s = sec % 60
        return f"{m}:{s:02d}"

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except: return 0

    # 🚀 1. Search Engine (pytubefix)
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        loop = asyncio.get_running_loop()
        def _execute_search():
            try:
                s = Search(query)
                results = []
                for v in s.videos[:limit]:
                    results.append({
                        "title": v.title,
                        "vidid": v.video_id,
                        "duration": self._sec_to_str(v.length)
                    })
                return results
            except Exception as e:
                log.error(f"Search Error: {e}")
                return []
        return await loop.run_in_executor(None, _execute_search)

    # 🚀 2. Metadata Extraction (pytubefix)
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL:
                    return data, vid
                _meta_cache.pop(key, None)

        loop = asyncio.get_running_loop()
        def _get_track():
            try:
                yt = YouTube(prepared, client='WEB') # Using WEB client as per docs for better stability
                details = {
                    "title": yt.title,
                    "link": prepared,
                    "vidid": yt.video_id,
                    "duration_min": self._sec_to_str(yt.length),
                    "thumb": yt.thumbnail_url
                }
                return details, yt.video_id
            except Exception as e:
                log.error(f"Track Extract Error for {prepared}: {e}")
                return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "0:00", "thumb": ""}, ""
                
        details, vid = await loop.run_in_executor(None, _get_track)
        
        if vid:
            async with _meta_cache_lock:
                _meta_cache[key] = (now, details, vid)
                
        return details, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min")
        sec = self._to_seconds(dur)
        return data.get("title", ""), dur, sec, data.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("title", "")

    async def duration(self, link: str, videoid: Union[bool, str, None] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid)
        return d.get("thumb", "")

    # 🚀 Download Thumbnail using aiohttp (Required for TG Messages)
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            base_dir = "downloads"
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            
            session = await self._ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return path
        except Exception as e:
            log.warning(f"Failed to download thumbnail: {e}")
        return None

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        # Dummy formats for compatibility
        prepared = _normalize_link(link, videoid)
        return [{"format_id": "direct", "ext": "mp4"}], prepared

    # 🚀 3. Extract Direct Stream URL (pytubefix)
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # Check Cache
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 60: # Valid if more than 60s left
                    return url
                _direct_cache.pop(key, None)

        loop = asyncio.get_running_loop()
        def _extract_direct():
            try:
                # Use WEB client to bypass some restrictions, falls back safely
                yt = YouTube(prepared, client='WEB')
                if prefer_audio:
                    # Extracts m4a (MPEG-4 AAC) as per the pytubefix docs
                    stream = yt.streams.get_audio_only()
                else:
                    stream = yt.streams.get_highest_resolution()
                
                return stream.url if stream else None
            except Exception as e:
                log.error(f"Direct Link Error for {prepared}: {e}")
                return None

        url = await loop.run_in_executor(None, _extract_direct)
        
        # Save to cache
        if url:
            async with _direct_cache_lock:
                _direct_cache[key] = (now + CACHE_DEFAULT_TTL, url)
                
        return url

    # 🚀 4. "Fake" Download Method (Returns Live Stream directly)
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        """
        🚫 NO LOCAL DOWNLOADING 🚫
        Bypasses download and returns the direct M3U8/MP4 stream url.
        The `True` boolean signals the caller (call.py) that this is a direct stream.
        """
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        
        # Get raw stream link from YouTube
        direct_url = await self.get_direct_link(prepared, prefer_audio=not is_video)
        
        if not direct_url:
            return None, False
            
        return direct_url, True

    # 🚀 5. Extract Playlist Details (pytubefix)
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + str(videoid)
        if "&" in link: link = link.split("&")[0]
        
        loop = asyncio.get_running_loop()
        def _get_playlist():
            try:
                pl = Playlist(link)
                vids = []
                for url in pl.video_urls:
                    try:
                        vid = url.split("v=")[1].split("&")[0]
                        vids.append(vid)
                        if len(vids) >= limit: break
                    except: continue
                return vids
            except Exception as e:
                log.error(f"Playlist Error: {e}")
                return []
                
        return await loop.run_in_executor(None, _get_playlist)

# exported instance
YouTube = YouTubeAPI()
