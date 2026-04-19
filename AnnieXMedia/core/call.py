import asyncio
import inspect
import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional
from asyncio import Lock

from pyrogram import enums, errors
from pyrogram.types import InlineKeyboardMarkup, InputMediaPhoto
from pyrogram.errors import ChatAdminRequired

from pytgcalls import PyTgCalls, filters
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality,
    Update,
    ChatUpdate,
    StreamEnded,
)
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NotInCallError,
    PyTgCallsAlreadyRunning,
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
from AnnieXMedia.utils.errors import capture_internal_err


class PyTgCallsErrorFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "UpdateGroupCall" in msg or "not found" in msg:
            return False
        return True

logging.getLogger("pyrogram.dispatcher").addFilter(PyTgCallsErrorFilter())

autoend = {}
counter = {}


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _build_stream(path: str, video: bool = False, ffmpeg_opts: str = "") -> MediaStream:
    """بناء الـ MediaStream الجديد كلياً المتوافق مع PyTgCalls V2"""
    path = str(path)
    base_flags = (
        "-threads 0 "
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-probesize 2M -analyzeduration 2M -rtbufsize 16M "
        "-fflags +genpts+igndts+fastseek -sync ext "
    )
    
    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.HD_720p,
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=base_flags + ffmpeg_opts,
    )


async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped:
        await auto_clean(popped)
    db[chat_id] = []
    try:
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except Exception:
        pass


class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        # Lazy Loading لعدم تعارض اللوبس
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

    # --- دوال التحكم المبنية على V2 API ---
    async def pause_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await _maybe_await(assistant.pause(chat_id)) # تم استبدال pause_stream بـ pause

    async def resume_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await _maybe_await(assistant.resume(chat_id)) # تم استبدال resume_stream بـ resume

    async def mute_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await _maybe_await(assistant.mute(chat_id)) # تم استبدال mute_stream بـ mute

    async def unmute_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await _maybe_await(assistant.unmute(chat_id)) # تم استبدال unmute_stream بـ unmute

    async def stop_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            await _clear_(chat_id)
            try:
                await _maybe_await(assistant.leave_call(chat_id)) # استبدال leave_group_call
            except Exception:
                pass
            finally:
                self.active_calls.discard(chat_id)

    async def force_stop_stream(self, chat_id: int) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            try:
                if db.get(chat_id): db.get(chat_id).pop(0)
                await remove_active_video_chat(chat_id)
                await remove_active_chat(chat_id)
            except Exception:
                pass

            await _clear_(chat_id)
            try:
                await _maybe_await(assistant.leave_call(chat_id))
            except Exception:
                pass
            finally:
                self.active_calls.discard(chat_id)

    async def seek_stream(self, chat_id: int, file_path: str, to_seek: int, duration: int, mode: str) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            stream = _build_stream(file_path, video=(mode == "video"), ffmpeg_opts=f"-ss {to_seek} ")
            await _maybe_await(assistant.play(chat_id, stream)) # الدالة الموحدة play()

    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: bool = False, image: str = None) -> None:
        async with self.get_lock(chat_id):
            assistant = await group_assistant(self, chat_id)
            lang = await get_lang(chat_id)
            _ = get_string(lang)

            try:
                chat = await app.get_chat(chat_id)
                if chat.type == enums.ChatType.CHANNEL:
                    mbr = await app.get_chat_member(chat_id, assistant.me.id)
                    if mbr.status == enums.ChatMemberStatus.BANNED:
                        raise AssistantErr("❌ Assistant is banned in this channel.")
            except Exception:
                pass

            stream = _build_stream(link, video=video)
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    await _maybe_await(assistant.play(chat_id, stream)) # الدالة الموحدة للتشغيل والدخول
                    break
                except (NoActiveGroupCall, ChatAdminRequired) as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    raise AssistantErr(_["call_8"])
                except Exception as e:
                    print("\n🚨🚨🚨 ERROR IN JOIN_CALL (PyTgCalls V2) 🚨🚨🚨")
                    traceback.print_exc()
                    if "not found" in str(e).lower() or "initialized" in str(e).lower():
                        if attempt < max_retries - 1:
                            try: await _maybe_await(assistant.leave_call(chat_id))
                            except: pass
                            await asyncio.sleep(1)
                            continue
                    raise AssistantErr(f"Error: {e}")

            self.active_calls.add(chat_id)
            await add_active_chat(chat_id)
            await music_on(chat_id)
            if video: await add_active_video_chat(chat_id)

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (NTgCalls Core v2.2.11)...")
        if self.userbot1: self.one = PyTgCalls(self.userbot1)
        if self.userbot2: self.two = PyTgCalls(self.userbot2)
        if self.userbot3: self.three = PyTgCalls(self.userbot3)
        if self.userbot4: self.four = PyTgCalls(self.userbot4)
        if self.userbot5: self.five = PyTgCalls(self.userbot5)

        for ast, enabled in ((self.one, config.STRING1), (self.two, config.STRING2), (self.three, config.STRING3)):
            if ast and enabled:
                try: await _maybe_await(ast.start())
                except PyTgCallsAlreadyRunning: pass

    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        def register_handlers(assistant):
            # نظام الـ V2 Events החדש
            @assistant.on_update(filters.stream_end())
            async def stream_end_handler(client: PyTgCalls, update: Update):
                if isinstance(update, StreamEnded):
                    chat_id = update.chat_id
                    curr_t = asyncio.get_running_loop().time()
                    if chat_id in self._stream_end_cache and (curr_t - self._stream_end_cache[chat_id] < 2.0):
                        return
                    self._stream_end_cache[chat_id] = curr_t
                    LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
                    await self.play(client, chat_id)

            @assistant.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
            async def left_call_handler(client: PyTgCalls, update: Update):
                await self.stop_stream(update.chat_id)

        for ast in assistants:
            register_handlers(ast)

    @capture_internal_err
    async def play(self, client: PyTgCalls, chat_id: int) -> None:
        """تشغيل الأغنية التالية في الطابور باستخدام V2 play()"""
        async with self.get_lock(chat_id):
            check = db.get(chat_id)
            if not check:
                return await _clear_(chat_id)

            loop = await get_loop(chat_id)
            try:
                if loop == 0:
                    popped = check.pop(0)
                    if popped: await auto_clean(popped)
                else:
                    await set_loop(chat_id, loop - 1)

                if not check:
                    await _clear_(chat_id)
                    try: await _maybe_await(client.leave_call(chat_id))
                    except: pass
                    self.active_calls.discard(chat_id)
                    return
            except Exception:
                await _clear_(chat_id)
                try: await _maybe_await(client.leave_call(chat_id))
                except: pass
                return

            queued = check[0].get("file")
            title = (check[0].get("title") or "").title()
            user = check[0].get("by")
            original_chat_id = check[0].get("chat_id")
            streamtype = check[0].get("streamtype")
            videoid = check[0].get("vidid")
            dur = check[0].get("dur")
            is_video = str(streamtype) == "video"

            final_link = queued
            if str(streamtype) == "youtube" or "vid_" in str(queued):
                try:
                    direct = await YouTube.get_direct_link(videoid, prefer_audio=not is_video)
                    if direct: final_link = direct
                except Exception as e:
                    LOGGER(__name__).error(f"Failed direct link: {e}")

            stream = _build_stream(final_link, video=is_video)

            try:
                # 🚀 الدالة السحرية play للتشغيل المباشر
                await _maybe_await(client.play(chat_id, stream))

                if is_video: await add_active_video_chat(chat_id)
                else: await remove_active_video_chat(chat_id)

                async def send_fast_message():
                    try:
                        img_url = f"https://i.ytimg.com/vi/{videoid}/hqdefault.jpg" if videoid else config.START_IMG_URL
                        from AnnieXMedia.utils.inline import stream_markup
                        btn = stream_markup(get_string(await get_lang(chat_id)), chat_id)
                        
                        if db[chat_id][0].get("mystic"):
                            await db[chat_id][0].get("mystic").delete()
                            
                        cap = get_string(await get_lang(chat_id))["stream_1"].format(
                            f"https://t.me/{app.username}?start=info_{videoid}", title[:23], dur, user
                        )
                        run = await app.send_photo(original_chat_id, photo=img_url, caption=cap, reply_markup=InlineKeyboardMarkup(btn))
                        if run:
                            db[chat_id][0]["mystic"] = run
                            db[chat_id][0]["markup"] = "stream"
                    except Exception as e:
                        LOGGER(__name__).error(f"Background photo err: {e}")

                asyncio.create_task(send_fast_message())

            except Exception as e:
                print("\n🚨🚨🚨 ERROR IN PLAY QUEUE 🚨🚨🚨")
                traceback.print_exc()
                await _clear_(chat_id)
                try: await app.send_message(original_chat_id, "❌ Failed to switch stream.")
                except: pass

StreamController = Call()
