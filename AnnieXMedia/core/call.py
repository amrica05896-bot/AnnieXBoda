# Authored By Certified Coders © 2026
# System: Call Controller (Hybrid: Modern Structure + Legacy Join Logic)
# Fixes: Instant Leave (Added -re), Ghost Join

import asyncio
import os
import traceback
from datetime import datetime, timedelta
from typing import Union

from pyrogram.errors import ChatAdminRequired, UserNotParticipant, NoActiveGroupCall
from pyrogram.types import InlineKeyboardMarkup
from pyrogram.raw import functions
from random import randint

# استيراد المكتبة (كما في الكود القديم)
from pytgcalls import PyTgCalls
from pytgcalls.exceptions import (
    NoAudioSourceFound,
    NoVideoSourceFound,
    NotInCallError,
    PyTgCallsAlreadyRunning
)
from pytgcalls.types import (
    AudioQuality,
    ChatUpdate,
    MediaStream,
    StreamEnded,
    Update,
    VideoQuality,
    GroupCallConfig,
)

# محاولة استيراد أخطاء ntgcalls لو موجودة
try:
    from ntgcalls import ConnectionNotFound, TelegramServerError
except ImportError:
    class ConnectionNotFound(Exception): pass
    class TelegramServerError(Exception): pass

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
from AnnieXMedia.utils.inline.play import stream_markup
from AnnieXMedia.utils.formatters import check_duration, seconds_to_min, speed_converter
import yt_dlp

autoend = {}
counter = {}

# -----------------------------------------------------------------------------
# 1. إعدادات البث (منطق الكود القديم + حل الخروج الفوري)
# -----------------------------------------------------------------------------
def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    path = str(path)
    is_url = path.startswith("http")
    
    # 🔥 الإضافة الوحيدة هنا هي -re للملفات المحلية لمنع الخروج
    # باقي الإعدادات مطابقة للكود القديم
    titan_flags = "-threads 2 -ac 2 -probesize 10M -analyzeduration 10M"
    
    if is_url:
        titan_flags += " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    else:
        # هذا هو السطر الذي يمنع الخروج في نفس الثانية
        titan_flags = f"-re {titan_flags}"
    
    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    video_flags = MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE
    audio_flags = MediaStream.Flags.REQUIRED

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.STUDIO,
        video_parameters=VideoQuality.HD_720p, 
        audio_flags=audio_flags,
        video_flags=video_flags,
        ffmpeg_parameters=titan_flags,
    )

async def _clear_(chat_id: int) -> None:
    try:
        if popped := db.pop(chat_id, None):
            await auto_clean(popped)
        db[chat_id] = []
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except: pass

# -----------------------------------------------------------------------------
# 2. الكنترول (بمنطق الكود القديم)
# -----------------------------------------------------------------------------
class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        self.one = PyTgCalls(self.userbot1, cache_duration=100) if self.userbot1 else None
        self.two = PyTgCalls(self.userbot2, cache_duration=100) if self.userbot2 else None
        self.three = PyTgCalls(self.userbot3, cache_duration=100) if self.userbot3 else None
        self.four = PyTgCalls(self.userbot4, cache_duration=100) if self.userbot4 else None
        self.five = PyTgCalls(self.userbot5, cache_duration=100) if self.userbot5 else None

        self.active_calls: set[int] = set()

    # --- نفس دوال الكود القديم للتحكم ---
    @capture_internal_err
    async def pause_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        try: await assistant.resume(chat_id)
        except: await assistant.unmute(chat_id)

    @capture_internal_err
    async def mute_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.mute(chat_id)

    @capture_internal_err
    async def unmute_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await assistant.unmute(chat_id)

    @capture_internal_err
    async def stop_stream(self, chat_id: int):
        assistant = await group_assistant(self, chat_id)
        await _clear_(chat_id)
        try: await assistant.leave_call(chat_id)
        except: pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def force_stop_stream(self, chat_id: int):
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
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None):
        assistant = await group_assistant(self, chat_id)
        # نفس منطق القديم: auto_start=False
        ksk = GroupCallConfig(auto_start=False)
        stream = dynamic_media_stream(path=link, video=bool(video))
        await assistant.play(chat_id, stream, config=ksk)

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str):
        assistant = await group_assistant(self, chat_id)
        stream = dynamic_media_stream(path=file_path, video=(mode=="video"), ffmpeg_params=f"-ss {to_seek} -to {duration}")
        await assistant.play(chat_id, stream)

    @capture_internal_err
    async def speedup_stream(self, chat_id: int, file_path: str, speed: float, playing: list):
        if not playing: raise AssistantErr("Invalid stream info")
        assistant = await group_assistant(self, chat_id)
        base = os.path.basename(file_path)
        chatdir = os.path.join("playback", str(speed))
        os.makedirs(chatdir, exist_ok=True)
        out = os.path.join(chatdir, base)
        if not os.path.exists(out):
            vs = str(2.0 / float(speed))
            cmd = f'ffmpeg -i "{file_path}" -filter:v "setpts={vs}*PTS" -filter:a atempo={speed} -y "{out}"'
            proc = await asyncio.create_subprocess_shell(cmd, stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
        dur = int(await asyncio.get_event_loop().run_in_executor(None, check_duration, out))
        played, con_seconds = speed_converter(playing[0].get("played", 0), speed)
        duration_min = seconds_to_min(dur)
        is_video = playing[0].get("streamtype") == "video"
        
        stream = dynamic_media_stream(path=out, video=is_video, ffmpeg_params=f"-ss {played} -to {duration_min}")
        await assistant.play(chat_id, stream)
        
        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            db[chat_id][0].update({
                "played": con_seconds, "dur": duration_min, "seconds": dur, "speed_path": out, "speed": speed
            })

    # --------------------------------------------------------------------------
    # 🔥🔥🔥 أهم دالة: Join Call (نسخ لصق من القديم مع تحسين الإنشاء) 🔥🔥🔥
    # --------------------------------------------------------------------------
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
        
        # 1. تجهيز الاستريم
        stream = dynamic_media_stream(path=link, video=bool(video))
        
        # 2. الكونفج من الكود القديم
        ksk = GroupCallConfig(auto_start=False)

        try:
            # 3. محاولة الدخول (زي القديم بالظبط)
            await assistant.play(chat_id, stream, config=ksk)
            
        except NoActiveGroupCall:
            # 🔥 هنا الإضافة: لو مفيش كول، ننشئه يدوياً بدل ما نبعت رسالة خطأ
            # لأن المستخدمين بيشتكوا إن المساعد مش بيدخل
            try:
                user_client = getattr(assistant, "app", getattr(assistant, "client", None))
                if user_client:
                    await user_client.invoke(
                        functions.phone.CreateGroupCall(
                            peer=await user_client.resolve_peer(chat_id),
                            random_id=randint(10000, 99999)
                        )
                    )
                    await asyncio.sleep(2) # انتظار تيليجرام
                    await assistant.play(chat_id, stream, config=ksk)
                else:
                    raise AssistantErr(_["call_8"])
            except Exception:
                raise AssistantErr(_["call_8"])

        except (NoAudioSourceFound, NoVideoSourceFound):
            raise AssistantErr(_["call_11"])
        except (ConnectionNotFound, TelegramServerError):
            raise AssistantErr(_["call_10"])
        except Exception as e:
            # محاولة أخيرة (Retry)
            try:
                 await assistant.leave_call(chat_id)
                 await asyncio.sleep(1)
                 await assistant.play(chat_id, stream, config=ksk)
            except:
                 raise AssistantErr(f"ᴜɴᴀʙʟᴇ ᴛᴏ ᴊᴏɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴄᴀʟʟ.\nRᴇᴀsᴏɴ: {e}")
                 
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

    async def start(self) -> None:
        LOGGER(__name__).info("Starting Call Clients...")
        clients = [self.one, self.two, self.three, self.four, self.five]
        for c in clients:
            if c:
                try: await c.start()
                except Exception as e: LOGGER(__name__).error(f"Failed to start client: {e}")

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        clients = [self.one, self.two, self.three, self.four, self.five]
        for c in clients:
            if c:
                try: pings.append(c.ping)
                except: pass
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    @capture_internal_err
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        CRITICAL = (ChatUpdate.Status.KICKED | ChatUpdate.Status.LEFT_GROUP | ChatUpdate.Status.CLOSED_VOICE_CHAT)

        async def unified_update_handler(client, update: Update) -> None:
            if isinstance(update, StreamEnded):
                try:
                    assistant = await group_assistant(self, update.chat_id)
                    await self.play(assistant, update.chat_id)
                except: pass
            
            elif isinstance(update, ChatUpdate):
                status = update.status
                if (status & ChatUpdate.Status.LEFT_CALL) or (status & CRITICAL):
                    await self.stop_stream(update.chat_id)

        for assistant in assistants:
            try: assistant.on_update()(unified_update_handler)
            except: pass

    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        if not check:
            await _clear_(chat_id)
            try: await client.leave_call(chat_id)
            except: pass
            return

        loop = await get_loop(chat_id)
        try:
            if loop == 0: popped = check.pop(0)
            else:
                loop -= 1
                await set_loop(chat_id, loop)
            await auto_clean(popped)
            if not check:
                await _clear_(chat_id)
                try: await client.leave_call(chat_id)
                except: pass
                finally: self.active_calls.discard(chat_id)
                return
        except:
            try: await _clear_(chat_id); return await client.leave_call(chat_id)
            except: return

        queued = check[0]["file"]
        videoid = check[0]["vidid"]
        language = await get_lang(chat_id)
        _ = get_string(language)
        title = (check[0]["title"]).title()
        user = check[0]["by"]
        original_chat_id = check[0]["chat_id"]
        streamtype = check[0]["streamtype"]
        
        db[chat_id][0]["played"] = 0
        if check[0].get("old_dur"):
            db[chat_id][0]["dur"] = check[0].get("old_dur")
            db[chat_id][0]["seconds"] = check[0].get("old_second")
            db[chat_id][0]["speed_path"] = None
            db[chat_id][0]["speed"] = 1.0

        is_video = str(streamtype) == "video"

        # Helper to resolve links
        async def resolve_link(vid, vid_id_val):
            if not vid: return None
            try:
                # Direct link logic
                link = f"https://www.youtube.com/watch?v={vid_id_val}"
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio/best"
                opts = {"format": fmt, "quiet": True, "nocheckcertificate": True}
                loop_run = asyncio.get_running_loop()
                return await loop_run.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(link, download=False).get("url"))
            except: return vid

        # Determine Stream Path
        final_stream_path = queued
        # Try resolving if it's a youtube ID and local file doesn't exist
        if not os.path.exists(str(queued)) and videoid:
             res = await resolve_link(queued, videoid)
             if res: final_stream_path = res

        stream = dynamic_media_stream(path=final_stream_path, video=is_video)
        
        try:
            await client.play(chat_id, stream)
        except Exception:
            try:
                await client.leave_call(chat_id)
                await asyncio.sleep(0.5)
                await client.play(chat_id, stream)
            except:
                return await app.send_message(original_chat_id, text=_["call_6"])

        if is_video: await add_active_video_chat(chat_id)
        else: await remove_active_video_chat(chat_id)

        img = await get_thumb(videoid)
        button = stream_markup(_, chat_id)
        try:
            if db[chat_id][0].get("mystic"): await db[chat_id][0].get("mystic").delete()
        except: pass
        
        run = await app.send_photo(
            chat_id=original_chat_id,
            photo=img,
            caption=_["stream_1"].format(f"https://t.me/{app.username}?start=info_{videoid}", title[:23], check[0].get("dur"), user),
            reply_markup=InlineKeyboardMarkup(button),
        )
        db[chat_id][0]["mystic"] = run
        db[chat_id][0]["markup"] = "stream"

# Instantiate
StreamController = Call()
__all__ = ["StreamController", "Call", "autoend", "counter"]
