# file: AnnieXMedia/platforms/Youtube.py
# Optimized for Abdullah's 10-Core Server (Native Subprocess + Android Client)

import asyncio
import re
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import aiohttp
import aiofiles
from pyrogram import enums
from youtubesearchpython.aio import VideosSearch
import time

log = logging.getLogger("AnnieXMedia.YouTube")
COOKIES_PATH = "AnnieXMedia/assets/cookies.txt"

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self._api_sema = None

    async def get_sema(self) -> asyncio.Semaphore:
        if self._api_sema is None:
            self._api_sema = asyncio.Semaphore(15)
        return self._api_sema

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

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            try: vid = link.split("v=")[1].split("&")[0]
            except: pass
        query = vid if vid else link
        try:
            res = await VideosSearch(query, limit=1).next()
            results = res.get("result", [])
            if results:
                data = results[0]
                v_id = data.get("id", vid)
                thumb = (data.get("thumbnails") or [{}])[-1].get("url", "").split("?")[0]
                return {
                    "title": data.get("title", "Unknown"),
                    "link": f"https://www.youtube.com/watch?v={v_id}",
                    "vidid": v_id,
                    "duration_min": data.get("duration", "0:00"),
                    "thumb": thumb,
                }, v_id
        except Exception as e: log.debug(f"Search error: {e}")
        return {"title": "Unknown", "duration_min": "0:00", "thumb": "", "vidid": vid, "link": link}, vid

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "0:00")
        parts = [int(p) for p in str(dur).split(":")]
        secs = 0
        for p in parts: secs = secs * 60 + p
        return data["title"], dur, secs, data["thumb"], str(vid)

    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        **kwargs
    ) -> Optional[str]:
        """محرك الاستخراج الصاروخي (Android Client + Subprocess)"""
        vid = str(videoid) if videoid and str(videoid) not in ["True", "False"] else ""
        if not vid and "v=" in link:
            vid = link.split("v=")[1].split("&")[0]
        
        target_url = f"https://www.youtube.com/watch?v={vid}" if vid else link
        # ضفنا صيغة 18 كبديل سريع لو 140 مش موجودة (زي ما حصل في VEVO)
        media_format = "best[ext=mp4]/best" if video else "140/18/bestaudio[ext=m4a]/bestaudio/best"
        
        args = [
            "yt-dlp",
            "--force-ipv4",
            "--extractor-args", "youtube:player_client=android,web", # أندرويد للسرعة، ويب احتياطي للحظر
            "--quiet", "--no-warnings", "--no-playlist",
            "-f", media_format,
            "-g", target_url
        ]

        if os.path.isfile(COOKIES_PATH):
            args.insert(2, "--cookies")
            args.insert(3, COOKIES_PATH)

        sema = await self.get_sema()
        try:
            async with sema:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20.0)
                
                if process.returncode == 0:
                    direct_url = stdout.decode().strip()
                    if direct_url: return direct_url
                else:
                    log.error(f"yt-dlp Error: {stderr.decode().strip()}")
        except asyncio.TimeoutError:
            log.error(f"yt-dlp Timeout for {target_url}")
            try: process.kill() 
            except: pass
        except Exception as e:
            log.error(f"Internal Engine Failure: {e}")
        return None

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        return await self.download(link, None, video=not prefer_audio)

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            res = await VideosSearch(query, limit=limit).next()
            return [{"title": d["title"], "vidid": d["id"], "duration": d["duration"]} for d in res.get("result", [])]
        except: return []

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
