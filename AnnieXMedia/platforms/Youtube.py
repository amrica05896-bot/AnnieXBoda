# file: AnnieXMedia/platforms/Youtube.py
# 🚀 Ultra-Lightweight YouTube API using ytubefix & ytmusicapi
# No yt-dlp, No local downloads (Live Stream Only)

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from ytmusicapi import YTMusic
from pytubefix import YouTube as YTFix, Playlist
# Logging Setup
log = logging.getLogger("AnnieXMedia.YouTube")
log.setLevel(logging.INFO)

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
        self.ytmusic = YTMusic()
        self._aio_session = None

    async def _ensure_aio_session(self) -> aiohttp.ClientSession:
        if self._aio_session is None or self._aio_session.closed:
            self._aio_session = aiohttp.ClientSession()
        return self._aio_session

    async def url(self, message) -> Optional[str]:
        """Extract URL from a pyrogram Message-like object."""
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None):
            msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    if getattr(ent, "type", None) == "url":
                        return text[ent.offset: ent.offset + ent.length].split("&si")[0]
                    if getattr(ent, "url", None):
                        return getattr(ent, "url").split("&si")[0]
                except: continue
        return None

    # 🚀 1. بحث سريع جداً عن طريق YTMusic
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        loop = asyncio.get_running_loop()
        def _execute_search():
            try:
                results = self.ytmusic.search(query, filter="songs", limit=limit)
                parsed = []
                for r in results:
                    parsed.append({
                        "title": r.get("title", "Unknown"),
                        "vidid": r.get("videoId", ""),
                        "duration": r.get("duration", "0:00")
                    })
                return parsed
            except Exception as e:
                log.error(f"YTMusic Search Error: {e}")
                return []
        return await loop.run_in_executor(None, _execute_search)

    # 🚀 2. جلب التفاصيل باستخدام ytubefix (بدون تحميل)
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        loop = asyncio.get_running_loop()
        
        def _get_track():
            try:
                yt = YTFix(prepared, client='WEB') # WEB client for stability
                sec = yt.length
                mins = f"{sec // 60}:{sec % 60:02d}"
                details = {
                    "title": yt.title,
                    "link": prepared,
                    "vidid": yt.video_id,
                    "duration_min": mins,
                    "thumb": yt.thumbnail_url
                }
                return details, yt.video_id
            except Exception as e:
                log.error(f"Track Extract Error: {e}")
                return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "0:00", "thumb": ""}, ""
                
        return await loop.run_in_executor(None, _get_track)

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
        except: pass
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except: return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        return [{"format_id": "direct", "ext": "mp4"}], prepared

    # 🚀 3. جلب الرابط المباشر للبث (Live Stream Only)
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        loop = asyncio.get_running_loop()

        def _extract_direct():
            try:
                yt = YTFix(prepared, client='WEB')
                if prefer_audio:
                    stream = yt.streams.get_audio_only()
                else:
                    stream = yt.streams.get_highest_resolution()
                return stream.url if stream else None
            except Exception as e:
                log.error(f"Direct Link Error: {e}")
                return prepared # Fallback

        return await loop.run_in_executor(None, _extract_direct)

    # 🚀 4. دالة التحميل الوهمية (تحاكي التحميل لعدم كسر البوت)
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
        لا يوجد تحميل هنا! ترجع الدالة الرابط المباشر فوراً كبث.
        الـ True تعني للـ Call.py أن هذا Stream وليس ملف محلي.
        """
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        
        direct_url = await self.get_direct_link(prepared, prefer_audio=not is_video)
        
        # Return the direct URL and 'True' to indicate it's a direct stream
        return direct_url, True

    # 🚀 5. استخراج القوائم بسرعة باستخدام Playlist
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + str(videoid)
        if "&" in link: link = link.split("&")[0]
        
        loop = asyncio.get_running_loop()
        def _get_playlist():
            try:
                pl = Playlist(link)
                # Fetch only up to 'limit' to be fast
                return [video.video_id for video in pl.videos[:limit]]
            except Exception as e:
                log.error(f"Playlist Error: {e}")
                return []
                
        return await loop.run_in_executor(None, _get_playlist)

# exported instance
YouTube = YouTubeAPI()
