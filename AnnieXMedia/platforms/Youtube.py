# file: AnnieXMedia/platforms/Youtube.py
# Powered Exclusively by Invidious API (No yt-dlp)
# Authored By Certified Coders © 2026

import asyncio
import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import aiofiles

import logging

# Logging Setup
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# 🌐 قائمة سيرفرات Invidious الموثوقة (لضمان عدم توقف البوت إذا تعطل سيرفر)
INVIDIOUS_INSTANCES = [
    "https://invidious.nerdvpn.de",
    "https://vid.puffyan.us",
    "https://invidious.weblibre.org",
    "https://invidious.fdn.fr",
    "https://invidious.perennialte.ch"
]

META_CACHE_TTL = 3600
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()

_aio_connector = aiohttp.TCPConnector(limit=100, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid:
        return str(videoid)
    if not link:
        return ""
    link = link.strip().split("&")[0]
    
    # استخراج الـ ID من الرابط
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", link)
    if match:
        return match.group(1)
    return link

def _format_time(seconds: int) -> str:
    if seconds == 0:
        return "Live"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

class YouTubeAPI:
    def __init__(self):
        self.base = "https://youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.instances = INVIDIOUS_INSTANCES

    async def _api_call(self, endpoint: str, params: dict = None) -> Optional[Dict[str, Any]]:
        """دالة ذكية تتصل بسيرفرات Invidious بالترتيب حتى تنجح"""
        sess = await _ensure_aio_session()
        for instance in self.instances:
            url = f"{instance}{endpoint}"
            try:
                async with sess.get(url, params=params, timeout=4) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception as e:
                log.debug(f"Invidious instance {instance} failed: {e}")
                continue
        return None

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None):
            msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    t = getattr(ent, "type", None)
                    if t == "url":
                        off, ln = getattr(ent, "offset"), getattr(ent, "length")
                        return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u: return u.split("&si")[0]
                except Exception: continue
        return None

    # 🚀 البحث السريع باستخدام Invidious API
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        params = {"q": query, "type": "video", "region": "US"}
        data = await self._api_call("/api/v1/search", params=params)
        
        results = []
        if data and isinstance(data, list):
            for item in data[:limit]:
                if item.get("type") == "video":
                    duration = item.get("lengthSeconds", 0)
                    results.append({
                        "title": item.get("title", "Unknown"),
                        "vidid": item.get("videoId", ""),
                        "duration": _format_time(duration)
                    })
        return results

    # 🚀 جلب تفاصيل الفيديو
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid = _normalize_link(link, videoid)
        
        # إذا لم يكن رابطاً أو ID (طوله 11 حرف)، نقوم بالبحث
        if len(vid) != 11:
            results = await self.search(vid, limit=1)
            if not results:
                return {"title": "Unknown", "vidid": "", "duration_min": "0:00", "thumb": ""}, ""
            vid = results[0]["vidid"]

        key = "q:" + vid
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, cached_vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL:
                    return data, cached_vid

        api_data = await self._api_call(f"/api/v1/videos/{vid}")
        
        if api_data:
            title = api_data.get("title", "Unknown")
            length_seconds = api_data.get("lengthSeconds", 0)
            is_live = api_data.get("liveNow", False)
            duration_min = "Live" if is_live else _format_time(length_seconds)
            
            # جلب أفضل جودة صورة مصغرة
            thumbnails = api_data.get("videoThumbnails", [])
            thumb = thumbnails[-1].get("url", "") if thumbnails else ""
            
            details = {
                "title": title,
                "link": f"https://youtube.com/watch?v={vid}",
                "vidid": vid,
                "duration_min": duration_min,
                "thumb": thumb
            }
            
            async with _meta_cache_lock:
                _meta_cache[key] = (now, details, vid)
            return details, vid

        return {"title": "Unknown", "link": link, "vidid": "", "duration_min": "0:00", "thumb": ""}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if not vid:
            raise ValueError("Video not found")
        dur = data.get("duration_min")
        sec = 0 if str(dur).lower() in ["live", "none"] else int(self._to_seconds(dur))
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
            
            sess = await _ensure_aio_session()
            async with sess.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    async with aiofiles.open(path, "wb") as f:
                        await f.write(data)
                    return path
        except Exception as e:
            log.warning(f"Failed to download thumbnail: {e}")
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except Exception:
            return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        vid = _normalize_link(link, videoid)
        api_data = await self._api_call(f"/api/v1/videos/{vid}")
        
        out = []
        if api_data:
            streams = api_data.get("formatStreams", []) + api_data.get("adaptiveFormats", [])
            for stream in streams:
                out.append({
                    "format": stream.get("itag"),
                    "filesize": stream.get("clen"),
                    "format_id": stream.get("itag"),
                    "ext": stream.get("container") or stream.get("type", "").split(";")[0].split("/")[-1],
                    "format_note": stream.get("qualityLabel") or stream.get("audioQuality", ""),
                })
        return out, f"https://youtube.com/watch?v={vid}"

    # 🚀 استخراج الرابط المباشر من Invidious
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        vid = _normalize_link(link)
        if not vid or len(vid) != 11: return None

        key = f"{vid}_{prefer_audio}"
        now = int(time.time())
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now:
                return cached[1]

        api_data = await self._api_call(f"/api/v1/videos/{vid}")
        if not api_data: return None

        direct_url = None

        if prefer_audio:
            # البحث عن صيغ الصوت فقط (m4a عادةً مدعوم بشكل أفضل)
            audios = [fmt for fmt in api_data.get("adaptiveFormats", []) if "audio" in fmt.get("type", "")]
            if audios:
                # محاولة الحصول على m4a أولاً، ثم أي شيء آخر
                m4a_audios = [a for a in audios if "mp4a" in a.get("type", "")]
                best_audio = m4a_audios[0] if m4a_audios else audios[0]
                direct_url = best_audio.get("url")
        else:
            # البحث عن فيديو مع صوت مدمج
            videos = api_data.get("formatStreams", [])
            if videos:
                direct_url = videos[-1].get("url") # عادةً تكون الجودة 720p هنا

        if direct_url:
            async with _direct_cache_lock:
                _direct_cache[key] = (now + 18000, direct_url) # كاش لمدة 5 ساعات
            return direct_url

        return None

    # 🚀 تشغيل/تحميل مباشر وبدون yt-dlp
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
        
        is_video = bool(video or songvideo)
        
        # بما أن Invidious يوفر روابط مباشرة (Direct googlevideo URLs)،
        # يمكننا إرجاعها مباشرة لـ pytgcalls بدون الحاجة للتحميل المحلي.
        # هذا سيوفر مساحة الرام والديسك لديك بشكل هائل ويقلل وقت التشغيل!
        
        direct = await self.get_direct_link(link, prefer_audio=not is_video)
        if direct:
            return direct, True # True تعني أن هذا رابط مباشر للتشغيل، وليس ملف محلي

        return None, False

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: plid = videoid
        else:
            try: plid = parse_qs(urlparse(link).query).get("list", [None])[0]
            except Exception: plid = link

        if not plid: return []

        data = await self._api_call(f"/api/v1/playlists/{plid}", params={"page": 1})
        result = []
        if data and "videos" in data:
            for vid in data["videos"][:limit]:
                result.append(vid.get("videoId"))
        return result

# exported instance
YouTube = YouTubeAPI()
