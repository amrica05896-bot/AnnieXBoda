# Authored By Certified Coders © 2026
# System: PyTgCalls V2.2.11 Core Call Controller
# Optimized for Python 3.13+ Asyncio & NTgCalls Native Binds

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Union, Optional
from asyncio import Lock

import yt_dlp
from pyrogram import enums, errors
from pyrogram.types import InlineKeyboardMarkup, InputMediaPhoto
from pyrogram.errors import ChatAdminRequired

from pytgcalls import PyTgCalls, filters
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality,
    GroupCallConfig,
    Update,
    ChatUpdate,
    StreamEnded,
    GroupCallParticipant
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


class PyTgCallsErrorFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if 'UpdateGroupCall' in msg: return False
        if 'Connection with chat id' in msg and 'not found' in msg: return False
        return True

logging.getLogger('pyrogram.dispatcher').addFilter(PyTgCallsErrorFilter())

autoend = {}
counter = {}


async def get_direct_link(videoid: str, video: bool = False):
    """جلب الرابط المباشر باستخدام yt_dlp لدعم السرعة القصوى"""
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
    except Exception: 
        return link


def _build_stream(path: str, video: bool = False, ffmpeg_opts: str = "") -> MediaStream:
    """بناء مجرى البيانات وفقاً لأحدث معايير MediaStream في V2.2.X"""
    path = str(path)
    base_flags = (
        "-threads 2 "
        "-probesize 10M -analyzeduration 10M -rtbufsize 5M "
        "-fflags +genpts+igndts+nobuffer -sync ext "
    )
    final_ffmpeg = base_flags + ffmpeg_opts
    
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
    except Exception: pass


class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        # يتم التهيئة في دالة start حصرياً لمنع كراش Python 3.13 Event Loop
        self.one = None
        self.two = None
        self.three = None
        self.four = None
        self.five = None

        self.active_calls: set[int] = set()
        self.chat_locks: dict[int, Lock] = {}
        self._stream_end_cache = {} 

    def get_lock(self, chat_id: int) -> Lock:
        if chat_id not in self.chat_locks:
            self.chat_locks[chat_id] = Lock()
        return self.chat_locks[chat_id]

    async def _edit_media_with_retry(self, message, media_obj: InputMediaPhoto, reply_markup):
        try: return await message.edit_media(media=media_obj, reply_markup=reply_markup)
        except errors.FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try: return await message.edit_media(media=media_obj, reply_markup=reply_markup)
            except Exception: return None
        except Exception: return None

    async def _send_photo_with_retry(self, chat_id: int, photo, caption: str, reply_markup):
        try: return await app.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup)
        except errors.FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try: return await app.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup)
            except Exception: return None
        except Exception: return None

    # --- استبدال دوال التحكم القديمة بالمسميات والتحديثات الجديدة ---
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
            await _clear_(chat_id)
            try: 
                await assistant.leave_call(chat_id, close=False)
            except Exception: pass
            finally: self.active_calls.discard(chat_id)

    async def force_stop_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            try:
                check = db.get(chat_id)
                if check: check.pop(0)
            except Exception: pass
            
            await remove_active_video_chat(chat_id)
            await remove_active_chat(chat_id)
            await _clear_(chat_id)
            try: 
                # تفعيل الميزة الجديدة close=True لتفريغ الرامات كلياً
                await assistant.leave_call(chat_id, close=True)
            except Exception: pass
            finally: self.active_calls.discard(chat_id)

    async def change_volume_call(self, chat_id: int, volume: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            try: await assistant.change_volume_call(chat_id, volume)
            except Exception as e:
                LOGGER(__name__).error(f"Failed to change volume for {chat_id}: {e}")
                raise AssistantErr(f"Failed to change volume: {e}")

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

    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: bool = False, image: str = None) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            lang = await get_lang(chat_id)
            _ = get_string(lang)

            try:
                chat = await app.get_chat(chat_id)
                if chat.type == enums.ChatType.CHANNEL:
                    assistant_member = await app.get_chat_member(chat_id, assistant.me.id)
                    if assistant_member.status == enums.ChatMemberStatus.BANNED:
                        raise AssistantErr("❌ Assistant is banned in this channel.")
            except Exception: pass

            final_link = link
            stream = _build_stream(final_link, video=video)

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                    break
                except (NoActiveGroupCall, ChatAdminRequired):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    raise AssistantErr(_["call_8"])
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    if "group call not found" in str(e).lower() or "cannot be initialized" in str(e).lower():
                        if attempt < max_retries - 1:
                            try: await assistant.leave_call(chat_id)
                            except Exception: pass
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
                    # تفعيل ميزة no_update للكاش الصارمة (V2.2.X)
                    users = len(await assistant.get_participants(chat_id))
                    if users == 1: autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                except Exception: pass

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (NTgCalls v2.2.11)...")
        # التحميل المتأخر (Lazy Loading) ضروري هنا
        if self.userbot1: self.one = PyTgCalls(self.userbot1)
        if self.userbot2: self.two = PyTgCalls(self.userbot2)
        if self.userbot3: self.three = PyTgCalls(self.userbot3)
        if self.userbot4: self.four = PyTgCalls(self.userbot4)
        if self.userbot5: self.five = PyTgCalls(self.userbot5)

        if self.one and config.STRING1: await self.one.start()
        if self.two and config.STRING2: await self.two.start()
        if self.three and config.STRING3: await self.three.start()
        if self.four and config.STRING4: await self.four.start()
        if self.five and config.STRING5: await self.five.start()

    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        
        for assistant in assistants:
            @assistant.on_update(filters.stream_end())
            async def stream_end_handler(client: PyTgCalls, update: Update):
                if isinstance(update, StreamEnded):
                    chat_id = update.chat_id
                    
                    current_time = asyncio.get_running_loop().time()
                    if chat_id in self._stream_end_cache:
                        if current_time - self._stream_end_cache[chat_id] < 2.0:
                            return
                    self._stream_end_cache[chat_id] = current_time
                    self._stream_end_cache = {cid: t for cid, t in self._stream_end_cache.items() if current_time - t < 5.0}
                    
                    LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
                    await self.play(client, chat_id)

            @assistant.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
            async def left_call_handler(client: PyTgCalls, update: Update):
                await self.stop_stream(update.chat_id)
            
            # ميزة التقاط طرد المساعد باستخدام UpdatedGroupCallParticipant (V2.2.X)
            @assistant.on_update(filters.call_participant(GroupCallParticipant.Action.KICKED))
            async def kicked_handler(client: PyTgCalls, update: Update):
                await self.stop_stream(update.chat_id)

    @capture_internal_err
    async def play(self, client: PyTgCalls, chat_id: int) -> None:
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
                    try: await client.leave_call(chat_id, close=False)
                    except Exception: pass
                    finally: self.active_calls.discard(chat_id)
                    
                    if config.AUTO_END:
                        try: await app.send_message(chat_id, "✅ Queue finished. Stream ended automatically.")
                        except Exception: pass
                    return
            except Exception:
                try: 
                    await _clear_(chat_id)
                    return await client.leave_call(chat_id, close=False)
                except Exception: return

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
                 except Exception: pass

            stream = _build_stream(final_link, video=is_video)

            try:
                await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                
                if is_video: await add_active_video_chat(chat_id)
                else: await remove_active_video_chat(chat_id)

                img = await get_thumb(videoid)
                from AnnieXMedia.utils.inline import stream_markup
                button = stream_markup(get_string(await get_lang(chat_id)), chat_id)
                
                try:
                    if db[chat_id][0].get("mystic"):
                        await db[chat_id][0].get("mystic").delete()
                except Exception: pass
                
                caption_text = get_string(await get_lang(chat_id))["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{videoid}", 
                    title[:23], 
                    duration_str, 
                    user
                )

                run = await self._send_photo_with_retry(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=caption_text,
                    reply_markup=InlineKeyboardMarkup(button),
                )
                
                if run:
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                LOGGER(__name__).error(f"Queue Play Error: {e}")
                await _clear_(chat_id)
                try: await app.send_message(original_chat_id, "❌ Failed to switch stream.")
                except Exception: pass

StreamController = Call()
