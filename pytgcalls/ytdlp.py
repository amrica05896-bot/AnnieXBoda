# Authored By Certified Coders © 2026
# RACE MODE: Android/iOS/Web Spoofing + Auto Cookies + IPv4 Force
# STABLE MODE: pytgcalls-safe formats only (NO image-only / NO broken audio)

import asyncio
import logging
import re
import shlex
import os
from typing import Optional, Tuple

from .exceptions import YtDlpError
from .list_to_cmd import list_to_cmd
from .types.raw import VideoParameters

py_logger = logging.getLogger("pytgcalls")


class YtDlp:
    YOUTUBE_REGX = re.compile(
        r'^((?:https?:)?//)?((?:www|m)\.)?'
        r'(youtube(-nocookie)?\.com|youtu.be)'
        r'(/(?:[\w\-]+\?v=|embed/|live/|v/)?)'
        r'([\w\-]+)(\S+)?$',
    )

    @staticmethod
    def is_valid(link: str) -> bool:
        return bool(link and YtDlp.YOUTUBE_REGX.match(link))

    @staticmethod
    async def extract(
        link: Optional[str],
        video_parameters: VideoParameters,
        add_commands: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:

        if not link:
            return None, None

        # 🎯 pytgcalls SAFE FORMAT (FAST + STABLE)
        # - mp4 only
        # - real video (not image)
        # - fallback guaranteed
        ytdlp_format = (
            "bv*[ext=mp4][height<=720]+ba[ext=m4a]/"
            "bv*[ext=mp4][height<=360]+ba[ext=m4a]/"
            "b[ext=mp4]/best"
        )

        commands = [
            "yt-dlp",
            "-g",

            "--extractor-args",
            "youtube:player_client=android,ios,web",

            "--format",
            ytdlp_format,

            # ⚡ Network speed
            "--force-ipv4",
            "--socket-timeout", "10",

            # 🧹 Clean & fast
            "--no-playlist",
            "--no-write-subs",
            "--no-warnings",
            "--ignore-errors",
            "--no-cache-dir",
        ]

        # 🍪 Auto Cookies (Safe)
        possible_cookies = (
            "/app/cookies.txt",
            "cookies.txt",
            "AnnieXMedia/cookies.txt",
            "assets/cookies.txt",
        )

        for cookie_path in possible_cookies:
            if os.path.isfile(cookie_path):
                commands.extend(["--cookies", cookie_path])
                break

        if add_commands:
            commands.extend(shlex.split(add_commands))

        commands.append(link)

        py_logger.debug(f"yt-dlp cmd → {list_to_cmd(commands)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *commands,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=15,
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise YtDlpError("yt-dlp timeout (slow response or blocked)")

            if not stdout:
                error = stderr.decode(errors="ignore")
                if "Sign in" in error:
                    raise YtDlpError("YouTube blocked – cookies invalid or expired")
                raise YtDlpError(error or "yt-dlp returned empty output")

            lines = stdout.decode(errors="ignore").strip().splitlines()

            # yt-dlp -g ممكن يرجّع 1 أو 2 URL
            if len(lines) == 1:
                return lines[0], lines[0]
            elif len(lines) >= 2:
                return lines[0], lines[1]

            raise YtDlpError("No playable streams found")

        except FileNotFoundError:
            raise YtDlpError("yt-dlp binary not found")
