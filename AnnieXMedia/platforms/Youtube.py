# file: AnnieXMedia/platforms/Youtube.py
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

import aiohttp
# 👈 تم تغيير الاسم هنا لـ YTFix لمنع التداخل مع كود البوت
from pytubefix import YouTube as YTFix, Search, Playlist

log = logging.getLogger("AnnieXMedia.YouTube")
log.setLevel(logging.INFO)

_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

META_CACHE_TTL = 3600
CACHE_DEFAULT_TTL = 21600

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid: return f"https://www.youtube.com/watch?v={videoid}"
    if not link: return ""
    link = link.strip()
    if "youtu.be/" in link: return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link: return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self._aio_session = None

    async def _ensure_aio_session(self) -> aiohttp.ClientSession:
        if self._aio_session is None or self._aio_session.closed:
            self._aio_session = aiohttp.ClientSession()
        return self._aio_session

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
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

    def _sec_to_str(self, sec: int) -> str:
        if not sec: return "0:00"
        return f"{sec // 60}:{sec % 60:02d}"

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except: return 0

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        loop = asyncio.get_running_loop()
        def _execute_search():
            try:
                s = Search(query)
                results = []
                for v in s.videos[:limit]:
                    results.append({"title": v.title, "vidid": v.video_id, "duration": self._sec_to_str(v.length)})
                return results
            except Exception as e:
                log.error(f"Search Error: {e}")
                return []
        return await loop.run_in_executor(None, _execute_search)

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid
                _meta_cache.pop(key, None)

        loop = asyncio.get_running_loop()
        def _get_track():
            try:
                # 👈 استخدام YTFix المستعار
                yt = YTFix(prepared, client='WEB') 
                details = {
                    "title": yt.title, "link": prepared, "vidid": yt.video_id,
                    "duration_min": self._sec_to_str(yt.length), "thumb": yt.thumbnail_url
                }
                return details, yt.video_id
            except Exception as e:
                log.error(f"Track Extract Error for {prepared}: {e}")
                return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": "0:00", "thumb": ""}, ""
                
        details, vid = await loop.run_in_executor(None, _get_track)
        if vid:
            async with _meta_cache_lock: _meta_cache[key] = (now, details, vid)
        return details, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        return data.get("title", ""), data.get("duration_min"), self._to_seconds(data.get("duration_min")), data.get("thumb", ""), vid

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
                    with open(path, "wb") as f: f.write(await resp.read())
                    return path
        except: pass
        return None

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        return [{"format_id": "direct", "ext": "mp4"}], prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now + 60: return cached[1]
            if cached: _direct_cache.pop(key, None)

        loop = asyncio.get_running_loop()
        def _extract_direct():
            try:
                # 👈 استخدام YTFix المستعار
                yt = YTFix(prepared, client='WEB')
                stream = yt.streams.get_audio_only() if prefer_audio else yt.streams.get_highest_resolution()
                return stream.url if stream else None
            except Exception as e:
                log.error(f"Direct Link Error for {prepared}: {e}")
                return None

        url = await loop.run_in_executor(None, _extract_direct)
        if url:
            async with _direct_cache_lock: _direct_cache[key] = (now + CACHE_DEFAULT_TTL, url)
        return url

    async def download(self, link: str, mystic: Any, video: Union[bool, str] = None, videoid: Union[bool, str] = None, songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None, title: Union[bool, str] = None) -> Tuple[Optional[str], bool]:
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        direct_url = await self.get_direct_link(prepared, prefer_audio=not is_video)
        if not direct_url: return None, False
        return direct_url, True

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
                        vids.append(url.split("v=")[1].split("&")[0])
                        if len(vids) >= limit: break
                    except: continue
                return vids
            except Exception as e:
                log.error(f"Playlist Error: {e}")
                return []
        return await loop.run_in_executor(None, _get_playlist)

YouTube = YouTubeAPI()
