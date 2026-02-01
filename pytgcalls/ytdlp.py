import asyncio
import logging
import re
import shlex
import os
from typing import Optional, Tuple

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

        # دمج إعدادات الجودة من الكود الأول مع تحسينات الشبكة من الكود الثاني
        commands = [
            'yt-dlp',
            '-g',
            
            # --- 1. إعدادات الجودة (من الكود الأول لضمان عمل الفيديو) ---
            # تم تعديل الصيغة لتشمل الصوت كبديل سريع
            '-f', 'bestvideo[vcodec~="(vp09|avc1)"]+m4a/bestaudio/best',
            '-S', f'res:{min(video_parameters.width, video_parameters.height)}',

            # --- 2. تحسينات السرعة (Race Mode - من الكود الثاني) ---
            # انتحال صفة أندرويد لتسريع الاستجابة وتخطي بعض القيود
            '--extractor-args', 'youtube:player_client=android,ios,web',
            '--force-ipv4',               # منع تأخير DNS IPv6
            '--no-check-certificate',     # تجاوز فحص الشهادات للسرعة
            '--socket-timeout', '10',     # مهلة قصيرة للاتصال بالسيرفر
            
            # --- 3. تخطي الفحوصات غير الضرورية ---
            '--no-playlist',
            '--no-check-formats',         # سرعة صاروخية (عدم فحص كل الصيغ)
            '--no-write-subs',
            '--no-warnings',
            '--ignore-errors',
            '--no-cache-dir',             # عدم الكتابة على الهارد
        ]

        # --- 4. البحث التلقائي عن الكوكيز (من الكود الثاني) ---
        possible_cookies = [
            '/app/cookies.txt',           # مسار السيرفرات
            'cookies.txt',                # المسار المحلي
            'AnnieXMedia/cookies.txt',    
            'assets/cookies.txt'
        ]

        for path in possible_cookies:
            if os.path.exists(path):
                commands.extend(['--cookies', path])
                # py_logger.debug(f"🍪 Using cookies from: {path}") 
                break

        # معالجة الأوامر الإضافية بأمان (من الكود الأول)
        if add_commands:
            commands += await cleanup_commands(
                shlex.split(add_commands),
                'yt-dlp',
                ['-f', '-g', '--no-warnings']
            )

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
                # استخدام مهلة 20 ثانية (حل وسط آمن)
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=20,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill() # استخدام Kill بدلاً من terminate للسرعة والقوة
                except:
                    pass
                raise YtDlpError('yt-dlp process timeout (Race Lost)')

            if stderr:
                err_msg = stderr.decode()
                # اكتشاف أخطاء الحظر وتسجيل الدخول (من الكود الثاني)
                if "Sign in" in err_msg:
                    raise YtDlpError("YouTube Blocked: Check cookies.txt validation.")
                
                # إذا لم يكن هناك مخرجات (رابط)، ارفع الخطأ
                if not stdout:
                    raise YtDlpError(err_msg)

            data = stdout.decode().strip().split('\n')
            if data:
                return data[0], data[1] if len(data) >= 2 else data[0]
            raise YtDlpError('No video URLs found')

        except FileNotFoundError:
            raise YtDlpError('yt-dlp is not installed on your system')
