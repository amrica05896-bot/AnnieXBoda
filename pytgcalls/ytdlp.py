# Authored By Certified Coders © 2026
# RACE MODE: Android/iOS Spoofing + Cookies Auth + IPv4 Force
# FIXED: Removed deprecated arguments (no-call-home) & Added Auto-Cookies

import asyncio
import logging
import re
import shlex
import os  # مهم جداً عشان البحث عن ملف الكوكيز
from typing import Optional
from typing import Tuple

from .exceptions import YtDlpError
from .ffmpeg import cleanup_commands
from .list_to_cmd import list_to_cmd
from .types.raw import VideoParameters

py_logger = logging.getLogger('pytgcalls')


class YtDlp:
    YOUTUBE_REGX = re.compile(
        r'^((?:https?:)?//)?((?:www|m)\.)?'
        r'(youtube(-nocookie)?\.com|youtu.be)'
        r'(/(?:[\w\-]+\?v=|embed/|live/|v/)?)'
        r'([\w\-]+)(\S+)?$',
    )

    @staticmethod
    def is_valid(link: str) -> bool:
        return bool(YtDlp.YOUTUBE_REGX.match(link))

    @staticmethod
    async def extract(
        link: Optional[str],
        video_parameters: VideoParameters,
        add_commands: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        if link is None:
            return None, None

        # 🔥 RACE MODE: NUCLEAR CONFIGURATION (16-Core Optimized) 🔥
        commands = [
            'yt-dlp',
            '-g',
            # استخدام أندرويد و iOS لأن استجابتهم أسرع (JSON أصغر)
            '--extractor-args', 'youtube:player_client=android,ios,web',
            
            # تحديد الصيغ (صوت فقط للسرعة، أو فيديو خفيف)
            '--format', 'bestaudio/best',
            
            # --- تحسينات الشبكة (Network Boost) ---
            '--force-ipv4',               # يمنع تأخير DNS في IPv6
            '--no-check-certificate',     # تجاوز SSL Handshake
            '--socket-timeout', '10',     # لو السيرفر ماردش في 10 ثواني اقطع
            
            # --- تخطي الفحوصات (Skip Checks) ---
            '--no-playlist',              
            '--no-check-formats',         # سرعة صاروخية (يأخذ أول صيغة تقابله)
            '--no-write-subs',
            '--no-warnings',
            '--ignore-errors',
            '--no-cache-dir',             # عدم القراءة/الكتابة على الهارد
            
            # ❌ (تم الحذف) الأوامر التي تسبب الكراش في النسخ الحديثة:
            # --no-call-home  <-- كان السبب في المشكلة
            # --no-remote-subtitles
        ]

        # ✅ إضافة الكوكيز تلقائياً (Auto-Detect Cookies)
        # يبحث عن الملف في المسارات المحتملة ويستخدمه إذا وجد
        possible_cookies = [
            '/app/cookies.txt',           # مسار الدوكر الرسمي
            'cookies.txt',                # المسار الحالي
            'AnnieXMedia/cookies.txt',    # مسار داخل السورس
            'assets/cookies.txt'
        ]

        for path in possible_cookies:
            if os.path.exists(path):
                commands.extend(['--cookies', path])
                # py_logger.debug(f"🍪 Using cookies from: {path}") 
                break

        if add_commands:
            commands += shlex.split(add_commands)

        commands.append(link)

        py_logger.log(
            logging.DEBUG,
            f'Running with "{list_to_cmd(commands)}" command',
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *commands,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                # المهلة الزمنية للسباق (Race Timeout)
                # رفعناها لـ 15 ثانية لتغطية وقت قراءة الكوكيز وفك التشفير
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=15, 
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill() # Kill أسرع من Terminate
                except:
                    pass
                raise YtDlpError('yt-dlp process timeout (Race Lost or Slow Proxy)')
            
            if not stdout and stderr:
                err_msg = stderr.decode()
                # لو الخطأ بسبب الحظر (رغم وجود الكوكيز أحياناً)، نوضحه
                if "Sign in" in err_msg:
                    raise YtDlpError("YouTube Blocked: Check cookies.txt validation.")
                
                # أحياناً yt-dlp يرمي تحذيرات في stderr بس بيجيب الرابط في stdout
                if not stdout:
                    raise YtDlpError(err_msg)
            
            data = stdout.decode().strip().split('\n')
            if data:
                # العودة بالرابط المباشر
                return data[0], data[1] if len(data) >= 2 else data[0]
            raise YtDlpError('No video URLs found')
        except FileNotFoundError:
            raise YtDlpError('yt-dlp is not installed on your system')
