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

log = logging.getLogger("AnnieXMedia.YouTube")

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        
        # الإعدادات الصاروخية المتكاملة (IPv4 + Node + WebSockets Bypass)
        self.base_opts = {
            "quiet": True,
            "no_warnings": True,
            "source_address": "0.0.0.0", # إجبار IPv4 لإلغاء الـ 150 ثانية تأخير
            "js_runtimes": {"node": {}}, # تفعيل نود لفك التشفير
            "impersonate": "chrome", # انتحال المتصفح وفتح دعم الويب سوكت (curl_cffi)
            "extractor_args": {
                "youtube": {
                    "player_client": ["mweb"], # عميل الموبايل ويب الذهبي
                    "remote_components": ["ejs:github"]
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

    # دالة الاستخراج الأساسية (بتشتغل في الخلفية بدون ما توقف البوت)
    async def _extract_native(self, query: str, opts: dict) -> dict:
        loop = asyncio.get_running_loop()
        def extract():
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(query, download=False)
        return await loop.run_in_executor(None, extract)

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        
        # لو مش رابط يوتيوب، هنحوله لبحث سريع
        query = link if (link.startswith("http") or vid) else f"ytsearch1:{link}"
        
        opts = self.base_opts.copy()
        opts["extract_flat"] = "in_playlist" # عشان البلاي ليست
        
        try:
            info = await self._extract_native(query, opts)
            if "entries" in info: 
                info = info["entries"][0]
            
            v_id = info.get("id", vid)
            thumb = info.get("thumbnail", "")
            dur_seconds = info.get("duration", 0)
            duration = time.strftime('%M:%S', time.gmtime(dur_seconds)) if dur_seconds else "0:00"
            
            return {
                "title": info.get("title", "Unknown"),
                "link": f"https://www.youtube.com/watch?v={v_id}",
                "vidid": v_id,
                "duration_min": duration,
                "thumb": thumb,
            }, v_id
        except Exception as e:
            log.error(f"Search/Track error: {e}")
            return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "0:00")
        parts = [int(p) for p in str(dur).split(":")]
        secs = sum(p * (60 ** i) for i, p in enumerate(reversed(parts)))
        return data["title"], dur, secs, data["thumb"], str(vid)

    async def download(self, link: str, mystic: Any, video: Union[bool, str] = None, videoid: Union[bool, str] = None, **kwargs) -> Optional[str]:
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        
        target_url = f"https://www.youtube.com/watch?v={vid}" if vid else link
        media_format = "best[ext=mp4]/best" if video else "140/18/bestaudio[ext=m4a]/bestaudio/best"
        
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

    # مكتبة البحث الجديدة بالكامل مبنية على yt-dlp
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        opts = self.base_opts.copy()
        opts["extract_flat"] = True
        try:
            info = await self._extract_native(f"ytsearch{limit}:{query}", opts)
            results = info.get("entries", [])
            return [
                {
                    "title": d.get("title", "Unknown"), 
                    "vidid": d.get("id"), 
                    "duration": time.strftime('%M:%S', time.gmtime(d.get("duration", 0))) if d.get("duration") else "0:00"
                } 
                for d in results if d.get("id")
            ]
        except:
            return []
            
    # دالة البلاي ليست (هتسحب كل الروابط طلقة)
    async def get_playlist(self, url: str) -> List[str]:
        opts = self.base_opts.copy()
        opts["extract_flat"] = True
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

YouTube = YouTubeAPI()
