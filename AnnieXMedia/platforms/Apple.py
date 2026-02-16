# Authored By Certified Coders © 2026
# System: Apple Music API
# Updated to use: pytubefix (for YouTube matching) & aiohttp (for scraping)

import re
import asyncio
from typing import List, Union, Optional

import aiohttp
from bs4 import BeautifulSoup
from youtubesearchpython.aio import VideosSearch

class AppleAPI:
    def __init__(self):
        self.regex = r"^https:\/\/music\.apple\.com\/.+"
        self.base = "https://music.apple.com/in/playlist/"

    async def valid(self, link: str) -> bool:
        return bool(re.search(self.regex, link or ""))

    async def track(self, url: str, playid: Union[bool, str] = None):
        if playid:
            url = self.base + url

        # 1. جلب بيانات الصفحة من Apple Music
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return False
                html = await response.text()

        soup = BeautifulSoup(html, "html.parser")
        title_query: Optional[str] = None
        
        # محاولة استخراج اسم الأغنية والفنان
        for tag in soup.find_all("meta"):
            if tag.get("property") == "og:title":
                title_query = tag.get("content")
                break

        if not title_query:
            return False

        # 2. البحث في يوتيوب باستخدام pytubefix (المكتبة المعتمدة)
        try:
            loop = asyncio.get_running_loop()
            
            def _search():
                s = Search(title_query)
                return s.videos[0] if s.videos else None
            
            video = await loop.run_in_executor(None, _search)
            
            if not video:
                return False

            track_details = {
                "title": video.title,
                "link": video.watch_url,
                "vidid": video.video_id,
                "duration_min": video.length, # pytubefix يعيدها ثواني، المنسق هيحولها
                "thumb": video.thumbnail_url,
            }
            return track_details, track_details["vidid"]
            
        except Exception:
            return False

    async def playlist(self, url: str, playid: Union[bool, str] = None):
        if playid:
            url = self.base + url

        try:
            playlist_id = url.split("playlist/")[1]
        except Exception:
            playlist_id = "Unknown"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return False
                html = await response.text()

        soup = BeautifulSoup(html, "html.parser")
        
        # البحث عن كل الأغاني داخل القائمة
        applelinks = soup.find_all("meta", attrs={"property": "music:song"})
        results: List[str] = []
        
        for item in applelinks:
            try:
                # استخراج اسم الأغنية من الرابط (Slug)
                # مثال: https://music.apple.com/us/album/song-name/123 -> song name
                slug = item["content"].split("album/")[1].split("/")[0]
                clean_name = slug.replace("-", " ")
                results.append(clean_name)
            except Exception:
                continue

        return results, playlist_id
