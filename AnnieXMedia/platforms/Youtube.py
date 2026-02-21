import asyncio
import os
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp

try:
    import orjson as _orjson  
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    import json as _json
    def _loads_bytes(b: bytes):
        return _json.loads(b.decode("utf-8", "ignore"))

PROBE_TIMEOUT = 1.2
AIO_CONN_LIMIT = 256
META_CACHE_TTL = 3600

API_BASE_URL = os.environ.get("TITAN_API_URL", "https://api-rskcpw.fly.dev")
API_WS_URL = os.environ.get("TITAN_WS_URL", "wss://api-rskcpw.fly.dev/api/v1/ws/stream")
API_KEY = os.environ.get("TITAN_SECRET_KEY", "Titan_2026_Ultra_Fast")
API_HEADER = "X-Titan-Key"

_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid:
        return "https://www.youtube.com/watch?v=" + str(videoid)
    if not link:
        return ""
    link = link.strip()
    return link.split("&")[0]

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://www.youtube.com/playlist?list="
        self._ws = None
        self._ws_lock = asyncio.Lock()

    async def _get_ws_link(self, url: str, prefer_audio: bool = True) -> Optional[str]:
        try:
            async with self._ws_lock:
                sess = await _ensure_aio_session()
                if not self._ws or self._ws.closed:
                    self._ws = await sess.ws_connect(API_WS_URL, timeout=5)
                    await self._ws.send_json({"auth": API_KEY})
            await self._ws.send_json({"url": url, "audio_only": prefer_audio})
            msg = await self._ws.receive_json(timeout=8)
            if msg and msg.get("success"):
                return msg.get("direct_stream_url")
        except Exception:
            self._ws = None
        return None

    async def _fetch_from_rest(self, url: str, prefer_audio: bool = True) -> Optional[Dict[str, Any]]:
        try:
            sess = await _ensure_aio_session()
            api_url = f"{API_BASE_URL}/api/v1/extract?url={urllib.parse.quote(url)}&audio_only={str(prefer_audio).lower()}"
            headers = {API_HEADER: API_KEY, "Accept": "application/json"}
            async with sess.get(api_url, headers=headers, timeout=12) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and data.get("success"):
                        return data
        except Exception:
            pass
        return None

    async def url(self, message) -> Optional[str]:
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

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        api_data = await self._fetch_from_rest(f"ytsearch{limit}:{query}", prefer_audio=True)
        if api_data:
            dur_sec = api_data.get("duration", 0)
            dur_str = "Live" if api_data.get("is_live") else f"{dur_sec // 60}:{dur_sec % 60:02d}"
            return [{
                "title": api_data.get("title", "Unknown"),
                "vidid": api_data.get("video_id", ""),
                "duration": dur_str
            }]
        return []

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
                
        api_data = await self._fetch_from_rest(prepared, prefer_audio=True)
        if api_data:
            vid_id = api_data.get("video_id", "")
            dur_sec = api_data.get("duration", 0)
            dur = "Live" if api_data.get("is_live") else f"{dur_sec // 60}:{dur_sec % 60:02d}"
            
            thumb_url = ""
            thumbnails = api_data.get("thumbnails", [])
            if thumbnails and isinstance(thumbnails, list):
                thumb_url = thumbnails[-1].get("url", "")
                
            details = {
                "title": api_data.get("title", "Unknown"),
                "link": prepared,
                "vidid": vid_id,
                "duration_min": dur,
                "thumb": thumb_url,
            }
            async with _meta_cache_lock:
                _meta_cache[key] = (now, details, vid_id)
            return details, vid_id

        return {"title": "Unknown", "link": prepared, "vidid": "", "duration_min": None, "thumb": ""}, ""

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        if vid == "":
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

    async def slider(self, query: str, query_type: int):
        results = await self.search(query, limit=1)
        if not results:
            raise ValueError("No results found")
        item = results[0]
        thumb = f"https://i.ytimg.com/vi/{item['vidid']}/hqdefault.jpg"
        return item["title"], item["duration"], thumb, item["vidid"]

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            base_dir = "downloads"
            os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            session = await _ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception:
            pass
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts:
                s = s * 60 + p
            return s
        except Exception:
            try:
                return int(float(t))
            except Exception:
                return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        prepared = _normalize_link(link, videoid)
        api_data = await self._fetch_from_rest(prepared, prefer_audio=False)
        out: List[Dict[str, Any]] = []
        if api_data and api_data.get("smart_formats"):
            sf = api_data["smart_formats"]
            all_f = sf.get("best_muxed", []) + sf.get("audio_only", []) + sf.get("video_only", [])
            for fmt in all_f:
                try:
                    out.append({
                        "format": fmt.get("format_id"),
                        "filesize": None, 
                        "format_id": fmt.get("format_id"),
                        "ext": fmt.get("ext"),
                        "format_note": fmt.get("resolution", ""),
                    })
                except Exception:
                    continue
        return out, prepared

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None

        ws_url = await self._get_ws_link(prepared, prefer_audio)
        if ws_url: return ws_url

        api_data = await self._fetch_from_rest(prepared, prefer_audio)
        if api_data:
            return api_data.get("direct_stream_url")
            
        return None

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
        prepared = _normalize_link(link, videoid)

        direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
        if direct:
            return direct, True
            
        return None, False

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        return []

YouTube = YouTubeAPI()
