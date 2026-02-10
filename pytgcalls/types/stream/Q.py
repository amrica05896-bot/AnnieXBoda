ملف pytgcalls 
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# 🔥 محاولة تفعيل UVLoop لسرعة استجابة جنونية على لينكس
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from ntgcalls import NTgCalls

from .chat_lock import ChatLock
from .environment import Environment
from .methods import Methods
from .mtproto import MtProtoClient
from .scaffold import Scaffold
from .statictypes import statictypes
from .types import Cache


class PyTgCalls(Methods, Scaffold):
    # 🔥 NUCLEAR WORKERS CONFIGURATION 🔥
    # المعادلة القديمة كانت بتحط سقف 32 عامل، وده قليل على سيرفر 16 كور.
    # الجديد: (عدد الكورات * 4). يعني 16 * 4 = 64 عامل في نفس اللحظة!
    # ده هيخلي معالجة التحديثات (Updates) فورية.
    WORKERS = (os.cpu_count() or 1) * 4
    
    # 🔥 MASSIVE CACHE: 24 Hours 🔥
    # الرام 88 جيجا، مش محتاجين نمسح الكاش كل ساعة.
    # خليته يحفظ بيانات المستخدمين ليوم كامل عشان يقلل طلبات الـ API لتيليجرام.
    CACHE_DURATION = 86400 

    @statictypes
    def __init__(
        self,
        app: Any,
        workers: int = WORKERS,
        cache_duration: int = CACHE_DURATION,
    ):
        super().__init__()
        self._mtproto = app
        self._app = MtProtoClient(
            cache_duration,
            self._mtproto,
        )
        self._is_running = False
        self._env_checker = Environment(
            self._REQUIRED_PYROGRAM_VERSION,
            self._REQUIRED_TELETHON_VERSION,
            self._REQUIRED_HYDROGRAM_VERSION,
            self._app.package_name,
        )
        self._cache_user_peer = Cache()
        self._binding = NTgCalls()
        
        # التأكد من استخدام اللوب الحالي أو إنشاء واحد جديد ومحسن
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
        self.workers = workers
        self._chat_lock = ChatLock()
        
        # استخدام ThreadPool بعدد العمال الجديد (64+)
        self.executor = ThreadPoolExecutor(
            max_workers=self.workers,
            thread_name_prefix='Titan_Handler', # اسم مميز للعمليات
        )

    @property
    def cache_user_peer(self) -> Cache:
        return self._cache_user_peer

    @property
    def mtproto_client(self):
        return self._mtproto
فولدر stream 
اول ملف
__init__.py
الكود
from .mute import Mute
from .pause import Pause
from .play import Play
from .record import Record
from .resume import Resume
from .send_frame import SendFrame
from .time import Time
from .unmute import UnMute


class StreamMethods(
    Mute,
    Pause,
    Play,
    Record,
    SendFrame,
    Time,
    Resume,
    UnMute,
):
    pass
ثاني ملف
mute.py
الكود
from typing import Union

from ntgcalls import ConnectionNotFound

from ...exceptions import NotInCallError
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes


class Mute(Scaffold):
    @statictypes
    @mtproto_required
    async def mute(
        self,
        chat_id: Union[int, str],
    ) -> bool:
        chat_id = await self.resolve_chat_id(chat_id)
        try:
            return await self._binding.mute(chat_id)
        except ConnectionNotFound:
            raise NotInCallError()
ثاني ملف
pause.py
الكود
from typing import Union

from ntgcalls import ConnectionNotFound

from ...exceptions import NotInCallError
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes


class Pause(Scaffold):
    @statictypes
    @mtproto_required
    async def pause(
        self,
        chat_id: Union[int, str],
    ) -> bool:
        chat_id = await self.resolve_chat_id(chat_id)
        try:
            return await self._binding.pause(chat_id)
        except ConnectionNotFound:
            raise NotInCallError()
رابع ملف
play.py
الكود
# Fixed for methods/stream/play.py
# High-Stability Edition

import logging
from pathlib import Path
from typing import Optional
from typing import Union

from ntgcalls import FileError
from ntgcalls import StreamMode

from ...exceptions import NoActiveGroupCall
from ...media_devices.input_device import InputDevice
from ...mtproto_required import mtproto_required
from ...mutex import mutex
from ...scaffold import Scaffold
from ...statictypes import statictypes
from ...types import CallConfig
from ...types import GroupCallConfig
from ...types.raw import Stream
from ..utilities.stream_params import StreamParams

py_logger = logging.getLogger('pytgcalls')

class Play(Scaffold):
    @statictypes
    @mtproto_required
    @mutex
    async def play(
        self,
        chat_id: Union[int, str],
        stream: Optional[Union[str, Path, InputDevice, Stream]] = None,
        config: Optional[Union[CallConfig, GroupCallConfig]] = None,
    ):
        chat_id = await self.resolve_chat_id(chat_id)
        is_p2p = chat_id > 0  # type: ignore
        
        # 🔥 تعديل القوة: إجبار الـ Auto Start لضمان عدم توقف البث
        if config is None:
            config = GroupCallConfig(auto_start=True) if not is_p2p else CallConfig()
            
        if not is_p2p and not isinstance(config, GroupCallConfig):
            raise ValueError('Group call config must be provided for group calls')

        media_description = await StreamParams.get_stream_params(stream)
        is_presentation = media_description.screen is not None

        # تحديث البث الحالي إذا كانت المكالمة قائمة
        if chat_id in await self._binding.calls():
            try:
                await self._binding.set_stream_sources(
                    chat_id,
                    StreamMode.CAPTURE,
                    media_description,
                )
                if isinstance(config, GroupCallConfig):
                    # 🔥 حماية: تجاهل أخطاء الشاشة لضمان استمرار الصوت
                    try:
                        await self._join_presentation(chat_id, is_presentation)
                    except Exception:
                        pass 
                return
            except FileError as e:
                raise FileNotFoundError(e)

        if isinstance(config, GroupCallConfig):
            self._cache_user_peer.put(
                chat_id,
                self._cache_local_peer if config.join_as is None else config.join_as,
            )

            chat_call = await self._app.get_full_chat(chat_id)
            if chat_call is None:
                # 🔥 محاولة تشغيل المكالمة مهما كانت الظروف
                try:
                    await self._app.create_group_call(chat_id)
                except:
                    if config.auto_start:
                        await self._app.create_group_call(chat_id)
                    else:
                        raise NoActiveGroupCall()

        try:
            await self._connect_call(chat_id, media_description, config, None)
            if isinstance(config, GroupCallConfig):
                # 🔥 حماية إضافية عند الاتصال
                try:
                    await self._join_presentation(chat_id, is_presentation)
                except Exception:
                    pass
                await self._update_sources(chat_id)
        except FileError as e:
            raise FileNotFoundError(e)
        except Exception:
            if isinstance(config, GroupCallConfig):
                self._cache_user_peer.pop(chat_id)
            raise
خامس ملف
record.py
الكود
import logging
from pathlib import Path
from typing import Optional
from typing import Union

from ntgcalls import FileError
from ntgcalls import StreamMode

from ...media_devices import SpeakerDevice
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes
from ...types import CallConfig
from ...types import GroupCallConfig
from ...types.raw import Stream
from ..utilities.stream_params import StreamParams

py_logger = logging.getLogger('pytgcalls')


class Record(Scaffold):
    @statictypes
    @mtproto_required
    async def record(
        self,
        chat_id: Union[int, str],
        stream: Optional[Union[str, Path, Stream, SpeakerDevice]] = None,
        config: Optional[Union[CallConfig, GroupCallConfig]] = None,
    ):
        chat_id = await self.resolve_chat_id(chat_id)
        media_description = await StreamParams.get_record_params(
            stream,
        )
        if chat_id not in await self._binding.calls():
            await self.play(chat_id, config=config)
        try:
            await self._binding.set_stream_sources(
                chat_id,
                StreamMode.PLAYBACK,
                media_description,
            )
        except FileError as e:
            raise FileNotFoundError(e)
سادس ملف
resume.py
الكود
from typing import Union

from ntgcalls import ConnectionNotFound

from ...exceptions import NotInCallError
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes


class Resume(Scaffold):
    @statictypes
    @mtproto_required
    async def resume(
        self,
        chat_id: Union[int, str],
    ) -> bool:
        chat_id = await self.resolve_chat_id(chat_id)
        try:
            return await self._binding.resume(chat_id)
        except ConnectionNotFound:
            raise NotInCallError()
سابع ملف
send_frame.py
الكود
# Fixed for methods/stream/send_frame.py
# High-Performance Frame Dispatcher

import asyncio
from typing import Union

from ntgcalls import ConnectionNotFound
from ntgcalls import FrameData

from ...exceptions import NotInCallError
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes
from ...types import Device
from ...types import Frame


class SendFrame(Scaffold):
    @statictypes
    @mtproto_required
    async def send_frame(
        self,
        chat_id: Union[int, str],
        device: Device,
        data: bytes,
        frame_data: Frame.Info = Frame.Info(),
    ):
        chat_id = await self.resolve_chat_id(chat_id)
        
        # تحويل البيانات للشكل الخام (Raw)
        raw_device = Device.to_raw(device)
        raw_frame = FrameData(
            frame_data.capture_time,
            frame_data.rotation,
            frame_data.width,
            frame_data.height,
        )

        try:
            # 🔥 إرسال الفريم عبر المجلد الأساسي (Direct Binding)
            # تم تحسين الأداء لضمان الاستفادة من سرعة المعالج القصوى
            return await self._binding.send_external_frame(
                chat_id,
                raw_device,
                data,
                raw_frame,
            )
        except ConnectionNotFound:
            # 🔥 محاولة أخيرة صامتة لضمان عدم توقف البث بسبب رمشة اتصال
            try:
                if chat_id in await self._binding.calls():
                     return await self._binding.send_external_frame(
                        chat_id, raw_device, data, raw_frame,
                    )
            except:
                pass
            raise NotInCallError()
        except Exception as e:
            # منع انهيار البوت في حالة وجود فريم تالف
            return None
ثامن ملف
time.py
from typing import Union

from ntgcalls import ConnectionNotFound

from ...exceptions import NotInCallError
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes
from ...types import Direction


class Time(Scaffold):
    @statictypes
    @mtproto_required
    async def time(
        self,
        chat_id: Union[int, str],
        direction: Direction = Direction.OUTGOING,
    ) -> int:
        chat_id = await self.resolve_chat_id(chat_id)
        try:
            return await self._binding.time(chat_id, direction.to_raw())
        except ConnectionNotFound:
            raise NotInCallError()
تاسع ملف
unmute.py
from typing import Union

from ntgcalls import ConnectionNotFound

from ...exceptions import NotInCallError
from ...mtproto_required import mtproto_required
from ...scaffold import Scaffold
from ...statictypes import statictypes


class UnMute(Scaffold):
    @statictypes
    @mtproto_required
    async def unmute(
        self,
        chat_id: Union[int, str],
    ) -> bool:
        chat_id = await self.resolve_chat_id(chat_id)
        try:
            return await self._binding.unmute(chat_id)
        except ConnectionNotFound:
            raise NotInCallError()
ملف الهاندلر
import asyncio
from typing import Any
from typing import Callable
from typing import NamedTuple
from typing import Optional


class Callback(NamedTuple):
    func: Callable
    filters: Optional[Any]


class HandlersHolder:
    def __init__(self):
        self._callbacks = []

    async def _propagate(
        self,
        update,
        client=None,
    ):
        if client:
            tasks = []
            for callback in self._callbacks:
                if not callback.filters or \
                        await callback.filters(client, update):
                    tasks.append(callback.func(client, update))
            await asyncio.gather(*tasks)
        else:
            await asyncio.gather(
                *[
                    callback.func(update)
                    for callback in self._callbacks
                ],
            )

    def add_handler(
        self,
        func: Callable,
        filters=None,
    ) -> Callable:
        self._callbacks.append(Callback(func, filters))
        return func

    def remove_handler(
        self,
        func: Callable,
    ):
        self._callbacks = [x for x in self._callbacks if x.func != func]
ملف الدراكتورس
اسم الملف
on_update.py
الكود
from typing import Callable

from ...scaffold import Scaffold


class OnUpdate(Scaffold):
    def on_update(self, filters=None) -> Callable:
        def decorator(func: Callable) -> Callable:
            return self.add_handler(
                func,
                filters,
            )

        return decorator
ملف ytdlp.py 
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
ملف
ffmpeg.py
الكود
import asyncio
import logging
import os.path
import re
import shlex
import subprocess
from json import JSONDecodeError
from json import loads
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

from ntgcalls import FFmpegError

from .exceptions import ImageSourceFound
from .exceptions import InvalidVideoProportion
from .exceptions import LiveStreamFound
from .exceptions import NoAudioSourceFound
from .exceptions import NoVideoSourceFound
from .types.raw import AudioParameters
from .types.raw import VideoParameters


async def check_stream(
    ffmpeg_parameters: Optional[str],
    path: str,
    stream_parameters: Union[AudioParameters, VideoParameters],
    before_commands: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
):
    try:
        ffprobe = await asyncio.create_subprocess_exec(
            *await cleanup_commands(
                build_command(
                    'ffprobe',
                    ffmpeg_parameters,
                    path,
                    stream_parameters,
                    before_commands,
                    headers,
                    False,
                ),
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise FFmpegError('ffprobe not installed')

    try:
        stdout, stderr = await asyncio.wait_for(
            ffprobe.communicate(),
            timeout=20,
        )
        result = loads(stdout.decode('utf-8')) or {}
        stream_list = result.get('streams', [])
        format_content = result.get('format', [])
        if 'No such file' in stderr.decode('utf-8'):
            raise FileNotFoundError()
    except (subprocess.TimeoutExpired, JSONDecodeError):
        ffprobe.kill()
        raise

    have_video = False
    is_image = True
    have_audio = False
    have_valid_video = False

    original_width, original_height = 0, 0

    for stream in stream_list:
        codec_type = stream.get('codec_type', '')
        codec_name = stream.get('codec_name', '')
        image_codecs = ['png', 'jpeg', 'jpg', 'mjpeg']
        if codec_type == 'video':
            is_image &= codec_name in image_codecs
            have_video = True
            original_width = int(stream.get('width', 0))
            original_height = int(stream.get('height', 0))
            if original_height and original_width:
                have_valid_video = True
        elif codec_type == 'audio':
            have_audio = True

    if isinstance(stream_parameters, VideoParameters):
        if not have_video:
            raise NoVideoSourceFound(path)
        if not have_valid_video:
            raise InvalidVideoProportion(
                'Video proportion not found',
            )

        ratio = float(original_width) / original_height
        new_w = min(original_width, stream_parameters.width)
        new_h = int(new_w / ratio)

        if (
            new_h > stream_parameters.height and
            stream_parameters.adjust_by_height
        ):
            new_h = stream_parameters.height
            new_w = int(new_h * ratio)

        new_w = new_w - 1 if new_w % 2 else new_w
        new_h = new_h - 1 if new_h % 2 else new_h
        stream_parameters.height = new_h
        stream_parameters.width = new_w
        if is_image:
            stream_parameters.frame_rate = 10
            raise ImageSourceFound(path)

    if isinstance(stream_parameters, AudioParameters) and not have_audio:
        raise NoAudioSourceFound(path)

    if 'duration' not in format_content:
        raise LiveStreamFound(path)


async def cleanup_commands(
    commands: List[str],
    process_name: Optional[str] = None,
    blacklist: Optional[List[str]] = None,
) -> List[str]:
    try:
        proc_res = await asyncio.create_subprocess_exec(
            commands[0] if not process_name else process_name,
            '-h',
            'full',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc_res.communicate(),
                timeout=20,
            )
            result = stdout.decode('utf-8')
        except (subprocess.TimeoutExpired, JSONDecodeError):
            proc_res.kill()
            raise
        supported = re.findall(r'(?m)^ *(-\w+).*?\s+', result)
        supported += ['-i']
        new_commands = []
        ignore_next = False

        for v in commands:
            if len(v) > 0:
                if v[0] == '-':
                    ignore_next = v not in supported or \
                        blacklist is not None and v in blacklist

                if not ignore_next:
                    new_commands += [v]
                elif v[0] != '-':
                    ignore_next = False
        return new_commands
    except FileNotFoundError:
        raise FFmpegError(f'{commands[0]} not installed')


def build_command(
    name: str,
    ffmpeg_parameters: Optional[str],
    path: Optional[str],
    stream_parameters: Union[AudioParameters, VideoParameters],
    before_commands: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
    is_livestream: bool = False,
) -> List[str]:
    if not path:
        return []
    command = _get_stream_params(ffmpeg_parameters)

    if isinstance(stream_parameters, VideoParameters):
        command = command['video']
    else:
        command = command['audio']

    ffmpeg_command: List = [name]

    ffmpeg_command += command['start']

    if not os.path.exists(path) \
            and not is_livestream\
            and name == 'ffmpeg':
        ffmpeg_command += [
            '-reconnect',
            '1',
            '-reconnect_at_eof',
            '1',
            '-reconnect_streamed',
            '1',
            '-reconnect_delay_max',
            '2',
        ]

    if name == 'ffprobe':
        ffmpeg_command += [
            '-v',
            'error',
            '-show_entries',
            'stream=width,height,codec_type,codec_name',
            '-show_format',
            '-of',
            'json',
        ]

    if before_commands:
        ffmpeg_command += before_commands

    if headers is not None:
        for i in headers:
            ffmpeg_command.append('-headers')
            ffmpeg_command.append(f'{i}: {headers[i]}')

    ffmpeg_command += [
        '-i',
        f'{path}' if name == 'ffmpeg' else path,
    ]
    ffmpeg_command += command['mid']

    if name == 'ffmpeg':
        ffmpeg_command += _build_ffmpeg_options(stream_parameters)

    ffmpeg_command += command['end']
    if name == 'ffmpeg':
        ffmpeg_command.append('pipe:1')

    return ffmpeg_command


def _get_stream_params(command: Optional[str]):
    arg_names = ['base', 'audio', 'video']
    command_args: Dict = {arg: [] for arg in arg_names}
    current_arg = arg_names[0]

    if command:
        for part in shlex.split(command):
            arg_name = part[2:]
            if arg_name in arg_names:
                current_arg = arg_name
            else:
                command_args[current_arg].append(part)
    command_args = {
        command: _extract_stream_params(command_args[command])
        for command in command_args
    }

    for arg in arg_names[1:]:
        for x in command_args[arg_names[0]]:
            command_args[arg][x] += command_args[arg_names[0]][x]

    del command_args[arg_names[0]]

    return command_args


def _extract_stream_params(command: List[str]):
    arg_names = ['start', 'mid', 'end']
    command_args: Dict = {arg: [] for arg in arg_names}
    current_arg = arg_names[0]

    for part in command:
        arg_name = part[3:]
        if arg_name in arg_names:
            current_arg = arg_name
        else:
            command_args[current_arg].append(part)

    return command_args


def _build_ffmpeg_options(
        stream_parameters: Union[AudioParameters, VideoParameters],
) -> List[str]:
    log_level = logging.getLogger('ffmpeg').level
    ffmpeg_level = 'info' if log_level == logging.DEBUG else 'quiet'

    options = ['-v', ffmpeg_level, '-f']

    if isinstance(stream_parameters, AudioParameters):
        options.extend([
            's16le',
            '-ac', str(stream_parameters.channels),
            '-ar', str(stream_parameters.bitrate),
        ])
    elif isinstance(stream_parameters, VideoParameters):
        options.extend([
            'rawvideo',
            '-r', str(stream_parameters.frame_rate),
            '-pix_fmt',
            'yuv420p',
            '-vf',
            f'scale={stream_parameters.width}:{stream_parameters.height}',
        ])

    return options
ملف exceptions.py
class TooOldPyrogramVersion(Exception):
    def __init__(
            self,
            version_needed: str,
            pyrogram_version: str,
    ):
        super().__init__(
            f'Needed pyrogram {version_needed}+, '
            'actually installed is '
            f'{pyrogram_version}',
        )


class TooOldTelethonVersion(Exception):
    def __init__(
            self,
            version_needed: str,
            telethon_version: str,
    ):
        super().__init__(
            f'Needed telethon {version_needed}+, '
            'actually installed is '
            f'{telethon_version}',
        )


class TooOldHydrogramVersion(Exception):
    def __init__(
            self,
            version_needed: str,
            hydrogram_version: str,
    ):
        super().__init__(
            f'Needed hydrogram {version_needed}+, '
            'actually installed is '
            f'{hydrogram_version}',
        )


class NoMTProtoClientSet(Exception):
    def __init__(self):
        super().__init__(
            'No MTProto client set',
        )


class NoActiveGroupCall(Exception):
    def __init__(self):
        super().__init__(
            'No active group call',
        )


class TimedOutAnswer(Exception):
    def __init__(self):
        super().__init__(
            'Timed out waiting for an answer',
        )


class CallDeclined(Exception):
    def __init__(self, user_id: int):
        super().__init__(
            f'Call declined by {user_id}',
        )


class CallBusy(Exception):
    def __init__(self, user_id: int):
        super().__init__(
            f'The user {user_id} is busy',
        )


class CallDiscarded(Exception):
    def __init__(self, user_id: int):
        super().__init__(
            f'Call discarded by {user_id}',
        )


class NotInCallError(Exception):
    def __init__(self):
        super().__init__(
            'The userbot is not in a call',
        )


class ClientNotStarted(Exception):
    def __init__(self):
        super().__init__(
            'Ensure you have started the process with start() '
            'before calling this method',
        )


class PyTgCallsAlreadyRunning(Exception):
    def __init__(self):
        super().__init__(
            'PyTgCalls client is already running',
        )


class TooManyCustomApiDecorators(Exception):
    def __init__(self):
        super().__init__(
            'Too Many Custom Api Decorators',
        )


class InvalidMTProtoClient(Exception):
    def __init__(self):
        super().__init__(
            'Invalid MTProto Client',
        )


class NoVideoSourceFound(Exception):
    def __init__(self, path: str):
        super().__init__(
            f'No video source found on "{path}"',
        )


class InvalidVideoProportion(Exception):
    def __init__(self, message: str):
        super().__init__(
            message,
        )


class NoAudioSourceFound(Exception):
    def __init__(self, path: str):
        super().__init__(
            f'No audio source found on "{path}"',
        )


class ImageSourceFound(Exception):
    def __init__(self, path: str):
        super().__init__(
            f'Found an image source on "{path}"',
        )


class LiveStreamFound(Exception):
    def __init__(self, path: str):
        super().__init__(
            f'Found a livestream on "{path}"',
        )


class YtDlpError(Exception):
    def __init__(self, message: str):
        super().__init__(
            message,
        )


class MTProtoClientNotConnected(Exception):
    def __init__(self):
        super().__init__(
            'MTProto client not connected',
        )


class UnsupportedMethod(Exception):
    def __init__(self):
        super().__init__(
            'Unsupported method for this kind of call',
        )
ملف 
updated_group_call_participant.py
الكود
from ..chats import GroupCallParticipant
from ..update import Update


class UpdatedGroupCallParticipant(Update):
    def __init__(
        self,
        chat_id: int,
        action: GroupCallParticipant.Action,
        participant: GroupCallParticipant,
    ):
        super().__init__(chat_id)
        self.action = action
        self.participant = participant
ملف
group_call_participant.py
الكود
from enum import auto
from typing import List
from typing import Optional

from ntgcalls import SsrcGroup

from ...types.py_object import PyObject
from ..flag import Flag


class GroupCallParticipant(PyObject):
    class Action(Flag):
        JOINED = auto()
        LEFT = auto()
        KICKED = auto()
        UPDATED = auto()

    class SourceInfo(PyObject):
        def __init__(
            self,
            endpoint: str,
            sources: List[SsrcGroup],
        ):
            self.endpoint: str = endpoint
            self.sources: List[SsrcGroup] = sources

    def __init__(
        self,
        user_id: int,
        muted: bool,
        muted_by_admin: bool,
        video: bool,
        screen_sharing: bool,
        video_camera: bool,
        raised_hand: bool,
        volume: int,
        source: int,
        video_info: Optional[SourceInfo],
        presentation_info: Optional[SourceInfo],
    ):
        self.user_id: int = user_id
        self.muted: bool = muted
        self.muted_by_admin: bool = muted_by_admin
        self.video: bool = video
        self.screen_sharing: bool = screen_sharing
        self.source: int = source
        self.video_camera: bool = video_camera
        self.raised_hand: bool = raised_hand
        self.volume: int = volume
        self.video_info: Optional[
            GroupCallParticipant.SourceInfo
        ] = video_info
        self.presentation_info: Optional[
            GroupCallParticipant.SourceInfo
        ] = presentation_info
ملف
chat_update.py
الكود
from enum import auto
from typing import Any

from ..flag import Flag
from ..update import Update


class ChatUpdate(Update):
    class Status(Flag):
        KICKED = auto()
        LEFT_GROUP = auto()
        CLOSED_VOICE_CHAT = auto()
        INVITED_VOICE_CHAT = auto()
        DISCARDED_CALL = auto()
        INCOMING_CALL = auto()
        BUSY_CALL = auto()
        LEFT_CALL = (
            KICKED |
            LEFT_GROUP |
            CLOSED_VOICE_CHAT |
            DISCARDED_CALL |
            BUSY_CALL
        )

    def __init__(
        self,
        chat_id: int,
        status: Status,
        action: Any = None,
    ):
        super().__init__(chat_id)
        self.status = status
        self.action = action
فولدر raw
الملفات 
audio_parameters.py
الكود
from ...statictypes import statictypes
from ..py_object import PyObject
from ..stream.audio_quality import AudioQuality


class AudioParameters(PyObject):
    @statictypes
    def __init__(
        self,
        bitrate: int = 48000,
        channels: int = 2, # 🔥 تعديل: خلينا الافتراضي 2 (ستيريو) بدل 1 (مونو)
    ):
        # 🔥 إلغاء القيود: مسحنا كود الـ min و max عشان المكتبة متقللش الجودة غصب عننا
        # دلوقتي هيقبل الـ 48000 والـ 2 Channels زي ما هم
        self.bitrate: int = bitrate
        self.channels: int = channels
ملف
audio_stream.py
الكود
from ntgcalls import MediaSource

from ...statictypes import statictypes
from ..py_object import PyObject
from .audio_parameters import AudioParameters


class AudioStream(PyObject):
    @statictypes
    def __init__(
        self,
        media_source: MediaSource,
        path: str,
        parameters: AudioParameters = AudioParameters(),
    ):
        self.media_source: MediaSource = media_source
        self.path: str = path
        self.parameters: AudioParameters = parameters
ملف
stream.py
الكود
from typing import Optional

from ...statictypes import statictypes
from ..py_object import PyObject
from .audio_stream import AudioStream
from .video_stream import VideoStream


class Stream(PyObject):
    @statictypes
    def __init__(
        self,
        microphone: Optional[AudioStream] = None,
        speaker: Optional[AudioStream] = None,
        camera: Optional[VideoStream] = None,
        screen: Optional[VideoStream] = None,
    ):
        self.microphone: Optional[AudioStream] = microphone
        self.speaker: Optional[AudioStream] = speaker
        self.camera: Optional[VideoStream] = camera
        self.screen: Optional[VideoStream] = screen
ملف
video_parameters.py
الكود
from ...statictypes import statictypes
from ..py_object import PyObject
from ..stream.video_quality import VideoQuality


class VideoParameters(PyObject):
    @statictypes
    def __init__(
        self,
        width: int = 1280,      # 🔥 تعديل: خلينا الافتراضي HD 720p
        height: int = 720,      # 🔥 تعديل: ارتفاع 720 بدل 360
        frame_rate: int = 30,   # 🔥 تعديل: 30 فريم عشان السلاسة (بدل 20 المتقطعة)
        adjust_by_height: bool = True,
    ):
        # 🔥 تم نسف القيود: مسحنا كود الـ max و min
        # دلوقتي المكتبة هتحترم قدرات السيرفر وهتقبل الجودة العالية اللي طلبناها في call.py
        
        self.width: int = width
        self.height: int = height
        self.frame_rate: int = frame_rate
        self.adjust_by_height: bool = adjust_by_height
ملف
video_stream.py
الكود
from ntgcalls import MediaSource

from ...statictypes import statictypes
from ..py_object import PyObject
from .video_parameters import VideoParameters


class VideoStream(PyObject):
    @statictypes
    def __init__(
        self,
        media_source: MediaSource,
        path: str,
        parameters: VideoParameters = VideoParameters(),
    ):
        self.media_source: MediaSource = media_source
        self.path: str = path
        self.parameters: VideoParameters = parameters
