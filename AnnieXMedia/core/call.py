# AnnieXMedia/core/call.py
# Authored By Certified Coders © 2026 (Rebuilt & Hardened for pytgcalls 2.2.11 compatibility)
# Purpose: Unified call controller (PyTgCalls primary, ntgcalls fallback)
# Exports: StreamController, autoend, counter

import asyncio
import os
import sys
import traceback
import importlib
import logging
from datetime import datetime, timedelta
from random import randint
from typing import Optional, Union, Dict, Any

# try to detect version and import compatible names
def _import_tgcalls():
    """
    Try to import pytgcalls and friends. Return dict of found symbols.
    """
    symbols = {}
    try:
        import pytgcalls
        from pytgcalls import PyTgCalls
        from pytgcalls import __version__ as _ptver
        # try to import typical exceptions & types
        try:
            from pytgcalls.exceptions import (
                NoActiveGroupCall,
                NoAudioSourceFound,
                NoVideoSourceFound,
                NotInCallError,
                PyTgCallsAlreadyRunning,
                PyTgCallsError,
            )
        except Exception:
            # not fatal, provide generic placeholders
            NoActiveGroupCall = type("NoActiveGroupCall", (Exception,), {})
            NoAudioSourceFound = type("NoAudioSourceFound", (Exception,), {})
            NoVideoSourceFound = type("NoVideoSourceFound", (Exception,), {})
            NotInCallError = type("NotInCallError", (Exception,), {})
            PyTgCallsAlreadyRunning = type("PyTgCallsAlreadyRunning", (Exception,), {})
            PyTgCallsError = type("PyTgCallsError", (Exception,), {})
        try:
            from pytgcalls.types import (
                MediaStream,
                GroupCallConfig,
                AudioQuality,
                VideoQuality,
                ChatUpdate,
                StreamEnded,
                Update,
            )
        except Exception:
            # minimal placeholders to avoid crashes at import time (not full functionality)
            MediaStream = getattr(pytgcalls, "MediaStream", object)
            GroupCallConfig = getattr(pytgcalls, "GroupCallConfig", lambda auto_start: None)
            AudioQuality = getattr(pytgcalls, "AudioQuality", object)
            VideoQuality = getattr(pytgcalls, "VideoQuality", object)
            ChatUpdate = getattr(pytgcalls, "ChatUpdate", object)
            StreamEnded = getattr(pytgcalls, "StreamEnded", object)
            Update = getattr(pytgcalls, "Update", object)

        symbols.update({
            "backend": "pytgcalls",
            "PyTgCalls": PyTgCalls,
            "MediaStream": MediaStream,
            "GroupCallConfig": GroupCallConfig,
            "AudioQuality": AudioQuality,
            "VideoQuality": VideoQuality,
            "ChatUpdate": ChatUpdate,
            "StreamEnded": StreamEnded,
            "Update": Update,
            "NoActiveGroupCall": NoActiveGroupCall,
            "NoAudioSourceFound": NoAudioSourceFound,
            "NoVideoSourceFound": NoVideoSourceFound,
            "NotInCallError": NotInCallError,
            "PyTgCallsAlreadyRunning": PyTgCallsAlreadyRunning,
            "PyTgCallsError": PyTgCallsError,
            "version": getattr(_ptver, "__str__", lambda: str(_ptver))(),
        })
        return symbols
    except Exception:
        # fallback to ntgcalls if available
        try:
            import ntgcalls
            from ntgcalls import NTgCalls
            symbols.update({"backend": "ntgcalls", "PyTgCalls": NTgCalls})
            # provide minimal placeholders for types/exceptions
            symbols.update({
                "MediaStream": object,
                "GroupCallConfig": lambda auto_start: None,
                "AudioQuality": object,
                "VideoQuality": object,
                "ChatUpdate": object,
                "StreamEnded": object,
                "Update": object,
                "NoActiveGroupCall": Exception,
                "NoAudioSourceFound": Exception,
                "NoVideoSourceFound": Exception,
                "NotInCallError": Exception,
                "PyTgCallsAlreadyRunning": Exception,
                "PyTgCallsError": Exception,
                "version": "ntgcalls-fallback",
            })
            return symbols
        except Exception:
            # nothing available
            return {}

_TGCALLS = _import_tgcalls()

# Use logging wrapper from project if available, else fallback
try:
    from AnnieXMedia import LOGGER, app, YouTube, userbot
except Exception:
    # minimal fallback
    LOGGER = lambda name=None: logging.getLogger(name or __name__)
    app = None
    YouTube = None
    userbot = None

# project imports (these must exist in your project)
try:
    import config
    from strings import get_string
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
    from AnnieXMedia.utils.formatters import check_duration, seconds_to_min, speed_converter
    from AnnieXMedia.utils.inline.play import stream_markup
except Exception:
    # If project-specific modules missing, make stubs for safe import (development only)
    def get_string(x): return lambda k: k
    db = {}
    async def group_assistant(self, chat_id): raise RuntimeError("group_assistant not available")
    class AssistantErr(Exception): pass
    def capture_internal_err(f): return f

# expose some globals required by other plugins
autoend: Dict[int, datetime] = {}
counter: Dict[int, dict] = {}

# Pull types from _TGCALLS
MediaStream = _TGCALLS.get("MediaStream", object)
GroupCallConfig = _TGCALLS.get("GroupCallConfig", lambda auto_start: None)
AudioQuality = _TGCALLS.get("AudioQuality", object)
VideoQuality = _TGCALLS.get("VideoQuality", object)
ChatUpdate = _TGCALLS.get("ChatUpdate", object)
StreamEnded = _TGCALLS.get("StreamEnded", object)
Update = _TGCALLS.get("Update", object)

NoActiveGroupCall = _TGCALLS.get("NoActiveGroupCall", Exception)
NoAudioSourceFound = _TGCALLS.get("NoAudioSourceFound", Exception)
NoVideoSourceFound = _TGCALLS.get("NoVideoSourceFound", Exception)
NotInCallError = _TGCALLS.get("NotInCallError", Exception)
PyTgCallsAlreadyRunning = _TGCALLS.get("PyTgCallsAlreadyRunning", Exception)
PyTgCallsError = _TGCALLS.get("PyTgCallsError", Exception)

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def clean_vidid(vid: Optional[Union[str,bool]]) -> Optional[str]:
    if vid is None or vid is True or vid is False: 
        return None
    return str(vid)

def extract_video_id(url: str) -> Optional[str]:
    import re
    if not url or not isinstance(url, str):
        return None
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

async def _invalidate_direct_cache_for_vid(videoid: Optional[str]) -> None:
    if not videoid or YouTube is None: 
        return
    try:
        fn = getattr(YouTube, "invalidate_direct_cache", None)
        if callable(fn):
            maybe = fn(videoid)
            if asyncio.iscoroutine(maybe):
                await maybe
    except Exception:
        pass

# MediaStream factory (safe)
def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: Optional[str] = None) -> Any:
    """
    Build a MediaStream object (pytgcalls::MediaStream) with sane ffmpeg flags.
    - Use -re for local files (prevents ffmpeg from finishing instantly).
    - Add reconnect flags for URLs.
    - Allow extra ffmpeg_params for seek/speed operations.
    """
    path = "" if path is None else str(path)
    is_url = path.startswith("http")
    base_flags = []
    # local files: read at native rate to prevent instant-complete
    if not is_url:
        base_flags.append("-re")
        base_flags.append("-threads 2")
        base_flags.append("-probesize 10M")
        base_flags.append("-analyzeduration 10M")
        base_flags.append("-fflags +genpts+igndts+nobuffer -sync ext")
    else:
        base_flags.append("-threads 2")
        base_flags.append("-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5")
        base_flags.append("-probesize 10M -analyzeduration 10M -rtbufsize 10M -fflags +genpts+igndts+nobuffer -sync ext")

    # prefer STUDIO for high-quality paths if available
    aparam = getattr(AudioQuality, "STUDIO", getattr(AudioQuality, "HIGH", AudioQuality))
    vparam = getattr(VideoQuality, "HD_720p", VideoQuality)

    if ffmpeg_params:
        base_flags.append(str(ffmpeg_params))

    ffmpeg_string = " ".join(base_flags)

    # Build MediaStream object according to backend availability
    try:
        # if real MediaStream class is available, instantiate it
        if MediaStream is not object:
            return MediaStream(
                media_path=path,
                audio_parameters=aparams if (aparams := aparam) else aparam,
                video_parameters=vparam,
                video_flags=(getattr(MediaStream, "Flags", object).REQUIRED if video else getattr(MediaStream, "Flags", object).IGNORE),
                audio_flags=(getattr(MediaStream, "Flags", object).REQUIRED),
                ffmpeg_parameters=ffmpeg_string,
            )
    except Exception:
        # last resort: return a dict describing the stream (some backends accept dicts)
        return {
            "media_path": path,
            "audio_parameters": aparam,
            "video_parameters": vparam,
            "video": video,
            "ffmpeg": ffmpeg_string,
        }

# -----------------------------------------------------------------------------
# Call Controller
# -----------------------------------------------------------------------------
class Call:
    def __init__(self):
        # userbot clients provided by project (may be None)
        one = getattr(userbot, "one", None) if userbot is not None else None
        two = getattr(userbot, "two", None) if userbot is not None else None
        three = getattr(userbot, "three", None) if userbot is not None else None
        four = getattr(userbot, "four", None) if userbot is not None else None
        five = getattr(userbot, "five", None) if userbot is not None else None

        PT = _TGCALLS.get("PyTgCalls")
        self.one = PT(one, cache_duration=100) if (PT and one) else None
        self.two = PT(two, cache_duration=100) if (PT and two) else None
        self.three = PT(three, cache_duration=100) if (PT and three) else None
        self.four = PT(four, cache_duration=100) if (PT and four) else None
        self.five = PT(five, cache_duration=100) if (PT and five) else None

        self.active_calls = set()
        self._backend = _TGCALLS.get("backend", "none")

    # internal helper to obtain the right assistant (userbot) for chat
    async def _assistant_for_chat(self, chat_id: int):
        """
        returns the low-level assistant (PyTgCalls instance bound to a userbot client)
        The project-specific helper group_assistant is used when available.
        """
        try:
            return await group_assistant(self, chat_id)
        except Exception:
            # fallback: try find any started client that includes this chat
            for candidate in (self.one, self.two, self.three, self.four, self.five):
                if candidate:
                    return candidate
            raise

    # safe play wrapper (handles auto_start config)
    async def _play_safe(self, chat_id: int, stream_obj, force_join: bool = False):
        assistant = await self._assistant_for_chat(chat_id)
        cfg = GroupCallConfig(auto_start=force_join)
        # assistant.play may be coroutine or method depending on backend
        try:
            await assistant.play(chat_id, stream_obj, config=cfg)
        except TypeError:
            # some backends accept different signature
            await assistant.play(chat_id, stream_obj)

    # basic controls
    @capture_internal_err
    async def pause_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        try:
            await assistant.resume(chat_id)
        except Exception:
            # fallback unmute
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
        except Exception:
            pass
        self.active_calls.discard(chat_id)

    @capture_internal_err
    async def force_stop_stream(self, chat_id: int):
        assistant = await self._assistant_for_chat(chat_id)
        try:
            q = db.get(chat_id)
            if isinstance(q, list) and q:
                q.pop(0)
        except Exception:
            pass
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except Exception:
            pass
        self.active_calls.discard(chat_id)

    # skip_stream simplified to immediate play with auto_start fallback
    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None):
        stream = dynamic_media_stream(path=link, video=bool(video))
        await self._play_safe(chat_id, stream, force_join=False)

    # get vc participants (non-muted)
    @capture_internal_err
    async def vc_users(self, chat_id: int) -> list:
        assistant = await self._assistant_for_chat(chat_id)
        try:
            participants = await assistant.get_participants(chat_id)
            return [p.user_id for p in participants if not getattr(p, "is_muted", False)]
        except Exception:
            return []

    # seek / speedup
    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str):
        is_video = mode == "video"
        ff = f"-ss {to_seek} -to {duration}"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ff)
        assistant = await self._assistant_for_chat(chat_id)
        await assistant.play(chat_id, stream)

    @capture_internal_err
    async def speedup_stream(self, chat_id: int, file_path: str, speed: float, playing: list):
        if not playing or not isinstance(playing, list):
            raise AssistantErr("Invalid stream info")
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
        # update db state if matches
        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            db[chat_id][0].update({
                "played": con_seconds,
                "dur": duration_min,
                "seconds": dur,
                "speed_path": out,
                "speed": speed,
            })

    # The robust join_call with permission checks and create-call fallback
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None):
        assistant = await self._assistant_for_chat(chat_id)
        lang = await get_lang(chat_id)
        _ = get_string(lang)
        final_link = link
        vid_id = extract_video_id(str(link)) if link else None
        await _invalidate_direct_cache_for_vid(vid_id)

        # Prepare stream
        stream = dynamic_media_stream(path=final_link, video=bool(video))

        # If already active just play
        if chat_id in self.active_calls:
            try:
                await self._play_safe(chat_id, stream, force_join=False)
                return
            except Exception:
                pass

        # Attempt join with retries and fallback create
        retries = 3
        for attempt in range(retries):
            try:
                await self._play_safe(chat_id, stream, force_join=True)
                # small stabilization delay
                await asyncio.sleep(1.2)
                try:
                    await assistant.mute(chat_id)
                    await asyncio.sleep(0.1)
                    await assistant.unmute(chat_id)
                except Exception:
                    pass
                break
            except Exception as e:
                err = str(e).lower()
                # Permission / No Active Call cases -> raise call_8 for stream to handle UI
                if isinstance(e, NoActiveGroupCall) or isinstance(e, NotInCallError) or "noactivegroupcall" in err or "groupcall_forbidden" in err or "chat_admin_required" in err:
                    # Try to create a group call (requires admin). Use pyrogram raw if possible.
                    try:
                        if hasattr(assistant, "app") and assistant.app:
                            try:
                                # This uses Pyrogram raw to attempt creation - will raise if not admin
                                await assistant.app.invoke(
                                    importlib.import_module("pyrogram.raw.functions.phone").CreateGroupCall(
                                        peer=await assistant.app.resolve_peer(chat_id),
                                        random_id=randint(100000, 999999)
                                    )
                                )
                                # wait a little then retry the loop
                                await asyncio.sleep(2.5)
                                continue
                            except Exception:
                                # can't create -> rethrow assistant error for call_8
                                raise AssistantErr(_["call_8"])
                    except Exception:
                        raise AssistantErr(_["call_8"])
                # If last attempt, map to specific assistant errors
                if attempt == retries - 1:
                    if isinstance(e, (NoAudioSourceFound, NoVideoSourceFound)):
                        raise AssistantErr(_["call_11"])
                    else:
                        raise AssistantErr(_["call_10"])
                await asyncio.sleep(0.8)
                continue

        # mark active
        self.active_calls.add(chat_id)
        await add_active_chat(chat_id)
        await music_on(chat_id)
        if video:
            await add_active_video_chat(chat_id)

        # autoend handling
        try:
            if await is_autoend():
                counter[chat_id] = {}
                try:
                    users = len(await assistant.get_participants(chat_id))
                    if users == 1:
                        autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                except Exception:
                    pass
        except Exception:
            pass

    # play handler (auto queue next)
    @capture_internal_err
    async def play(self, client, chat_id: int):
        check = db.get(chat_id)
        if not check:
            # cleanup and leave
            await _clear_(chat_id)
            try:
                await client.leave_call(chat_id)
            except Exception:
                pass
            return

        # queue loop/loop handling
        loop_val = await get_loop(chat_id)
        popped = None
        try:
            if loop_val == 0:
                popped = check.pop(0)
            else:
                loop_val -= 1
                await set_loop(chat_id, loop_val)
            await auto_clean(popped)
            if not check:
                await _clear_(chat_id)
                try:
                    await client.leave_call(chat_id)
                except Exception:
                    pass
                finally:
                    self.active_calls.discard(chat_id)
                return
        except Exception:
            try:
                await _clear_(chat_id)
                return await client.leave_call(chat_id)
            except Exception:
                return

        # prepare next item
        queued = check[0].get("file")
        streamtype = check[0].get("streamtype")
        videoid = clean_vidid(check[0].get("vidid"))
        language = await get_lang(chat_id)
        _ = get_string(language)
        title = (check[0].get("title") or "").title()
        user = check[0].get("by")
        original_chat_id = check[0].get("chat_id")
        is_video = str(streamtype) == "video"

        try:
            final_link = queued
            if queued and os.path.exists(str(queued)) and is_video and str(queued).endswith((".mp3", ".m4a")):
                if videoid:
                    try:
                        direct = None
                        if YouTube:
                            direct = await YouTube.get_direct_url(videoid, video=True) if hasattr(YouTube, "get_direct_url") else None
                        if direct:
                            final_link = direct
                    except Exception:
                        pass

            # special modes
            if str(queued).startswith("live_"):
                vid = videoid
                n, link = await YouTube.video(vid, True)
                if n == 0:
                    return await app.send_message(original_chat_id, text=_["call_6"])
                stream = dynamic_media_stream(path=link, video=is_video)
                await self._play_safe(chat_id, stream, force_join=False)

                img = await get_thumb(vid)
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(f"https://t.me/{app.username}?start=info_{vid}", title[:23], check[0].get("dur"), user),
                    reply_markup=InlineKeyboardMarkup(stream_markup(_, chat_id)),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
            else:
                # normal file/url
                stream = dynamic_media_stream(path=final_link, video=is_video)
                await self._play_safe(chat_id, stream, force_join=False if chat_id in self.active_calls else True)

                if is_video:
                    await add_active_video_chat(chat_id)
                else:
                    await remove_active_video_chat(chat_id)

                img = await get_thumb(videoid)
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(f"https://t.me/{app.username}?start=info_{videoid}", title[:23], check[0].get("dur"), user),
                    reply_markup=InlineKeyboardMarkup(stream_markup(_, chat_id)),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
        except Exception:
            # safe log without broken f-strings
            try:
                LOGGER(__name__).error("PLAY ERROR for chat %s: %s", str(chat_id), traceback.format_exc())
            except Exception:
                # ultimate fallback
                logging.error("PLAY ERROR for chat %s", chat_id)
            await _clear_(chat_id)
            try:
                await client.leave_call(chat_id)
            except Exception:
                pass
            return await app.send_message(original_chat_id, text=_["call_6"])

    # start all PyTgCalls clients
    async def start(self):
        try:
            if self.one and getattr(config, "STRING1", None):
                await self.one.start()
            if self.two and getattr(config, "STRING2", None):
                await self.two.start()
            if self.three and getattr(config, "STRING3", None):
                await self.three.start()
            if self.four and getattr(config, "STRING4", None):
                await self.four.start()
            if self.five and getattr(config, "STRING5", None):
                await self.five.start()
        except Exception:
            LOGGER(__name__).exception("Failed to start one of the call clients")

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if self.one and getattr(config, "STRING1", None):
            pings.append(getattr(self.one, "ping", 0))
        if self.two and getattr(config, "STRING2", None):
            pings.append(getattr(self.two, "ping", 0))
        if self.three and getattr(config, "STRING3", None):
            pings.append(getattr(self.three, "ping", 0))
        if self.four and getattr(config, "STRING4", None):
            pings.append(getattr(self.four, "ping", 0))
        if self.five and getattr(config, "STRING5", None):
            pings.append(getattr(self.five, "ping", 0))
        try:
            return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"
        except Exception:
            return "0.0"

    @capture_internal_err
    async def decorators(self):
        assistants = [a for a in (self.one, self.two, self.three, self.four, self.five) if a]
        CRITICAL = getattr(ChatUpdate, "Status", 0) if hasattr(ChatUpdate, "Status") else 0

        async def handler(client, update: Update):
            try:
                if isinstance(update, StreamEnded):
                    try:
                        assistant = await group_assistant(self, update.chat_id)
                        await self.play(assistant, update.chat_id)
                    except Exception:
                        pass
                elif isinstance(update, ChatUpdate):
                    status = getattr(update, "status", 0)
                    # bitmask checks if available
                    if (status & getattr(ChatUpdate.Status, "LEFT_CALL", 0)) or (status & CRITICAL):
                        await self.stop_stream(update.chat_id)
            except Exception:
                pass

        for assistant in assistants:
            try:
                assistant.on_update()(handler)
            except Exception:
                pass

# single controller instance used by project
StreamController = Call()

# re-export for other plugins
__all__ = ["StreamController", "Call", "autoend", "counter"]
