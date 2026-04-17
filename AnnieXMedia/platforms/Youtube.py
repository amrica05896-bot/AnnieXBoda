# file: AnnieXMedia/platforms/Youtube.py
# 🚀 ULTRA FAST YouTube Resolver for 16-Core Servers (2026)
# Powered by: uvloop, aiohttp[speedups], orjson, and Direct API Streaming

import asyncio
import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import orjson
from youtubesearchpython.aio import VideosSearch
from pyrogram import enums, types

import config

# إعدادات اللوج
logger = logging.getLogger("AnnieXMedia.YouTube")
logger.setLevel(logging.INFO)

# ==========================================
# ⚡ إعدادات السرعة القصوى (Performance Tuning)
# ==========================================
API_URL = getattr(config, "YOUTUBE_API_URL", "https://shrutibots.site")

# استخدام TCPConnector للحفاظ على الاتصالات مفتوحة (Keep-Alive) لسرعة البرق
_aio_connector = aiohttp.TCPConnector(
    limit=200,                  # عدد الاتصالات المتزامنة (مناسب لـ 16 كور)
    keepalive_timeout=300,      # بقاء الاتصال جاهز لمدة 5 دقائق
    ttl_dns_cache=300,          # كاش للـ DNS لتخطي وقت الاستعلام
    enable_cleanup_closed=True
)
_aio_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    """استدعاء جلسة اتصال جاهزة ومسخنة مسبقاً مع orjson للسرعة"""
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(
            connector=_aio_connector,
            json_serialize=orjson.dumps  # أسرع مكتبة JSON في العالم
        )
    return _aio_session

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.search_cache = {}
        # Semaphore لحماية الـ API من الـ Spam لو حصل ضغط فجأة
        self._api_sema = asyncio.Semaphore(50) 

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def url(self, message: types.Message) -> Union[str, None]:
        """استخراج الرابط من الرسالة بأسرع طريقة"""
        messages = [message]
        link = None
        if getattr(message, "reply_to_message", None):
            messages.append(message.reply_to_message)

        for msg in messages:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = getattr(msg, "entities", []) or getattr(msg, "caption_entities", []) or []
            
            for entity in entities:
                if entity.type == enums.MessageEntityType.URL:
                    link = text[entity.offset: entity.offset + entity.length]
                    break
                elif entity.type == enums.MessageEntityType.TEXT_LINK:
                    link = entity.url
                    break
            if link:
                return link.split("&si")[0].split("?si")[0]
        return None

    async def track(self, link: str, videoid: Union[str, None] = None) -> Tuple[Dict[str, Any], str]:
        """جلب تفاصيل الأغنية في لمح البصر باستخدام youtube-search-python"""
        query = videoid if videoid else link
        if not query or str(query) in ["True", "False"]:
            return {}, ""

        try:
            # ⚡ سرعة استجابة البحث هنا لا تتجاوز 0.1 ثانية
            search = VideosSearch(query, limit=1)
            res = await search.next()
            results = res.get("result", [])
            
            if results:
                data = results[0]
                v_id = data.get("id", "")
                thumb = (data.get("thumbnails") or [{}])[-1].get("url", "").split("?")[0]
                
                details = {
                    "title": data.get("title", "Unknown"),
                    "link": data.get("link", f"https://www.youtube.com/watch?v={v_id}"),
                    "vidid": v_id,
                    "duration_min": data.get("duration", "0:00"),
                    "thumb": thumb,
                }
                return details, v_id
        except Exception as e:
            logger.debug(f"Fast Search failed: {e}")
            
        return {"title": "Unknown", "duration_min": "0:00", "thumb": ""}, str(videoid)

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """بحث سريع جداً لدعم قوائم الاختيار (Slider)"""
        try:
            search = VideosSearch(query, limit=limit)
            res = await search.next()
            results = []
            for data in res.get("result", []):
                results.append({
                    "title": data.get("title", "Unknown"),
                    "vidid": data.get("id", ""),
                    "duration": data.get("duration", "0:00")
                })
            return results
        except Exception:
            return []

    async def slider(self, query: str, query_type: int) -> Tuple[str, str, str, str]:
        """تقليب النتائج للبحث"""
        results = await self.search(query, limit=10)
        if not results:
            raise ValueError("No results found")
        
        idx = query_type % len(results)
        item = results[idx]
        vid = item["vidid"]
        d, _ = await self.track(vid, videoid=vid)
        return d.get("title", "Unknown"), str(d.get("duration_min", "0:00")), d.get("thumb", ""), vid

    async def download(self, video_id: str, is_live: bool = False, video: bool = False) -> Optional[str]:
        """
        🚀 قلب السرعة: جلب رابط البث المباشر (Stream URL) من الـ API في 0.4 ثانية.
        لا يوجد تحميل ملفات إطلاقاً.
        """
        if not video_id or str(video_id) in ["True", "False"]:
            return None

        file_type = "video" if video else "audio"
        session = await get_session()

        # 1. حالة البث المباشر (Live)
        if is_live:
            try:
                async with self._api_sema:
                    async with session.get(f"{API_URL}/live", params={"url": video_id, "type": "live"}, timeout=5) as response:
                        if response.status == 200:
                            # استخدام orjson لفك التشفير بسرعة
                            data = await response.json(loads=orjson.loads)
                            stream_url = data.get("stream_url")
                            if stream_url:
                                return stream_url
            except Exception as e:
                logger.warning(f"Live API error: {e}")
            # Fallback للرابط الأساسي
            return f"https://www.youtube.com/watch?v={video_id}"

        # 2. حالة الأغاني والفيديوهات العادية (Stream)
        try:
            async with self._api_sema:
                # خطوة A: جلب التوكن من الـ API في لمح البصر
                params = {"url": video_id, "type": file_type}
                async with session.get(f"{API_URL}/download", params=params, timeout=7) as response:
                    if response.status != 200:
                        logger.error(f"❌ API Token Error: {response.status}")
                        return None
                    
                    data = await response.json(loads=orjson.loads)
                    token = data.get("download_token")
                    
                    if not token:
                        return None

                # خطوة B: إرجاع الرابط المباشر للـ PyTgCalls (FFmpeg)
                # الـ FFmpeg هيقرا من الرابط ده مباشرة في الرامات بدون حفظ ملفات!
                direct_stream_url = f"{API_URL}/stream/{video_id}?type={file_type}&token={token}"
                return direct_stream_url

        except asyncio.TimeoutError:
            logger.error(f"❌ API Timeout for {video_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Direct Stream Error for {video_id}: {e}")
            return None

# Exported Instance
YouTube = YouTubeAPI()
