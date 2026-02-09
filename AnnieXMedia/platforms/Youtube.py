# Authored By Certified Coders © 2026
# System: Ultimate YouTube Resolver (Full Feature Set)
# Included: Slider, Formats, Playlist, Tracking, Downloading, and Direct Links

import asyncio
import os
import re
import json
import logging
from typing import Union, Tuple, Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor

from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch
from yt_dlp import YoutubeDL

# Logging
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("AnnieXMedia.YouTube")

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # Smart Cookie Finder
        self.cookie_paths = [
            "cookies.txt",
            "AnnieXMedia/cookies.txt",
            "assets/cookies.txt",
            "/app/cookies.txt"
        ]

    def cookiefile(self) -> Optional[str]:
        for path in self.cookie_paths:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return path
        return None

    async def shell_cmd(self, cmd: str) -> str:
        """Runs shell commands asynchronously"""
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if stdout:
            return stdout.decode().strip()
        if stderr:
            err = stderr.decode()
            if "unavailable videos are hidden" in err.lower():
                return stdout.decode().strip() if stdout else ""
            LOG.debug(f"Shell Error: {err}")
        return ""

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message) -> Union[str, None]:
        """Extracts URL from message securely"""
        messages = [message]
        if message.reply_to_message:
            messages.append(message.reply_to_message)
        
        for msg in messages:
            if not msg: continue
            text = msg.text or msg.caption or ""
            
            # 1. Entities Check
            if msg.entities:
                for entity in msg.entities:
                    if entity.type == MessageEntityType.URL:
                        return text[entity.offset : entity.offset + entity.length]
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
            if msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
            
            # 2. Regex Fallback
            match = re.search(r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https?://youtu\.be/[\w-]+)', text)
            if match: return match.group(0)
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        try:
            results = VideosSearch(link, limit=1)
            res = (await results.next())["result"][0]
            
            title = res["title"]
            duration_min = res["duration"]
            thumbnail = res["thumbnails"][0]["url"].split("?")[0]
            vidid = res["id"]
            
            # Convert Duration to Seconds
            if str(duration_min) == "None": duration_sec = 0
            else:
                try:
                    parts = duration_min.split(":")
                    if len(parts) == 3: duration_sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                    elif len(parts) == 2: duration_sec = int(parts[0])*60 + int(parts[1])
                    else: duration_sec = 0
                except: duration_sec = 0
                
            return title, duration_min, duration_sec, thumbnail, vidid
        except:
            return "Unknown", "00:00", 0, "", ""

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        d = await self.details(link, videoid)
        return d[0]

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> str:
        d = await self.details(link, videoid)
        return d[1]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        d = await self.details(link, videoid)
        return d[3]

    async def video(self, link: str, videoid: Union[bool, str] = None) -> Tuple[int, str]:
        """Get Direct Stream Link"""
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        cookie = self.cookiefile()
        cmd = f"yt-dlp {'--cookies ' + cookie if cookie else ''} -g -f 'best[height<=?720][width<=?1280]' --force-ipv4 --geo-bypass '{link}'"
        
        url = await self.shell_cmd(cmd)
        if url: return 1, url
        return 0, "Failed to get video link"

    async def playlist(self, link: str, limit: int, user_id: int, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]

        cookie = self.cookiefile()
        cookie_cmd = f"--cookies {cookie}" if cookie else ""
        
        cmd = (
            f"yt-dlp {cookie_cmd} -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null"
        )
        
        output = await self.shell_cmd(cmd)
        return [vid for vid in output.split("\n") if vid]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        """Metadata Fetcher compatible with Annie's Call Controller"""
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            search = VideosSearch(link, limit=1)
            result = (await search.next())["result"][0]
            
            track_details = {
                "title": result["title"],
                "link": result["link"],
                "vidid": result["id"],
                "duration_min": result["duration"],
                "thumb": result["thumbnails"][0]["url"].split("?")[0],
                "cookiefile": self.cookiefile(),
            }
            return track_details, result["id"]
        except Exception as e:
            LOG.error(f"Track Fetch Error: {e}")
            return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        """Get available formats (Debugging/Quality Selection)"""
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        cookie = self.cookiefile()
        opts = {"quiet": True, "cookiefile": cookie, "no_warnings": True}
        
        def _get_fmt():
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(link, download=False)
        
        try:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(self.executor, _get_fmt)
            formats_available = []
            for fmt in info.get("formats", []):
                formats_available.append({
                    "format": fmt.get("format"),
                    "filesize": fmt.get("filesize"),
                    "format_id": fmt.get("format_id"),
                    "ext": fmt.get("ext"),
                    "note": fmt.get("format_note"),
                })
            return formats_available, link
        except:
            return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        """For search results slider/pagination"""
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            search = VideosSearch(link, limit=10)
            res = (await search.next())["result"]
            if query_type >= len(res): return None
            
            item = res[query_type]
            return item["title"], item["duration"], item["thumbnails"][0]["url"].split("?")[0], item["id"]
        except:
            return None

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        """
        Comprehensive Downloader Handling all Alexa/Annie cases
        """
        if videoid: link = self.base + link
        
        loop = asyncio.get_running_loop()
        cookie = self.cookiefile()
        base_dir = "downloads"
        if not os.path.exists(base_dir): os.makedirs(base_dir)

        # Common Options
        opts = {
            "cookiefile": cookie,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "concurrent_fragment_downloads": 5,
        }

        # 1. Song Video (Specific Format Download)
        if songvideo:
            fpath = f"{base_dir}/{title}.mp4"
            opts.update({
                "format": f"{format_id}+140",
                "outtmpl": fpath,
                "merge_output_format": "mp4"
            })
            if os.path.exists(fpath): return fpath, False
            await loop.run_in_executor(self.executor, lambda: YoutubeDL(opts).download([link]))
            return fpath, False

        # 2. Song Audio (Specific Format + Conversion)
        elif songaudio:
            fpath = f"{base_dir}/{title}.mp3"
            opts.update({
                "format": format_id,
                "outtmpl": f"{base_dir}/{title}.%(ext)s",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            })
            if os.path.exists(fpath): return fpath, False
            await loop.run_in_executor(self.executor, lambda: YoutubeDL(opts).download([link]))
            return fpath, False

        # 3. Video Playback (Stream or Download)
        elif video:
            # Try getting direct link first (Fastest)
            try:
                status, direct_url = await self.video(link)
                if status == 1: return direct_url, True
            except: pass
            
            # Fallback to download
            opts.update({
                "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]",
                "outtmpl": f"{base_dir}/%(id)s.%(ext)s"
            })
            def _dl():
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    return ydl.prepare_filename(info)
            
            fpath = await loop.run_in_executor(self.executor, _dl)
            return fpath, False

        # 4. Audio Playback (Stream or Download) - Default
        else:
            # Try Direct Link
            try:
                cmd = f"yt-dlp {'--cookies ' + cookie if cookie else ''} -g -f 'bestaudio[ext=m4a]/bestaudio/best' --force-ipv4 '{link}'"
                direct_url = await self.shell_cmd(cmd)
                if direct_url: return direct_url, True
            except: pass
            
            # Fallback Download
            opts.update({
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": f"{base_dir}/%(id)s.%(ext)s"
            })
            def _dl_audio():
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    fname = ydl.prepare_filename(info)
                    # Handle mp3 conversion manually if needed by call.py, but usually m4a is fine for ffmpeg
                    return fname
            
            fpath = await loop.run_in_executor(self.executor, _dl_audio)
            return fpath, False

    async def download_thumb(self, url: str) -> Optional[str]:
        """Helper to download thumbnails"""
        if not url: return None
        try:
            os.makedirs("downloads", exist_ok=True)
            path = f"downloads/thumb_{int(time.time())}.jpg"
            # Using simple curl for speed, or aiohttp if curl fails
            cmd = f"curl -o {path} {url}"
            await self.shell_cmd(cmd)
            if os.path.exists(path): return path
        except: pass
        return None

YouTube = YouTubeAPI()
