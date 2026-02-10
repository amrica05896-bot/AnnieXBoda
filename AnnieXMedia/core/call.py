# Authored By Certified Coders © 2026
# System: Call Controller (Adaptive 16-Core Edition)
# Optimized for: Custom PyTgCalls (High Quality + Auto-Detect Cores + New Filters)

import asyncio
import os
import traceback
from datetime import datetime, timedelta
from typing import Union

from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup
from ntgcalls import ConnectionNotFound, TelegramServerError

# 🔥 استيراد الكلاسات من مكتبتك المعدلة
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

# --- [1] إعدادات البث الديناميكية (Smart Cores Logic) ---
def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    # 1. كشف عدد الكورات الحقيقي للسيرفر
    # لو 16 كور هيشتغل بـ 16، لو 1 هيشتغل بـ 1 (أمان + سرعة)
    cores = os.cpu_count() or 2
    
    # 2. ضبط خيوط المعالجة بناءً على الكورات
    # -threads: عدد الكورات
    # -preset ultrafast: أسرع وضع لتقليل الحمل
    # -tune zerolatency: استجابة لحظية للبث
    titan_flags = f"-threads {cores} -preset ultrafast -tune zerolatency"
    
    if str(path).startswith("http"):
        # تحسينات الشبكة للروابط المباشرة (مثل يوتيوب)
        titan_flags += " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    
    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    # تحديد الأعلام (Flags) حسب نوع البث
    video_flags = MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE
    audio_flags = MediaStream.Flags.REQUIRED

    return MediaStream(
        media_path=path,
        # ✅ الجودة المستقرة لتليجرام (128kbps) كما طلبت
        audio_parameters=AudioQuality.HIGH,   
        # ✅ جودة الفيديو 720p 60FPS (بناءً على ملف video_quality.py)
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
        self.userbot1 = userbot.one
        self.userbot2 = userbot.two
        self.userbot3 = userbot.three
        self.userbot4 = userbot.four
        self.userbot5 = userbot.five

        # زيادة مدة الكاش لـ 24 ساعة (86400) لتقليل طلبات API كما في ملف pytgcalls.py
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
        # تشغيل تلقائي للأغنية التالية باستخدام الكونفيج الإجباري
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

    @capture_internal_err
    async def stream_call(self, link: str) -> None:
        assistant = await group_assistant(self, config.LOGGER_ID)
        stream = dynamic_media_stream(link)
        try:
            await assistant.play(config.LOGGER_ID, stream)
            await asyncio.sleep(8)
        except (NoActiveGroupCall, ConnectionNotFound):
            LOGGER(__name__).warning("⚠️ لم يتمكن البوت من الانضمام لمجموعة السجل.")
        except Exception:
            pass
        finally:
            try:
                await assistant.leave_call(config.LOGGER_ID)
            except: pass

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
        
        # 🔥 مكتبتك بتتطلب GroupCallConfig في المجموعات
        config = GroupCallConfig(auto_start=True)

        try:
            await assistant.play(chat_id, stream, config=config)
        except NoActiveGroupCall:
            # محاولة الإنشاء التلقائي للمكالمة (ميزة في مكتبتك)
            try:
                await assistant.create_group_call(chat_id)
                await assistant.play(chat_id, stream, config=config)
            except:
                raise AssistantErr("⚠️ **لا توجد مكالمة فيديو نشطة!**\nيرجى بدء مكالمة أولاً.")
        except (NoAudioSourceFound, NoVideoSourceFound):
            raise AssistantErr("❌ فشل العثور على مصدر الملف.")
        except AttributeError:
             # حماية الـ NoneType (إعادة محاولة سريعة)
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

    # --- [3] نظام التشغيل التلقائي (Next Track) ---
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

        # تجهيز التراك التالي
        track = check[0]
        queued = track["file"]
        title = track["title"]
        streamtype = track["streamtype"]
        videoid = track["vidid"]
        video = (streamtype == "video")
        
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
        
        # تحديث الواجهة (حماية من الكراشات)
        img = await get_thumb(videoid)
        lang = await get_lang(chat_id)
        _ = get_string(lang)
        button = stream_markup(_, chat_id)
        
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

    # --- [4] تشغيل العملاء والفلاتر الذكية ---

    async def start(self) -> None:
        LOGGER(__name__).info("Starting Custom PyTgCalls Clients...")
        clients = [self.one, self.two, self.three, self.four, self.five]
        for cli in clients:
            if cli._app._bind_client: 
                await cli.start()

    async def decorators(self) -> None:
        assistants = [self.one, self.two, self.three, self.four, self.five]
        
        # 🔥 استخدام الفلاتر الحديثة (Filters) بناءً على ملف filters.py
        
        # 1. فلتر انتهاء البث (Stream Ended)
        # التأكد إن اللي خلص ده "Audio" (لأن الفيديو بيخلص معاه تلقائي)
        @filters.stream_end(StreamEnded.Type.AUDIO)
        async def stream_end_handler(client: PyTgCalls, update: StreamEnded):
            await self.play(client, update.chat_id)

        # 2. فلتر تحديثات الشات (Left/Kicked/Closed)
        @filters.chat_update(
            ChatUpdate.Status.LEFT_CALL | 
            ChatUpdate.Status.KICKED | 
            ChatUpdate.Status.CLOSED_VOICE_CHAT
        )
        async def chat_update_handler(client: PyTgCalls, update: ChatUpdate):
            await self.stop_stream(update.chat_id)

        # تسجيل الفلاتر لكل المساعدين النشطين
        for assistant in assistants:
            # التأكد من وجود دالة add_handler (من ملف scaffold.py)
            if hasattr(assistant, 'add_handler'):
                assistant.add_handler(stream_end_handler)
                assistant.add_handler(chat_update_handler)

StreamController = Call()
