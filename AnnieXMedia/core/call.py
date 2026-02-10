# Authored By Certified Coders © 2026
# System: Call Controller (Fully Compatible with Custom Lib)
# Optimized for: 16-Core Adaptive & RAM Protection

import asyncio
import os
import traceback
from typing import Union

from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup
from ntgcalls import ConnectionNotFound, TelegramServerError

# 🔥 استيراد المكتبة بناءً على ملفاتك المرسلة
from pytgcalls import PyTgCalls, filters
from pytgcalls.exceptions import (
    NoActiveGroupCall, 
    NoAudioSourceFound, 
    NoVideoSourceFound,
    NotInCallError
)
from pytgcalls.types import (
    AudioQuality, 
    VideoQuality, 
    MediaStream, 
    StreamEnded, 
    ChatUpdate, 
    GroupCallConfig, 
    Update
)

import config
from strings import get_string
from AnnieXMedia import LOGGER, YouTube, app, userbot
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import (
    add_active_chat,
    add_active_video_chat,
    get_lang,
    get_loop,
    group_assistant,
    is_autoend,
    music_on,
    remove_active_chat,
    remove_active_video_chat,
    set_loop,
)
from AnnieXMedia.utils.exceptions import AssistantErr
from AnnieXMedia.utils.formatters import check_duration, seconds_to_min, speed_converter
from AnnieXMedia.utils.inline.play import stream_markup
from AnnieXMedia.utils.stream.autoclear import auto_clean
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

autoend = {}
counter = {}

# --- [1] إعدادات البث الذكية (Adaptive MediaStream) ---
def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    # كشف عدد الكورات (لو 16 يشتغل بـ 16، لو أقل يتأقلم)
    cores = os.cpu_count() or 2
    
    # إعدادات FFmpeg (بناءً على ملف media_stream.py الخاص بيك)
    # -preset ultrafast: لتقليل استخدام الرام والبروسيسور
    # -tune zerolatency: عشان البث يبدأ فوراً
    titan_flags = f"-threads {cores} -preset ultrafast -tune zerolatency"
    
    if str(path).startswith("http"):
        # تحسينات للروابط المباشرة لتقليل التقطيع
        titan_flags += " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    
    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    # إجبار الفيديو والصوت (بناءً على ملف media_stream.py Flags)
    video_flags = MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE
    audio_flags = MediaStream.Flags.REQUIRED

    return MediaStream(
        media_path=path,
        # ✅ AudioQuality.HIGH (128k) للاستقرار (زي ما طلبت)
        audio_parameters=AudioQuality.HIGH,   
        # ✅ VideoQuality.HD_720p (60FPS) بناءً على ملف video_quality.py
        video_parameters=VideoQuality.HD_720p, 
        audio_flags=audio_flags,
        video_flags=video_flags,
        ffmpeg_parameters=titan_flags,
    )

async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped:
        await auto_clean(popped)
    db[chat_id] = []
    await remove_active_video_chat(chat_id)
    await remove_active_chat(chat_id)
    await set_loop(chat_id, 0)

class Call:
    def __init__(self):
        # الحفاظ على أسماء المتغيرات القديمة عشان السورس ميكرش
        self.userbot1 = userbot.one
        self.userbot2 = userbot.two
        self.userbot3 = userbot.three
        self.userbot4 = userbot.four
        self.userbot5 = userbot.five

        # كاش 24 ساعة (86400) لتقليل الضغط على API تليجرام
        self.one = PyTgCalls(self.userbot1, cache_duration=86400)
        self.two = PyTgCalls(self.userbot2, cache_duration=86400)
        self.three = PyTgCalls(self.userbot3, cache_duration=86400)
        self.four = PyTgCalls(self.userbot4, cache_duration=86400)
        self.five = PyTgCalls(self.userbot5, cache_duration=86400)

        self.active_calls: set[int] = set()

    # --- [2] التحكم في البث ---

    @capture_internal_err
    async def pause_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try:
            await assistant.resume(chat_id)
        except:
            await assistant.unmute(chat_id)

    @capture_internal_err
    async def mute_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.mute(chat_id)

    @capture_internal_err
    async def unmute_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.unmute(chat_id)

    @capture_internal_err
    async def stop_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except: pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def force_stop_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try:
            check = db.get(chat_id)
            if check: check.pop(0)
        except: pass
        
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await _clear_(chat_id)
        
        try:
            await assistant.leave_call(chat_id)
        except: pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        # 🔥 إجباري: لازم نبعت GroupCallConfig حسب ملف play.py الخاص بيك
        config = GroupCallConfig(auto_start=True)
        stream = dynamic_media_stream(path=link, video=bool(video))
        await assistant.play(chat_id, stream, config=config)

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        ffmpeg_params = f"-ss {to_seek} -to {duration}"
        is_video = mode == "video"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ffmpeg_params)
        await assistant.play(chat_id, stream)

    @capture_internal_err
    async def speedup_stream(self, chat_id: int, file_path: str, speed: float, playing: list) -> None:
        if not isinstance(playing, list) or not playing or not isinstance(playing[0], dict):
            raise AssistantErr("Invalid stream info for speedup.")

        assistant = await group_assistant(self, chat_id)
        base = os.path.basename(file_path)
        chatdir = os.path.join("playback", str(speed))
        os.makedirs(chatdir, exist_ok=True)
        out = os.path.join(chatdir, base)

        if not os.path.exists(out):
            vs = str(2.0 / float(speed))
            cmd = f'ffmpeg -i "{file_path}" -filter:v "setpts={vs}*PTS" -filter:a atempo={speed} -y "{out}"'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        dur = int(await asyncio.get_event_loop().run_in_executor(None, check_duration, out))
        played, con_seconds = speed_converter(playing[0]["played"], speed)
        duration_min = seconds_to_min(dur)
        is_video = playing[0]["streamtype"] == "video"
        ffmpeg_params = f"-ss {played} -to {duration_min}"
        stream = dynamic_media_stream(path=out, video=is_video, ffmpeg_params=ffmpeg_params)

        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            await assistant.play(chat_id, stream)
            db[chat_id][0].update({
                "played": con_seconds,
                "dur": duration_min,
                "seconds": dur,
                "speed_path": out,
                "speed": speed,
                "old_dur": db[chat_id][0].get("dur"),
                "old_second": db[chat_id][0].get("seconds"),
            })
        else:
            raise AssistantErr("Stream mismatch during speedup.")

    # --- [3] الانضمام والتشغيل (Join Call) ---

    @capture_internal_err
    async def join_call(
        self,
        chat_id: int,
        original_chat_id: int,
        link: str,
        video: Union[bool, str] = None,
        image: Union[bool, str] = None,
    ) -> None:
        assistant = await group_assistant(self, chat_id)
        stream = dynamic_media_stream(path=link, video=bool(video))
        # 🔥 إجباري: Config حسب مكتبتك
        config = GroupCallConfig(auto_start=True)

        try:
            await assistant.play(chat_id, stream, config=config)
        except NoActiveGroupCall:
            # محاولة الإنشاء التلقائي
            try:
                await assistant.create_group_call(chat_id)
                await assistant.play(chat_id, stream, config=config)
            except:
                raise AssistantErr("⚠️ **لا توجد مكالمة فيديو نشطة!**\nيرجى بدء مكالمة أولاً.")
        except (NoAudioSourceFound, NoVideoSourceFound):
            raise AssistantErr("❌ فشل العثور على مصدر الملف.")
        except AttributeError:
             # حماية الـ NoneType (خاصة بالسيرفرات القوية)
             try:
                 await assistant.leave_call(chat_id)
                 await asyncio.sleep(0.5)
                 await assistant.play(chat_id, stream, config=config)
             except:
                 raise AssistantErr("⚠️ خطأ في الاتصال، حاول مرة أخرى.")
        except Exception as e:
            raise AssistantErr(f"❌ خطأ غير متوقع: {e}")
                 
        self.active_calls.add(chat_id)
        await add_active_chat(chat_id)
        await music_on(chat_id)
        if video: await add_active_video_chat(chat_id)

        if await is_autoend():
            counter[chat_id] = {}
            try:
                users = len(await assistant.get_participants(chat_id))
                if users == 1:
                    autoend[chat_id] = datetime.now() + timedelta(minutes=1)
            except: pass

    @capture_internal_err
    async def stream_call(self, link: str) -> None:
        assistant = await group_assistant(self, config.LOGGER_ID)
        stream = dynamic_media_stream(link)
        try:
            await assistant.play(config.LOGGER_ID, stream)
            await asyncio.sleep(5)
        except: pass
        finally:
            try: await assistant.leave_call(config.LOGGER_ID)
            except: pass

    # --- [4] التشغيل التالي (Queue Handler) ---

    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        popped = None
        loop = await get_loop(chat_id)
        
        try:
            if loop == 0:
                popped = check.pop(0)
            else:
                loop = loop - 1
                await set_loop(chat_id, loop)
            
            if popped: await auto_clean(popped)
            
            if not check:
                await _clear_(chat_id)
                try: await client.leave_call(chat_id)
                except: pass
                self.active_calls.discard(chat_id)
                return
        except:
            try:
                await _clear_(chat_id)
                return await client.leave_call(chat_id)
            except: return

        # بيانات التراك
        track = check[0]
        queued = track["file"]
        title = track["title"]
        streamtype = track["streamtype"]
        videoid = track["vidid"]
        video = (streamtype == "video")
        
        if track.get("old_dur"):
            db[chat_id][0].update({"dur": track["old_dur"], "seconds": track["old_second"], "speed_path": None, "speed": 1.0})

        stream = dynamic_media_stream(path=queued, video=video)
        
        try:
            await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
        except Exception:
            try:
                await client.leave_call(chat_id)
                await asyncio.sleep(0.5)
                await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except:
                return await app.send_message(track["chat_id"], "❌ فشل تشغيل المقطع التالي.")
        
        # تحديث الواجهة
        img = await get_thumb(videoid)
        button = stream_markup(get_string(await get_lang(chat_id)), chat_id)
        
        try:
            run = await app.send_photo(
                chat_id=track["chat_id"],
                photo=img,
                caption=f"🏷 **التالي:** [{title[:25]}](https://t.me/{app.username}?start=info_{videoid})\n⏱ **المدة:** {track['dur']}\n👤 **بواسطة:** {track['by']}",
                reply_markup=InlineKeyboardMarkup(button)
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
        except: pass

    # --- [5] الفلاتر والتشغيل (مهم جداً) ---

    async def start(self) -> None:
        LOGGER(__name__).info("Starting Custom PyTgCalls Clients...")
        clients = [self.one, self.two, self.three, self.four, self.five]
        for cli in clients:
            if hasattr(cli, '_app') and cli._app._bind_client: 
                await cli.start()

    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        
        # 🔥 تعريف الفلاتر بنفس الطريقة الموجودة في ملف filters.py الخاص بيك
        
        # 1. فلتر انتهاء البث
        @filters.stream_end(StreamEnded.Type.AUDIO)
        async def stream_end_handler(client: PyTgCalls, update: StreamEnded):
            await self.play(client, update.chat_id)

        # 2. فلتر تحديثات الشات (الخروج والطرد)
        @filters.chat_update(
            ChatUpdate.Status.LEFT_CALL | 
            ChatUpdate.Status.KICKED | 
            ChatUpdate.Status.CLOSED_VOICE_CHAT
        )
        async def chat_update_handler(client: PyTgCalls, update: ChatUpdate):
            await self.stop_stream(update.chat_id)

        # تسجيل الهاندلرز باستخدام add_handler من Scaffold
        for assistant in assistants:
            if hasattr(assistant, 'add_handler'):
                assistant.add_handler(stream_end_handler)
                assistant.add_handler(chat_update_handler)

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if config.STRING1: pings.append(self.one.ping)
        if config.STRING2: pings.append(self.two.ping)
        if config.STRING3: pings.append(self.three.ping)
        if config.STRING4: pings.append(self.four.ping)
        if config.STRING5: pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

StreamController = Call()
