# Authored By Certified Systems Architect
# Dedicated Song Downloader (Download Only Engine)
# Features:
#   - Standard Mode: Video <= 480p | Audio = 128kbps
#   - High Quality Mode: Video = Max | Audio = 320kbps
# Notes:
#   - NO DIRECT STREAMING
#   - STRICT Audio / Video Separation
#   - Always returns FILE PATH

import asyncio
import os
import logging
import time
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.ERROR)
def LOGGER(name): return logging.getLogger(name)

class Config:
    if os.path.exists("/dev/shm"):
        DOWNLOAD_PATH = "/dev/shm/AnnieSongDownloads"
    else:
        DOWNLOAD_PATH = os.path.abspath("downloads_songs")

    COOKIE_PATH = "AnnieXMedia/assets/cookies.txt"
    MAX_WORKERS = 4


os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)


class SongDownloaderAPI:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        self.force_high_quality = False

    def enable_quality(self):
        self.force_high_quality = True

    def disable_quality(self):
        self.force_high_quality = False

    def get_cookie_file(self):
        paths = [
            Config.COOKIE_PATH, "cookies.txt", "AnnieXMedia/cookies.txt",
            "assets/cookies.txt", "platforms/cookies.txt", "/app/cookies.txt"
        ]
        for p in paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        return None

    # ==========================================================
    # MAIN DOWNLOAD FUNCTION (FILE ONLY)
    # ==========================================================
    async def download(self, link: str, is_video: bool = False):
        """
        Returns:
            (file_path, False)
        """

        loop = asyncio.get_running_loop()
        cookies = self.get_cookie_file()

        def _download():
            uid = str(int(time.time() * 1000))
            ext = "mp4" if is_video else "mp3"
            out_path = os.path.join(Config.DOWNLOAD_PATH, f"{uid}.{ext}")

            # =============================
            # FORMAT SELECTION
            # =============================
            if is_video:
                if self.force_high_quality:
                    ytdlp_format = "bestvideo+bestaudio/best"
                else:
                    ytdlp_format = (
                        "bestvideo[height<=480][ext=mp4]+bestaudio/best/"
                        "best[height<=480][ext=mp4]"
                    )
            else:
                ytdlp_format = "bestaudio/best"

            ydl_opts = {
                "format": ytdlp_format,
                "outtmpl": out_path,
                "quiet": True,
                "no_warnings": True,
                "geo_bypass": True,
                "force_ipv4": True,
                "noplaylist": True,
                "nocheckcertificate": True,
                "cookiefile": cookies,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"]
                        if self.force_high_quality else ["web"]
                    }
                },
            }

            # =============================
            # AUDIO POST PROCESSING
            # =============================
            if not is_video:
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320" if self.force_high_quality else "128",
                }]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])

            # =============================
            # FILE RESOLUTION CHECK
            # =============================
            if os.path.exists(out_path):
                return out_path

            base = out_path.rsplit(".", 1)[0]
            for e in (".mp3", ".m4a", ".mp4", ".webm", ".mkv"):
                if os.path.exists(base + e):
                    return base + e

            return None

        file_path = await loop.run_in_executor(self.pool, _download)

        if not file_path:
            raise Exception("DOWNLOAD_FAILED")

        return file_path, False


SongDownloader = SongDownloaderAPI()
