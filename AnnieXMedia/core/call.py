import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Union, Optional
from asyncio import Lock

import yt_dlp
from pyrogram import enums, errors
from pyrogram.types import InlineKeyboardMarkup, InputMediaPhoto
from pyrogram.errors import ChatAdminRequired

# Imports based on PyTgCalls v3.0 Docs
from pytgcalls import PyTgCalls, filters
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality,
    GroupCallConfig,
    Update,
    ChatUpdate,
    StreamEnded
)
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NotInCallError,
    NoAudioSourceFound,
    NoVideoSourceFound,
    PyTgCallsAlreadyRunning
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
from AnnieXMedia.utils.stream.autoclear import auto_clean
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

# ✨ ميزة من Hasii: إخفاء أخطاء PyTgCalls الوهمية من الكونسول
class PyTgCallsErrorFilter(logging.Filter):
    def filter(self, record):
        if 'UpdateGroupCall' in record.getMessage(): return False
        if 'Connection with chat id' in record.getMessage() and 'not found' in record.getMessage(): return False
        return True

logging.getLogger('pyrogram.dispatcher').addFilter(PyTgCallsErrorFilter())

autoend = {}
counter = {}

# ===============================
# Helper Functions
# ===============================

async def get_direct_link(videoid: str, video: bool = False):
    if not videoid: return None
    link = f"https://www.youtube.com/watch?v={videoid}"
    fmt = "best[ext=mp4]/best" if video else "bestaudio/best"
    opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True
    }
    try:
        loop = asyncio.get_running_loop()
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=False)
                return info.get("url")
        return await loop.run_in_executor(None, _extract)
    except: return link

def _build_stream(path: str, video: bool = False, ffmpeg_opts: str = "") -> MediaStream:
    """
    Constructs a MediaStream object compatible with PyTgCalls v3.0.
    ✨ تعديلات Hasii: تم إضافة إعدادات البافر لمنع التقطيع، وتم مسح reconnect، مع الحفاظ على threads للسيرفر.
    """
    path = str(path)
    
    # 1. Base FFmpeg parameters (دمج قوة Hasii مع Annie)
    # استخدام 2 كور للمكالمة + أحجام بافر كبيرة + ضبط التزامن
    base_flags = (
        "-threads 2 "
        "-probesize 10M -analyzeduration 10M -rtbufsize 5M "
        "-fflags +genpts+igndts+nobuffer -sync ext "
    )

    # 2. Add Custom Opts (like Seek -ss)
    final_ffmpeg = base_flags + ffmpeg_opts

    # 3. Return the Universal MediaStream Object
    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH, 
        video_parameters=VideoQuality.HD_720p, 
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=final_ffmpeg,
    )

async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped: await auto_clean(popped)
    db[chat_id] = []
    try:
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except: pass

# ===============================
# The Controller Class
# ===============================

class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        self.one = PyTgCalls(self.userbot1) if self.userbot1 else None
        self.two = PyTgCalls(self.userbot2) if self.userbot2 else None
        self.three = PyTgCalls(self.userbot3) if self.userbot3 else None
        self.four = PyTgCalls(self.userbot4) if self.userbot4 else None
        self.five = PyTgCalls(self.userbot5) if self.userbot5 else None

        self.active_calls: set[int] = set()
        self.chat_locks: dict[int, Lock] = {}
        
        # ✨ ميزة من Hasii: منع تكرار الأوامر لو فيه أكتر من مساعد في الجروب
        self._stream_end_cache = {} 

    def get_lock(self, chat_id: int) -> Lock:
        if chat_id not in self.chat_locks:
            self.chat_locks[chat_id] = Lock()
        return self.chat_locks[chat_id]

    # ✨ ميزة من Hasii: التعامل مع حظر تيليجرام لتعديل وإرسال الرسايل
    async def _edit_media_with_retry(self, message, media_obj: InputMediaPhoto, reply_markup):
        try: return await message.edit_media(media=media_obj, reply_markup=reply_markup)
        except errors.FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try: return await message.edit_media(media=media_obj, reply_markup=reply_markup)
            except: return None
        except: return None

    async def _send_photo_with_retry(self, chat_id: int, photo, caption: str, reply_markup):
        try: return await app.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup)
        except errors.FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try: return await app.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup)
            except: return None
        except: return None

    # --- Standard Controls ---
    async def pause_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await assistant.pause(chat_id)

    async def resume_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await assistant.resume(chat_id)

    async def mute_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await assistant.mute(chat_id)

    async def unmute_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await assistant.unmute(chat_id)

    async def stop_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            
            # ✨ ميزة من Hasii: إيقاف التحميل المسبق عند إيقاف البوت
            try:
                from AnnieXMedia import preload
                await preload.cancel_preload(chat_id)
            except: pass
            
            await _clear_(chat_id)
            try: await assistant.leave_call(chat_id)
            except: pass
            finally: self.active_calls.discard(chat_id)

    async def force_stop_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            try:
                check = db.get(chat_id)
                if check: check.pop(0)
            except: pass
            
            try:
                from AnnieXMedia import preload
                await preload.cancel_preload(chat_id)
            except: pass

            await remove_active_video_chat(chat_id)
            await remove_active_chat(chat_id)
            await _clear_(chat_id)
            try: await assistant.leave_call(chat_id)
            except: pass
            finally: self.active_calls.discard(chat_id)

    async def change_volume_call(self, chat_id: int, volume: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            try: await assistant.change_volume_call(chat_id, volume)
            except Exception as e:
                LOGGER(__name__).error(f"Failed to change volume for {chat_id}: {e}")
                raise AssistantErr(f"Failed to change volume: {e}")

    # --- Advanced Controls ---
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: int, duration: int, mode: str) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            ffmpeg_opts = f"-ss {to_seek} "
            is_video = (mode == "video")
            stream = _build_stream(file_path, video=is_video, ffmpeg_opts=ffmpeg_opts)
            await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))

    async def skip_stream(self, chat_id: int, link: str, video: bool = False) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            stream = _build_stream(link, video=video)
            await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))

    # --- Core Join/Play Logic ---
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: bool = False, image: str = None) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            lang = await get_lang(chat_id)
            _ = get_string(lang)

            # ✨ ميزة من Hasii: التأكد إن البوت مش مطرود أو المايك مقفول
            try:
                chat = await app.get_chat(chat_id)
                if chat.type == enums.ChatType.CHANNEL:
                    assistant_member = await app.get_chat_member(chat_id, assistant.me.id)
                    if assistant_member.status == enums.ChatMemberStatus.BANNED:
                        raise AssistantErr("❌ Assistant is banned in this channel.")
            except: pass

            final_link = link
            stream = _build_stream(final_link, video=video)

            # ✨ ميزة من Hasii: نظام إعادة المحاولة (Retry) في حالة تهنيج حالة المكالمة
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                    break # نجاح
                except (NoActiveGroupCall, ChatAdminRequired):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    raise AssistantErr(_["call_8"])
                except Exception as e:
                    if "group call not found" in str(e).lower() or "cannot be initialized" in str(e).lower():
                        if attempt < max_retries - 1:
                            try: await assistant.leave_call(chat_id)
                            except: pass
                            await asyncio.sleep(1)
                            continue
                    raise AssistantErr(f"Error: {e}")

            self.active_calls.add(chat_id)
            await add_active_chat(chat_id)
            await music_on(chat_id)
            if video: await add_active_video_chat(chat_id)
            
            if await is_autoend():
                counter[chat_id] = {}
                try:
                    users = len(await assistant.get_participants(chat_id))
                    if users == 1: autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                except: pass

            # ✨ ميزة من Hasii: بدء التحميل المسبق للأغاني الجاية
            try:
                from AnnieXMedia import preload
                asyncio.create_task(preload.start_preload(chat_id, count=2))
            except: pass

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (v3.0)...")
        if self.one and config.STRING1: await self.one.start()
        if self.two and config.STRING2: await self.two.start()
        if self.three and config.STRING3: await self.three.start()
        if self.four and config.STRING4: await self.four.start()
        if self.five and config.STRING5: await self.five.start()

    # --- Decorators / Filters System ---
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        
        for assistant in assistants:
            @assistant.on_update(filters.stream_end())
            async def stream_end_handler(client, update: Update):
                chat_id = update.chat_id
                
                # ✨ ميزة من Hasii: نظام الكاش لمنع التكرار لو فيه أكتر من مساعد
                current_time = asyncio.get_event_loop().time()
                if chat_id in self._stream_end_cache:
                    if current_time - self._stream_end_cache[chat_id] < 2.0:
                        return # رسالة مكررة، تجاهلها
                self._stream_end_cache[chat_id] = current_time
                self._stream_end_cache = {cid: t for cid, t in self._stream_end_cache.items() if current_time - t < 5.0}
                
                LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
                await self.play(client, chat_id)

            @assistant.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
            async def left_call_handler(client, update: Update):
                await self.stop_stream(update.chat_id)
            
            @assistant.on_update(filters.chat_update(ChatUpdate.Status.KICKED))
            async def kicked_handler(client, update: Update):
                await self.stop_stream(update.chat_id)

    # --- Queue Processing ---
    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            check = db.get(chat_id)
            if not check:
                await _clear_(chat_id)
                return

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
                    finally: self.active_calls.discard(chat_id)
                    
                    # ✨ ميزة من Hasii: رسالة الـ Auto End لو الطابور خلص
                    if config.AUTO_END:
                        try: await app.send_message(chat_id, "✅ Queue finished. Stream ended automatically.")
                        except: pass
                    return
            except:
                try: await _clear_(chat_id); return await client.leave_call(chat_id)
                except: return

            queued = check[0].get("file")
            title = (check[0].get("title") or "").title()
            user = check[0].get("by")
            original_chat_id = check[0].get("chat_id")
            streamtype = check[0].get("streamtype")
            videoid = check[0].get("vidid")
            duration_str = check[0].get("dur")
            
            is_video = str(streamtype) == "video"
            
            final_link = queued
            if "youtube" in str(queued):
                 try:
                    direct = await get_direct_link(videoid, video=is_video)
                    if direct: final_link = direct
                 except: pass

            stream = _build_stream(final_link, video=is_video)

            try:
                await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                
                if is_video: await add_active_video_chat(chat_id)
                else: await remove_active_video_chat(chat_id)

                img = await get_thumb(videoid)
                from AnnieXMedia.utils.inline import stream_markup
                button = stream_markup(get_string(await get_lang(chat_id)), chat_id)
                
                # مسح الرسالة القديمة بنظافة
                try:
                    if db[chat_id][0].get("mystic"):
                        await db[chat_id][0].get("mystic").delete()
                except: pass
                
                # ✨ ميزة من Hasii: إضافة شريط التقدم الوهمي الجمالي في الكابشن
                timer_bar = "—" * 12 + "●" + "—" * 0 # شكل مبدئي للشريط
                caption_text = get_string(await get_lang(chat_id))["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{videoid}", 
                    title[:23], 
                    duration_str, 
                    user
                )
                caption_text += f"\n\n⏳ `00:00 {timer_bar} {duration_str}`"

                # إرسال الرسالة بنظام الـ Retry للحماية من الفلود
                run = await self._send_photo_with_retry(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=caption_text,
                    reply_markup=InlineKeyboardMarkup(button),
                )
                
                if run:
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"
                
                # ✨ ميزة من Hasii: تشغيل البريلود للأغنية اللي عليها الدور
                try:
                    from AnnieXMedia import preload
                    asyncio.create_task(preload.start_preload(chat_id, count=2))
                except: pass
                
            except Exception as e:
                LOGGER(__name__).error(f"Queue Play Error: {e}")
                await _clear_(chat_id)
                try: await app.send_message(original_chat_id, "❌ Failed to switch stream.")
                except: pass

StreamController = Call()
