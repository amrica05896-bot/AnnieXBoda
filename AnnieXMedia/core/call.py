# Authored By Certified Coders © 2026
# System: Call Controller (Clean Native - No Manual Mute/Unmute)
# Strategy: Trusting Library Internal Logic with auto_start=False

import asyncio
import os
import re
import traceback
from datetime import datetime, timedelta
from typing import Union, Optional

import yt_dlp
from pyrogram.errors import ChatAdminRequired, UserAlreadyParticipant, UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup

from pytgcalls import PyTgCalls
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NoAudioSourceFound,
    NoVideoSourceFound,
    NotInCallError,
    PyTgCallsAlreadyRunning,
    PyTgCallsError
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

autoend = {}
counter = {}

# ===============================
# Helpers & FFmpeg Logic
# ===============================

def clean_vidid(vid):
    if vid is None or vid is True or vid is False: return None
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
    except: return link

def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    if not path: path = ""
    path = str(path)
    is_url = path.startswith("http")
    
    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")): 
        video = False

    # ==============================================================================
    # 🔥 STABLE FLAGS (Standard Buffer)
    # ==============================================================================
    
    if is_url:
        titan_flags = (
            "-threads 2 "
            "-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 "
            "-probesize 1M -analyzeduration 2M "
            "-fflags +genpts+igndts+nobuffer -sync ext"
        )
    else:
        # Local File
        titan_flags = (
            "-re -threads 2 "
            "-probesize 1M -analyzeduration 2M "
            "-fflags +genpts+igndts "
            "-sync ext -ss 0"
        )
    
    if ffmpeg_params: titan_flags += f" {ffmpeg_params}"

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH, 
        video_parameters=VideoQuality.HD_720p,
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

async def _invalidate_direct_cache_for_vid(videoid: Optional[str]) -> None:
    if not videoid: return
    try:
        fn = getattr(YouTube, "invalidate_direct_cache", None)
        if callable(fn):
            maybe = fn(videoid)
            if asyncio.iscoroutine(maybe): await maybe
    except: pass

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

    async def _send_log(self, text: str):
        print(f"[CALL LOG] {text}")
        if not config.LOGGER_ID: return
        try:
            await app.send_message(config.LOGGER_ID, text, disable_web_page_preview=True)
        except: pass

    async def _play_safe(self, chat_id, stream, force_join=False):
        assistant = await group_assistant(self, chat_id)
        config = GroupCallConfig(auto_start=False)
        await assistant.play(chat_id, stream, config=config)

    @capture_internal_err
    async def pause_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)
        await self._send_log(f"⏸️ **Paused**: `{chat_id}`")

    @capture_internal_err
    async def resume_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try: await assistant.resume(chat_id)
        except: await assistant.unmute(chat_id)
        await self._send_log(f"▶️ **Resumed**: `{chat_id}`")

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
            await self._send_log(f"⏹️ **Stopped**: `{chat_id}`")
        except: pass
        finally: self.active_calls.discard(chat_id)

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
            await self._send_log(f"⛔ **Force Stopped**: `{chat_id}`")
        except: pass
        finally: self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        if not link:
            try:
                check = db.get(chat_id)
                if check: link = check[0].get("file")
            except: pass
            if not link: return

        final_link = link
        vid_id = extract_video_id(str(link))
        await _invalidate_direct_cache_for_vid(vid_id)

        if os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a")):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=True)
                    if direct: final_link = direct
                except: pass
        elif link and ("youtube" in str(link) or "http" in str(link)):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct: final_link = direct
                except: pass

        new_is_video = bool(video)
        old_is_video = False
        try:
            check = db.get(chat_id)
            if check: old_is_video = str(check[0].get("streamtype")) == "video"
        except: pass

        stream = dynamic_media_stream(path=final_link, video=new_is_video)
        assistant = await group_assistant(self, chat_id)

        if chat_id in self.active_calls:
            try:
                if old_is_video != new_is_video:
                    try: await assistant.leave_call(chat_id)
                    except: pass
                    await self._play_safe(chat_id, stream, force_join=True)
                else:
                    await self._play_safe(chat_id, stream, force_join=False)
                await self._send_log(f"⏭️ **Skipped**: `{chat_id}`")
            except (NoActiveGroupCall, NotInCallError):
                await self._play_safe(chat_id, stream, force_join=True)
            except Exception as e:
                await self._send_log(f"⚠️ **Skip Error**: {e}")
                try: await self.stop_stream(chat_id)
                except: pass
                await asyncio.sleep(0.2)
                await self._play_safe(chat_id, stream, force_join=True)
        else:
            await self._play_safe(chat_id, stream, force_join=True)
            
        if new_is_video:
            await add_active_video_chat(chat_id)
        else:
            await remove_active_video_chat(chat_id)

    @capture_internal_err
    async def vc_users(self, chat_id: int) -> list:
        assistant = await group_assistant(self, chat_id)
        try:
            participants = await assistant.get_participants(chat_id)
            return [p.user_id for p in participants if not getattr(p, "is_muted", False)]
        except: return []

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str) -> None:
        ffmpeg_params = f"-ss {to_seek} -to {duration}"
        is_video = mode == "video"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ffmpeg_params)
        await self._play_safe(chat_id, stream, force_join=False)
        await self._send_log(f"⏩ **Seeked**: `{chat_id}`")

    @capture_internal_err
    async def speedup_stream(self, chat_id: int, file_path: str, speed: float, playing: list) -> None:
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
        ffmpeg_params = f"-ss {played} -to {duration_min}"
        stream = dynamic_media_stream(path=out, video=is_video, ffmpeg_params=ffmpeg_params)
        
        await self._play_safe(chat_id, stream, force_join=False)
        await self._send_log(f"⚡ **Speed ({speed}x)**: `{chat_id}`")
        
        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            db[chat_id][0].update({"played": con_seconds, "dur": duration_min, "seconds": dur, "speed_path": out, "speed": speed})

    # ==========================================================
    # 🔥 JOIN LOGIC: No Manual Unmute (Clean)
    # ==========================================================
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        lang = await get_lang(chat_id)
        _ = get_string(lang)

        final_link = link
        vid_id = extract_video_id(str(link)) if link else None
        await _invalidate_direct_cache_for_vid(vid_id)

        if link and os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a")):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=True)
                    if direct: final_link = direct
                except: pass
        elif link and ("youtube" in str(link) or "http" in str(link)):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct: final_link = direct
                except: pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))

        if chat_id in self.active_calls:
            try:
                await self._play_safe(chat_id, stream, force_join=False)
                return
            except Exception:
                pass

        retries = 3
        for attempt in range(retries):
            try:
                await self._play_safe(chat_id, stream, force_join=True)
                await self._send_log(f"✅ **Assistant Joined**: `{chat_id}`")
                # 🔥 No manual Mute/Unmute here. Letting the library handle it.
                break 
            except Exception as e:
                err_str = str(e).lower()
                
                if (isinstance(e, (NoActiveGroupCall, ChatAdminRequired)) 
                    or "chat_admin_required" in err_str 
                    or "noactivegroupcall" in err_str 
                    or "group call not found" in err_str):
                    
                    await self._send_log(f"⚠️ **Join Fail (No Call)**: `{chat_id}`")
                    raise AssistantErr(_["call_8"])

                if attempt == retries - 1:
                    await self._send_log(f"❌ **FATAL Join Error**: `{chat_id}`\n{e}")
                    if isinstance(e, (NoAudioSourceFound, NoVideoSourceFound)):
                        raise AssistantErr(_["call_11"])
                    elif isinstance(e, (ConnectionNotFound, TelegramServerError)):
                        raise AssistantErr(_["call_10"])
                    
                    if isinstance(e, PyTgCallsAlreadyRunning) or "already joined" in err_str:
                        try:
                            await self._play_safe(chat_id, stream, force_join=False)
                            break
                        except: pass
                    else:
                        raise AssistantErr(f"Error: {e}")
                
                await asyncio.sleep(1)
                continue

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
    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients...")
        if self.one and config.STRING1: await self.one.start()
        if self.two and config.STRING2: await self.two.start()
        if self.three and config.STRING3: await self.three.start()
        if self.four and config.STRING4: await self.four.start()
        if self.five and config.STRING5: await self.five.start()

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if self.one and config.STRING1: pings.append(self.one.ping)
        if self.two and config.STRING2: pings.append(self.two.ping)
        if self.three and config.STRING3: pings.append(self.three.ping)
        if self.four and config.STRING4: pings.append(self.four.ping)
        if self.five and config.STRING5: pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    @capture_internal_err
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        
        async def unified_update_handler(client, update: Update) -> None:
            if isinstance(update, StreamEnded):
                if update.stream_type == StreamEnded.Type.AUDIO:
                    chat_id = update.chat_id
                    await self._send_log(f"🔄 **Auto Next**: `{chat_id}`")
                    assistant = await group_assistant(self, chat_id)
                    await self.play(assistant, chat_id)
            
            elif isinstance(update, ChatUpdate):
                chat_id = update.chat_id
                status = update.status
                
                if status & ChatUpdate.Status.LEFT_CALL:
                    await self._send_log(f"🚪 **Left Call**: `{chat_id}`")
                    await self.stop_stream(chat_id)
                elif status & ChatUpdate.Status.KICKED:
                    await self._send_log(f"🚫 **Kicked**: `{chat_id}`")
                    await self.stop_stream(chat_id)
                elif status & ChatUpdate.Status.CLOSED_VOICE_CHAT:
                    await self._send_log(f"🛑 **VC Closed**: `{chat_id}`")
                    await self.stop_stream(chat_id)

        for assistant in assistants:
            try: assistant.on_update()(unified_update_handler)
            except: pass

    # --- Queue Handler (Auto Play Next) ---
    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        if not check:
            await _clear_(chat_id)
            try: await client.leave_call(chat_id)
            except: pass
            return
        
        old_is_video = False
        try:
            if len(check) > 0:
                old_is_video = str(check[0].get("streamtype")) == "video"
        except: pass

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
            try: await _clear_(chat_id); return await client.leave_call(chat_id)
            except: return
        else:
            queued = check[0].get("file")
            language = await get_lang(chat_id)
            _ = get_string(language)
            title = (check[0].get("title") or "").title()
            user = check[0].get("by")
            original_chat_id = check[0].get("chat_id")
            streamtype = check[0].get("streamtype")
            videoid = clean_vidid(check[0].get("vidid"))
            
            db[chat_id][0]["played"] = 0
            if (check[0]).get("old_dur"):
                db[chat_id][0]["dur"] = check[0].get("old_dur")
                db[chat_id][0]["seconds"] = check[0].get("old_second")
                db[chat_id][0]["speed_path"] = None
                db[chat_id][0]["speed"] = 1.0
            
            new_is_video = True if str(streamtype) == "video" else False
            
            try:
                final_link = queued
                vid_id = extract_video_id(str(queued)) or videoid
                await _invalidate_direct_cache_for_vid(vid_id)
                if queued and os.path.exists(str(queued)) and new_is_video and str(queued).endswith((".mp3", ".m4a")):
                     if vid_id:
                        try:
                            direct = await get_direct_link(vid_id, video=True)
                            if direct: final_link = direct
                        except: pass
                if queued and ("live_" in str(queued) or "vid_" in str(queued) or "index_" in str(queued)):
                    try:
                        if vid_id:
                            direct_url = await get_direct_link(vid_id, video=new_is_video)
                            if direct_url: final_link = direct_url
                            else:
                                path, direct = await YouTube.download(vid_id, None, video=new_is_video, videoid=vid_id)
                                if path: final_link = path
                    except: pass
                
                stream = dynamic_media_stream(path=final_link, video=new_is_video)
                
                if old_is_video != new_is_video:
                    try: await client.leave_call(chat_id)
                    except: pass
                    await self._play_safe(chat_id, stream, force_join=True)
                else:
                    if chat_id in self.active_calls:
                        try:
                            await self._play_safe(chat_id, stream, force_join=False)
                        except (NoActiveGroupCall, NotInCallError):
                            await self._play_safe(chat_id, stream, force_join=True)
                    else:
                        await self._play_safe(chat_id, stream, force_join=True)

                if new_is_video: await add_active_video_chat(chat_id)
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
                
                # 🔥 Log New Song Playing
                await self._send_log(f"🎵 **Playing Next**: `{chat_id}`\nTitle: {title}")

            except Exception as e:
                LOGGER(__name__).error(f"💣 [PLAY ERROR] Chat: {chat_id}\n{traceback.format_exc()}")
                await self._send_log(f"❌ **Play Error**: `{chat_id}`\n{e}")
                await _clear_(chat_id)
                try: await client.leave_call(chat_id)
                except: pass
                return await app.send_message(original_chat_id, text=_["call_6"])

StreamController = Call()
