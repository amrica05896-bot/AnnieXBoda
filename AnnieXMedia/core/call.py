# Authored By Certified Coders © 2026
# System: Call Controller (Final Fixed Version - No NameErrors)
# Fixes: NameError _TGCALLS, NameError _clear_, call_8 logic, Assistant Join

import asyncio
import os
import re
import traceback
import importlib
import logging
from datetime import datetime, timedelta
from random import randint
from typing import Union, Optional, Dict, Any

import yt_dlp
from pyrogram.raw import functions
from pyrogram.errors import ChatAdminRequired, UserAlreadyParticipant, UserNotParticipant, FloodWait
from pyrogram.types import InlineKeyboardMarkup

# -----------------------------------------------------------------------------
# 1. Dynamic Import & Compatibility Layer
# -----------------------------------------------------------------------------
TCALLS_BACKEND = "none"
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.exceptions import (
        NoActiveGroupCall,
        NoAudioSourceFound,
        NoVideoSourceFound,
        NotInCallError,
        PyTgCallsAlreadyRunning,
        PyTgCallsError,
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
    TCALLS_BACKEND = "pytgcalls"
except Exception:
    try:
        import ntgcalls as ntg
        PyTgCalls = getattr(ntg, "NTgCallsClient", object)
        NoActiveGroupCall = getattr(ntg, "NoActiveGroupCall", Exception)
        NoAudioSourceFound = getattr(ntg, "NoAudioSourceFound", Exception)
        NoVideoSourceFound = getattr(ntg, "NoVideoSourceFound", Exception)
        NotInCallError = getattr(ntg, "NotInCallError", Exception)
        PyTgCallsAlreadyRunning = getattr(ntg, "AlreadyRunning", Exception)
        PyTgCallsError = getattr(ntg, "NTgCallsError", Exception)
        
        AudioQuality = getattr(ntg, "AudioQuality", object)
        MediaStream = getattr(ntg, "MediaStream", object)
        VideoQuality = getattr(ntg, "VideoQuality", object)
        GroupCallConfig = getattr(ntg, "GroupCallConfig", object)
        ChatUpdate = getattr(ntg, "ChatUpdate", object)
        StreamEnded = getattr(ntg, "StreamEnded", object)
        Update = getattr(ntg, "Update", object)
        TCALLS_BACKEND = "ntgcalls"
    except Exception:
        # Fallback to prevent crash during import
        PyTgCalls = object
        NoActiveGroupCall = Exception
        NoAudioSourceFound = Exception
        NoVideoSourceFound = Exception
        NotInCallError = Exception
        PyTgCallsAlreadyRunning = Exception
        PyTgCallsError = Exception
        AudioQuality = object
        MediaStream = object
        VideoQuality = object
        GroupCallConfig = object
        ChatUpdate = object
        StreamEnded = object
        Update = object
        TCALLS_BACKEND = "none"

try:
    from ntgcalls import ConnectionNotFound, TelegramServerError
except ImportError:
    class ConnectionNotFound(Exception): pass
    class TelegramServerError(Exception): pass

# -----------------------------------------------------------------------------
# 2. Project Imports
# -----------------------------------------------------------------------------
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

# Global state for plugins
autoend: Dict[int, datetime] = {}
counter: Dict[int, dict] = {}

# -----------------------------------------------------------------------------
# 3. Helpers & FFmpeg Configuration
# -----------------------------------------------------------------------------

def clean_vidid(vid):
    if vid is None or vid is True or vid is False:
        return None
    return str(vid)

def extract_video_id(url: str) -> Union[str, None]:
    if not url or not isinstance(url, str):
        return None
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

async def get_direct_link(videoid: str, video: bool = False):
    clean_id = clean_vidid(videoid)
    if not clean_id or len(clean_id) != 11:
        return None
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
    except Exception:
        return link

async def _invalidate_direct_cache_for_vid(videoid: Optional[str]) -> None:
    if not videoid: return
    try:
        fn = getattr(YouTube, "invalidate_direct_cache", None)
        if callable(fn):
            maybe = fn(videoid)
            if asyncio.iscoroutine(maybe): await maybe
    except Exception: pass

def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: Optional[str] = None) -> Any:
    path = "" if path is None else str(path)
    is_url = path.startswith("http")

    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")):
        video = False

    common_flags = "-threads 2 -probesize 10M -analyzeduration 10M -fflags +genpts+igndts+nobuffer -sync ext"

    if is_url:
        titan_flags = f"{common_flags} -reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 -rtbufsize 10M"
    else:
        titan_flags = f"-re {common_flags}"

    if ffmpeg_params:
        titan_flags = f"{titan_flags} {ffmpeg_params}"

    try:
        audio_quality = getattr(AudioQuality, "STUDIO", getattr(AudioQuality, "HIGH", AudioQuality))
        video_quality = getattr(VideoQuality, "HD_720p", VideoQuality)
        
        MediaStreamFlags = getattr(MediaStream, "Flags", None)
        if MediaStreamFlags:
            v_flag = MediaStreamFlags.REQUIRED if video else MediaStreamFlags.IGNORE
            a_flag = MediaStreamFlags.REQUIRED
        else:
            v_flag = None
            a_flag = None

        if MediaStream is not object:
            return MediaStream(
                media_path=path,
                audio_parameters=audio_quality,
                video_parameters=video_quality,
                video_flags=v_flag,
                audio_flags=a_flag,
                ffmpeg_parameters=titan_flags,
            )
    except Exception:
        pass
    
    return {
        "media_path": path,
        "audio_parameters": audio_quality,
        "video_parameters": video_quality,
        "video": video,
        "ffmpeg": titan_flags,
    }

# ✅ دالة التنظيف (مهمة جداً لمنع خطأ NameError)
async def _clear_(chat_id: int) -> None:
    try:
        if popped := db.pop(chat_id, None):
            await auto_clean(popped)
        db[chat_id] = []
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except:
        pass

# -----------------------------------------------------------------------------
# 4. Call Controller Class
# -----------------------------------------------------------------------------
class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        # ✅ Fix: Use the globally defined PyTgCalls class, not a dictionary lookup
        PT = PyTgCalls if TCALLS_BACKEND != "none" else None
        
        self.one = PT(self.userbot1, cache_duration=100) if (PT and self.userbot1) else None
        self.two = PT(self.userbot2, cache_duration=100) if (PT and self.userbot2) else None
        self.three = PT(self.userbot3, cache_duration=100) if (PT and self.userbot3) else None
        self.four = PT(self.userbot4, cache_duration=100) if (PT and self.userbot4) else None
        self.five = PT(self.userbot5, cache_duration=100) if (PT and self.userbot5) else None

        self.active_calls: set[int] = set()

    async def _assistant_for_chat(self, chat_id: int):
        try:
            return await group_assistant(self, chat_id)
        except Exception:
            for client in [self.one, self.two, self.three, self.four, self.five]:
                if client: return client
            raise

    async def _play_safe(self, chat_id: int, stream_obj, force_join: bool = False):
        assistant = await self._assistant_for_chat(chat_id)
        try:
            cfg = GroupCallConfig(auto_start=force_join)
            await assistant.play(chat_id, stream_obj, config=cfg)
        except TypeError:
            await assistant.play(chat_id, stream_obj)

    @capture_internal_err
    async def pause_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        try:
            await assistant.resume(chat_id)
        except:
            await assistant.unmute(chat_id)

    @capture_internal_err
    async def mute_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        await assistant.mute(chat_id)

    @capture_internal_err
    async def unmute_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        await assistant.unmute(chat_id)

    @capture_internal_err
    async def stop_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except: pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def force_stop_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        try:
            check = db.get(chat_id)
            if check: check.pop(0)
        except: pass
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        # ✅ Fix: Ensure _clear_ is called correctly
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except: pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None):
        stream = dynamic_media_stream(path=link, video=bool(video))
        await self._play_safe(chat_id, stream, force_join=False)

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str):
        is_video = mode == "video"
        ff = f"-ss {to_seek} -to {duration}"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ff)
        assistant = await self._assistant_for_chat(chat_id)
        await assistant.play(chat_id, stream)

    @capture_internal_err
    async def speedup_stream(self, chat_id: int, file_path: str, speed: float, playing: list):
        if not playing: raise AssistantErr("Invalid stream info")
        assistant = await self._assistant_for_chat(chat_id)
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
        ff = f"-ss {played} -to {duration_min}"
        stream = dynamic_media_stream(path=out, video=is_video, ffmpeg_params=ff)
        await assistant.play(chat_id, stream)
        
        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            db[chat_id][0].update({
                "played": con_seconds, "dur": duration_min, "seconds": dur, "speed_path": out, "speed": speed
            })

    # --------------------------------------------------------------------------
    # 🔥 The Robust Join Logic
    # --------------------------------------------------------------------------
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await self._assistant_for_chat(chat_id)
        user_client = getattr(assistant, "app", getattr(assistant, "client", None))
        
        lang = await get_lang(chat_id)
        _ = get_string(lang)
        final_link = link
        vid_id = extract_video_id(str(link)) if link else None
        await _invalidate_direct_cache_for_vid(vid_id)

        try:
            if link and os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a")):
                if vid_id:
                    direct = await get_direct_link(vid_id, video=True)
                    if direct: final_link = direct
            elif link and ("youtube" in str(link) or "http" in str(link)):
                if vid_id:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct: final_link = direct
        except: pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))

        if chat_id in self.active_calls:
            try:
                await self._play_safe(chat_id, stream, force_join=False)
                return
            except: pass

        retries = 3
        for attempt in range(retries):
            try:
                await self._play_safe(chat_id, stream, force_join=True)
                
                await asyncio.sleep(1.2)
                try:
                    await assistant.mute(chat_id)
                    await asyncio.sleep(0.1)
                    await assistant.unmute(chat_id)
                except: pass
                
                # Check if joined successfully
                try:
                    parts = await assistant.get_participants(chat_id)
                    if not parts: raise NoActiveGroupCall
                except: pass

                break 

            except Exception as e:
                err_str = str(e).lower()
                
                # 🛑 FIX: Identify Permission/Call Errors & Prioritize call_8
                is_permission_error = (
                    isinstance(e, ChatAdminRequired) 
                    or "chat_admin_required" in err_str 
                    or "groupcall_forbidden" in err_str
                    or isinstance(e, NoActiveGroupCall) 
                    or "noactivegroupcall" in err_str
                    or "group call not found" in err_str
                )

                if is_permission_error:
                    if user_client:
                        try:
                            await user_client.invoke(
                                functions.phone.CreateGroupCall(
                                    peer=await user_client.resolve_peer(chat_id),
                                    random_id=randint(100000, 999999)
                                )
                            )
                            await asyncio.sleep(2.5)
                            continue 
                        except Exception:
                            raise AssistantErr(_["call_8"])
                    else:
                        raise AssistantErr(_["call_8"])

                if attempt == retries - 1:
                    if isinstance(e, (NoAudioSourceFound, NoVideoSourceFound)):
                        raise AssistantErr(_["call_11"])
                    
                    # 🔥 FIX: Double check msg for call_8 keywords before defaulting to call_10
                    if "admin" in err_str or "forbidden" in err_str or "found" in err_str:
                        raise AssistantErr(_["call_8"])
                        
                    raise AssistantErr(_["call_10"])
                
                await asyncio.sleep(1)

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
        LOGGER(__name__).info(f"Starting Call Clients... (Backend: {TCALLS_BACKEND})")
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
        
        Status = getattr(ChatUpdate, "Status", None)
        CRITICAL = 0
        if Status:
            CRITICAL = (getattr(Status, "KICKED", 0) | getattr(Status, "LEFT_GROUP", 0) | getattr(Status, "CLOSED_VOICE_CHAT", 0))

        async def unified_update_handler(client, update: Update) -> None:
            try:
                if isinstance(update, StreamEnded):
                    try:
                        assistant = await group_assistant(self, update.chat_id)
                        await self.play(assistant, update.chat_id)
                    except: pass
                elif isinstance(update, ChatUpdate):
                    status = getattr(update, "status", 0)
                    LEFT_CALL = getattr(Status, "LEFT_CALL", 0) if Status else 0
                    if (status & LEFT_CALL) or (status & CRITICAL):
                        await self.stop_stream(update.chat_id)
            except: pass

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

        queued = check[0].get("file")
        videoid = clean_vidid(check[0].get("vidid"))
        language = await get_lang(chat_id)
        _ = get_string(language)
        title = (check[0].get("title") or "").title()
        user = check[0].get("by")
        original_chat_id = check[0].get("chat_id")
        streamtype = check[0].get("streamtype")
        
        db[chat_id][0]["played"] = 0
        if check[0].get("old_dur"):
            db[chat_id][0]["dur"] = check[0].get("old_dur")
            db[chat_id][0]["seconds"] = check[0].get("old_second")
            db[chat_id][0]["speed_path"] = None
            db[chat_id][0]["speed"] = 1.0

        is_video = str(streamtype) == "video"

        try:
            final_link = queued
            vid_id = extract_video_id(str(queued)) or videoid
            await _invalidate_direct_cache_for_vid(vid_id)

            if queued and os.path.exists(str(queued)) and is_video and str(queued).endswith((".mp3", ".m4a")):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=True)
                        if direct: final_link = direct
                    except: pass
            
            if queued and ("live_" in str(queued) or "vid_" in str(queued) or "index_" in str(queued)):
                try:
                    if vid_id:
                        direct_url = await get_direct_link(vid_id, video=is_video)
                        if direct_url: final_link = direct_url
                        else:
                            path, direct = await YouTube.download(vid_id, None, video=is_video, videoid=vid_id)
                            if path: final_link = path
                except: pass

            stream = dynamic_media_stream(path=final_link, video=is_video)
            
            try:
                await self._play_safe(chat_id, stream, force_join=True)
            except Exception:
                try:
                    await client.leave_call(chat_id)
                    await asyncio.sleep(0.5)
                    await self._play_safe(chat_id, stream, force_join=True)
                except: pass

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
        except Exception as e:
            LOGGER(__name__).error(f"PLAY ERROR Chat: {chat_id} | {traceback.format_exc()}")
            await _clear_(chat_id)
            try: await client.leave_call(chat_id)
            except: pass
            return await app.send_message(original_chat_id, text=_["call_6"])

# Instantiate
StreamController = Call()
__all__ = ["StreamController", "Call", "autoend", "counter"]
