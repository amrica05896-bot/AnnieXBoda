# Authored By Certified Coders © 2026
# System: Call Controller (Engineered for Custom PyTgCalls)
# Compatibility: Verified with Deep Scan Result

import asyncio
import os
import re
import traceback
import yt_dlp
from datetime import datetime, timedelta
from typing import Union

from ntgcalls import TelegramServerError, ConnectionNotFound
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup
from pyrogram.errors import FloodWait

# 🔥 الاستدعاءات الصحيحة بناءً على الفحص
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

# --- [1] Helper Functions ---

def clean_vidid(vid):
    if vid is None or vid is True or vid is False: 
        return None
    return str(vid)

def extract_video_id(url: str) -> Union[str, None]:
    if not url or not isinstance(url, str): return None
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

async def get_direct_link(videoid: str, video: bool = False):
    clean_id = clean_vidid(videoid)
    if not clean_id or len(clean_id) != 11: return None
    link = f"https://www.youtube.com/watch?v={clean_id}"
    fmt = "best[ext=mp4]/best" if video else "bestaudio/best"
    opts = {"format": fmt, "quiet": True, "no_warnings": True, "geo_bypass": True, "nocheckcertificate": True}
    try:
        loop = asyncio.get_running_loop()
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=False)
                return info.get("url")
        return await loop.run_in_executor(None, _extract)
    except:
        return link

# 🔥 الدالة الأهم: تم ضبطها على هيكل MediaStream اللي في مكتبتك
def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    if not path: path = ""
    path = str(path)
    is_url = path.startswith("http")
    
    # حماية من تشغيل الصوت كفيديو
    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")):
        video = False

    # إعدادات FFmpeg المحسنة (Titan Flags)
    base_flags = "-threads 4 -probesize 10M -analyzeduration 10M -fflags +genpts+igndts+nobuffer -sync ext"
    if is_url:
        titan_flags = f"{base_flags} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    else:
        titan_flags = base_flags

    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    # بناء الكائن بناءً على ملف types/stream/media_stream.py
    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH, 
        video_parameters=VideoQuality.HD_720p, 
        # مكتبتك بتستخدم Flags للتحكم في الصوت والفيديو
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=titan_flags,
    )

async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped: await auto_clean(popped)
    db[chat_id] = []
    await remove_active_video_chat(chat_id)
    await remove_active_chat(chat_id)
    await set_loop(chat_id, 0)

# --- [2] Call Controller ---

class Call:
    def __init__(self):
        self.userbot1 = userbot.one
        self.userbot2 = userbot.two
        self.userbot3 = userbot.three
        self.userbot4 = userbot.four
        self.userbot5 = userbot.five

        # ضبط الكاش على 100 لتفادي مشاكل SQLite
        self.one = PyTgCalls(self.userbot1, cache_duration=100)
        self.two = PyTgCalls(self.userbot2, cache_duration=100)
        self.three = PyTgCalls(self.userbot3, cache_duration=100)
        self.four = PyTgCalls(self.userbot4, cache_duration=100)
        self.five = PyTgCalls(self.userbot5, cache_duration=100)

        self.active_calls: set[int] = set()

    @capture_internal_err
    async def pause_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try: await assistant.resume(chat_id)
        except: await assistant.unmute(chat_id)

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
        try: await assistant.leave_call(chat_id)
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
        try: await assistant.leave_call(chat_id)
        except: pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        if not link:
            try:
                check = db.get(chat_id)
                if check: link = check[0]["file"]
            except: pass
            if not link: return

        final_link = link
        vid_id = extract_video_id(str(link))
        
        # Smart Audio/Video Switch
        if os.path.exists(str(link)) and video:
            if str(link).endswith((".mp3", ".m4a", ".flac", ".opus")):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=True)
                        if direct: final_link = direct
                    except: pass
        elif link and ("youtube" in str(link) or "googleusercontent" in str(link)):
             if vid_id: 
                 try:
                     direct = await get_direct_link(vid_id, video=bool(video))
                     if direct: final_link = direct
                 except: pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))
        
        # استخدام GroupCallConfig بناءً على ملف types/calls/group_call_config.py
        config = GroupCallConfig(auto_start=False)
        
        if chat_id in self.active_calls:
            try:
                await assistant.change_stream(chat_id, stream)
            except:
                try: await assistant.play(chat_id, stream, config=config)
                except: pass 
        else:
            await assistant.play(chat_id, stream, config=config)

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        ffmpeg_params = f"-ss {to_seek} -to {duration}"
        is_video = mode == "video"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ffmpeg_params)
        await assistant.change_stream(chat_id, stream)

    @capture_internal_err
    async def stream_call(self, link: str) -> None:
        assistant = await group_assistant(self, config.LOGGER_ID)
        stream = dynamic_media_stream(link)
        try:
            await assistant.play(config.LOGGER_ID, stream)
            await asyncio.sleep(8)
        except: pass
        finally:
            try: await assistant.leave_call(config.LOGGER_ID)
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
        lang = await get_lang(chat_id)
        _ = get_string(lang)
        
        final_link = link
        vid_id = extract_video_id(str(link))

        if os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a", ".flac", ".opus")):
             if vid_id:
                 try:
                     direct = await get_direct_link(vid_id, video=True)
                     if direct: final_link = direct
                 except: pass
        elif link and ("youtube" in str(link) or "googleusercontent" in str(link)):
            if vid_id: 
                try:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct: final_link = direct
                except: pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))
        config = GroupCallConfig(auto_start=False)

        if chat_id in self.active_calls:
            try:
                await assistant.change_stream(chat_id, stream)
                return 
            except: pass 

        try:
            await assistant.play(chat_id, stream, config=config)
        except NoActiveGroupCall:
            try:
                await assistant.create_group_call(chat_id)
                await assistant.play(chat_id, stream, config=config)
            except:
                raise AssistantErr(_["call_8"])
        except (NoAudioSourceFound, NoVideoSourceFound):
            raise AssistantErr(_["call_11"])
        except Exception as e:
            if "already joined" in str(e).lower():
                try: await assistant.change_stream(chat_id, stream)
                except: pass
            else:
                raise AssistantErr(f"Error: {e}")
                  
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
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        popped = None
        loop = await get_loop(chat_id)
        try:
            if loop == 0: popped = check.pop(0)
            else:
                loop = loop - 1
                await set_loop(chat_id, loop)
            await auto_clean(popped)
            if not check:
                await _clear_(chat_id)
                try: await client.leave_call(chat_id)
                except: pass
                finally: self.active_calls.discard(chat_id)
                return
        except:
            try:
                await _clear_(chat_id)
                return await client.leave_call(chat_id)
            except: return

        queued = check[0]["file"]
        title = (check[0]["title"]).title()
        user = check[0]["by"]
        original_chat_id = check[0]["chat_id"]
        streamtype = check[0]["streamtype"]
        videoid = clean_vidid(check[0]["vidid"])
        video = True if str(streamtype) == "video" else False
        
        if check[0].get("old_dur"):
            db[chat_id][0].update({"dur": check[0]["old_dur"], "seconds": check[0]["old_second"], "speed_path": None, "speed": 1.0})

        async def _play_stream(stream_obj):
            try:
                if chat_id in self.active_calls:
                    await client.change_stream(chat_id, stream_obj)
                else:
                    await client.play(chat_id, stream_obj, config=GroupCallConfig(auto_start=True))
            except Exception:
                try:
                    await client.leave_call(chat_id)
                    await asyncio.sleep(0.5)
                    await client.play(chat_id, stream_obj, config=GroupCallConfig(auto_start=True))
                except:
                    await _clear_(chat_id)
                    return await app.send_message(original_chat_id, text="❌ خطأ في التشغيل")

        final_link = queued
        vid_id = extract_video_id(str(queued)) or videoid 

        if os.path.exists(str(queued)) and video and str(queued).endswith((".mp3", ".m4a", ".flac", ".opus")):
             if vid_id:
                 try:
                     direct_url = await get_direct_link(vid_id, video=True)
                     if direct_url: final_link = direct_url
                 except: pass
        elif "live_" in queued or "vid_" in queued or "index_" in queued:
             if vid_id:
                 try:
                     direct_url = await get_direct_link(vid_id, video=video)
                     if direct_url: final_link = direct_url
                 except: pass

        stream = dynamic_media_stream(path=final_link, video=video)
        await _play_stream(stream)
        
        try:
            img = await get_thumb(videoid)
            button = stream_markup(get_string(await get_lang(chat_id)), chat_id)
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=f"🏷 **التالي:** [{title[:25]}](https://t.me/{app.username}?start=info_{videoid})\n⏱ **المدة:** {check[0]['dur']}\n👤 **بواسطة:** {user}",
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
        except: pass

    async def start(self) -> None:
        LOGGER(__name__).info("Starting Custom PyTgCalls...")
        if config.STRING1: await self.one.start()
        if config.STRING2: await self.two.start()
        if config.STRING3: await self.three.start()
        if config.STRING4: await self.four.start()
        if config.STRING5: await self.five.start()

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if config.STRING1: pings.append(self.one.ping)
        if config.STRING2: pings.append(self.two.ping)
        if config.STRING3: pings.append(self.three.ping)
        if config.STRING4: pings.append(self.four.ping)
        if config.STRING5: pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        @filters.stream_end(StreamEnded.Type.AUDIO)
        async def stream_end_handler(client, update):
            await self.play(client, update.chat_id)
        @filters.chat_update(ChatUpdate.Status.LEFT_CALL | ChatUpdate.Status.KICKED | ChatUpdate.Status.CLOSED_VOICE_CHAT)
        async def chat_update_handler(client, update):
            await self.stop_stream(update.chat_id)
        for assistant in assistants:
            assistant.on_update()(stream_end_handler)
            assistant.on_update()(chat_update_handler)

StreamController = Call()
