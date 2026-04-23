# file: AnnieXMedia/platforms/Youtube.py
import asyncio
import re
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import aiohttp
import aiofiles
from pyrogram import enums
from yt_dlp import YoutubeDL

# 🚀 استيراد مكتبة البحث الصاروخية
from youtubesearchpython.aio import VideosSearch

log = logging.getLogger("AnnieXMedia.YouTube")

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        
        # 🚀 إعدادات التشغيل المباشر الصاروخية (InnerTube API فقط)
        self.base_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": None,           # تجاهل الكوكيز للسرعة
            "force_ipv4": True,           # 🔴 حجب الـ IPv6 لمنع تهنيج سيرفر Fly.io
            "source_address": "0.0.0.0", 
            
            "js_runtimes": {"node": {}},  # 🟢 شغال للطوارئ لفك التشفير في كسر ثانية
            "remote_components": ["ejs:github"],
            
            "extractor_args": {
                "youtube": {
                    # 🎯 مسحنا web و mweb البطيئين، واعتمدنا وحوش الـ API المباشر
                    "player_client": ["android_vr", "android"] 
                }
            }
        }

    async def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

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
                    if ent.type == enums.MessageEntityType.URL:
                        return text[ent.offset : ent.offset + ent.length].split("&si")[0]
                    if ent.url:
                        return ent.url.split("&si")[0]
                except: continue
        return None

    # الدالة دي بتشتغل وقت التحميل وجلب الرابط المباشر
    async def _extract_native(self, query: str, opts: dict) -> dict:
        loop = asyncio.get_running_loop()
        def extract():
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(query, download=False)
        return await loop.run_in_executor(None, extract)

    # ==========================================
    # 🚀 دوال البحث السريعة باستخدام youtubesearchpython
    # ==========================================

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        
        query = f"https://youtube.com/watch?v={vid}" if vid else link

        try:
            # بحث فوري عن التفاصيل
            search = VideosSearch(query, limit=1)
            result = await search.next()
            
            if result and "result" in result and len(result["result"]) > 0:
                info = result["result"][0]
                v_id = info.get("id", vid)
                duration = info.get("duration", "0:00")
                
                # جلب أعلى جودة للغلاف
                thumb_url = ""
                if "thumbnails" in info and len(info["thumbnails"]) > 0:
                    thumb_url = info["thumbnails"][-1].get("url", "")
                    if "?" in thumb_url: thumb_url = thumb_url.split("?")[0] # تنظيف الرابط

                return {
                    "title": info.get("title", "Unknown"),
                    "link": f"https://www.youtube.com/watch?v={v_id}",
                    "vidid": v_id,
                    "duration_min": duration,
                    "thumb": thumb_url,
                }, v_id
            else:
                return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid
        except Exception as e:
            log.error(f"Track Search error: {e}")
            return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "0:00")
        
        # تحويل الدقائق لثواني للـ PyTgCalls
        try:
            parts = [int(p) for p in str(dur).split(":")]
            secs = sum(p * (60 ** i) for i, p in enumerate(reversed(parts)))
        except:
            secs = 0
            
        return data["title"], dur, secs, data["thumb"], str(vid)

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            # بحث فوري لإنشاء قائمة (ليست / كيبورد البحث)
            search = VideosSearch(query, limit=limit)
            result = await search.next()
            
            if not result or "result" not in result:
                return []
            
            results = []
            for d in result["result"]:
                results.append({
                    "title": d.get("title", "Unknown"), 
                    "vidid": d.get("id"), 
                    "duration": d.get("duration", "0:00")
                })
            return results
        except Exception as e:
            log.error(f"Search error: {e}")
            return []

    # ==========================================
    # 🛡️ دوال استخراج الرابط المباشر للتشغيل (InnerTube API)
    # ==========================================

    async def download(self, link: str, mystic: Any, video: Union[bool, str] = None, videoid: Union[bool, str] = None, **kwargs) -> Optional[str]:
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        
        target_url = f"https://www.youtube.com/watch?v={vid}" if vid else link
        
        # للتشغيل المباشر في الكول: نختار أسرع وأقل جودة (b) لضمان عدم التقطيع
        media_format = "b" if video else "ba/b"
        
        opts = self.base_opts.copy()
        opts["format"] = media_format
        opts["noplaylist"] = True
        
        try:
            info = await self._extract_native(target_url, opts)
            return info.get("url")
        except Exception as e:
            log.error(f"Extraction Error: {e}")
            return None

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        return await self.download(link, None, video=not prefer_audio)
                
    async def get_playlist(self, url: str) -> List[str]:
        opts = {
            "extract_flat": True,
            "quiet": True,
            "skip_download": True,
            "no_warnings": True
        }
        try:
            info = await self._extract_native(url, opts)
            return [f"https://www.youtube.com/watch?v={entry['id']}" for entry in info.get("entries", []) if entry.get("id")]
        except Exception as e:
            log.error(f"Playlist extraction error: {e}")
            return []

    async def download_thumb(self, thumbnail_url: str) -> Optional[str]:
        if not thumbnail_url: return None
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/thumb_{int(time.time())}.jpg"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(thumbnail_url) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(path, "wb") as f:
                            await f.write(await resp.read())
                        return path
        except: pass
        return None

    # ==========================================
    # 🔥 إضافة دالة البث المباشر (المفقودة سابقاً)
    # ==========================================
    async def video(self, link: str, is_live: bool = False) -> Tuple[int, str]:
        """دالة للتعامل مع طلبات البث المباشر (Live Streams) لتوافق ملفات التشغيل والتخطي"""
        try:
            # نجلب الرابط المباشر للبث
            url = await self.get_direct_link(link, prefer_audio=True)
            if url:
                return 1, url # نرجع 1 كعلامة للنجاح مع الرابط
            return 0, ""      # نرجع 0 كعلامة للفشل
        except Exception as e:
            log.error(f"Live Video extraction error: {e}")
            return 0, ""

YouTube = YouTubeAPI()
