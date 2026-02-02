# Authored By Certified Coders © 2026
# RACE MODE: Android Client Spoofing + No-Check Flags + Zero Latency Extraction
import asyncio
import logging
import re
import shlex
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

        # 🔥 RACE MODE: NUCLEAR CONFIGURATION 🔥
        # تم تعديل الأعلام لجلب الرابط بأسرع طريقة برمجية ممكنة
        commands = [
            'yt-dlp',
            '-g',
            # استخدام أندرويد كلينت يوفر 0.4 ثانية لأن حجم الرد أصغر
            '--extractor-args', 'youtube:player_client=android,web',
            '--format', 'bestaudio/best', # البحث عن الصوت أولاً أسرع من دمج الفيديو
            '--no-playlist',              # منع الفحص الإضافي للقوائم
            '--no-check-formats',         # تخطي فحص الصيغ (توفير وقت ضخم)
            '--no-check-certificate',     # تخطي فحص الأمان لتسريع الـ Handshake
            '--no-warnings',
            '--ignore-errors',
            '--no-call-home',             # منع الاتصال بسيرفرات yt-dlp للتحديث
            '--no-cache-dir',             # عدم إضاعة الوقت في قراءة الكاش
        ]

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
                # في السباق.. لو مجاش في 10 ثواني يبقى خسرنا، ملوش لزمة الـ 60
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    10, 
                )
            except asyncio.TimeoutError:
                try:
                    proc.terminate()
                except:
                    pass
                raise YtDlpError('yt-dlp process timeout')
            
            if not stdout and stderr:
                raise YtDlpError(stderr.decode())
            
            data = stdout.decode().strip().split('\n')
            if data:
                # إرجاع الروابط فوراً
                return data[0], data[1] if len(data) >= 2 else data[0]
            raise YtDlpError('No video URLs found')
        except FileNotFoundError:
            raise YtDlpError('yt-dlp is not installed on your system')
