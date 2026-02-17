# Authored By Certified Coders © 2026
# System: SoundCloud API (Integrated with Youtube Core)

import asyncio
import re
from typing import Any, Dict, Tuple, Union

from yt_dlp import YoutubeDL

# نستدعي المحرك الرئيسي (YouTube) ليقوم بمهمة التحميل والكاش
from AnnieXMedia.platforms.Youtube import YouTube
from AnnieXMedia.utils.formatters import seconds_to_min


_SC_RE = re.compile(r"^https?://(soundcloud\.com|on\.soundcloud\.com)/.+", re.I)


class SoundAPI:
    def __init__(self):
        self.opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
        }

    async def valid(self, link: str) -> bool:
        return bool(link and _SC_RE.match(link))

    async def _extract_info(self, url: str) -> Dict[str, Any]:
        """استخراج البيانات فقط (اسم، صورة، مدة) بدون تحميل"""
        def _run(u: str):
            with YoutubeDL(self.opts) as ydl:
                return ydl.extract_info(u, download=False)

        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, _run, url)
            
            # معالجة الروابط المختصرة أو التوجيهات في ساوند كلاود
            _type = str(info.get("_type", ""))
            if _type in ("url", "url_transparent") and info.get("url"):
                info = await loop.run_in_executor(None, _run, info["url"])
            
            return info
        except Exception:
            return {}

    async def download(self, url: str) -> Union[Tuple[Dict[str, Any], str], bool]:
        """
        يقوم بجلب المعلومات، ثم يطلب من ملف Youtube.py تحميل الرابط
        """
        # 1. جلب المعلومات لعرضها في البوت
        info = await self._extract_info(url)
        if not info or info.get("_type") == "playlist":
            return False

        # 2. تجهيز البيانات
        title = (info.get("title") or "SoundCloud Track").strip()
        title = re.sub(r'[\\/*?:"<>|]', '', title) # تنظيف الاسم للملفات

        try:
            duration_sec = int(info.get("duration") or 0)
        except:
            duration_sec = 0

        uploader = info.get("uploader") or "SoundCloud"
        thumb = (
            info.get("thumbnail")
            or (info.get("thumbnails") or [{}])[0].get("url")
            or ""
        )
        track_id = info.get("id")

        # 3. التسليم للمحرك المركزي (Youtube.py) للتحميل
        # نمرر songaudio=True عشان ينزلها صوت (Best Audio)
        try:
            # mystic=None لأننا مش بنعدل رسالة هنا، بنرجع المسار بس
            out_path, _ = await YouTube.download(
                url,
                mystic=None,
                videoid=track_id, # نستخدم ID ساوند كلاود كمعرف للكاش
                songaudio=True,
                title=title,
                format_id="bestaudio/best" # نطلب أفضل جودة صوت متاحة
            )
        except Exception:
            return False

        if not out_path:
            return False

        details = {
            "title": title,
            "duration_sec": duration_sec,
            "duration_min": seconds_to_min(duration_sec),
            "uploader": uploader,
            "thumb": thumb,
            "filepath": out_path,
        }
        return details, out_path
