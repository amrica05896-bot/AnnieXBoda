"""
Call Controller (Merged - Revised)
Author: Certified Coders © 2026
System: Hybrid Engine (Hasii + AnonX + Alexa)
Purpose: Robust, compatible Call controller for PyTgCalls / NTgCalls / Pyrogram
Fixes applied in this revision:
- Guaranteed module-level `autoend` & `counter` for plugin imports
- Fixed instant-leave by forcing `-re` for local files and improved ffmpeg flags
- Stronger join logic: explicit permission checks, create-group-call only when allowed
- Verify participants after join and raise `call_8` if assistant isn't allowed to stay
- Defensive fallbacks when pytgcalls/ntgcalls aren't available
- Preserves all public methods used by AnnieXMedia (play/pause/stop/skip/etc.)
"""

import asyncio
import os
import re
import traceback
from random import randint
from datetime import datetime, timedelta
from typing import Union, Optional

import yt_dlp
from pyrogram.raw import functions
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, FloodWait
from pyrogram.types import InlineKeyboardMarkup

# Try to import pytgcalls first, fallback to ntgcalls if available. If neither, provide safe fallbacks.
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
        import ntgcalls as ntg  # type: ignore
        # Best-effort mappings
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
        # placeholders so module imports never fail
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

# Module-level state for plugins
autoend: dict[int, datetime] = {}
counter: dict[int, dict] = {}

# ------------------------------
# Helpers
# ------------------------------

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


def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: Optional[str] = None) -> MediaStream:
    """Return a MediaStream configured to avoid instant-leave.
    Local files MUST be played with `-re` so ffmpeg reads in realtime.
    Remote URLs include reconnect flags.
    """
    if not path:
        path = ""
    path = str(path)
    is_url = path.startswith("http")

    # If local audio file, force audio-only
    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")):
        video = False

    # Base flags
    if is_url:
        titan_flags = (
            "-threads 2 "
            "-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 "
            "-probesize 10M -analyzeduration 10M "
            "-rtbufsize 10M "
            "-fflags +genpts+igndts+nobuffer -sync ext"
        )
    else:
        # Critical: -re so ffmpeg doesn't finish instantly
        titan_flags = (
            "-re -threads 2 -ac 2 "
            "-probesize 10M -analyzeduration 10M "
            "-fflags +genpts+igndts+nobuffer -sync ext"
        )

    if ffmpeg_params:
        titan_flags = f"{titan_flags} {ffmpeg_params}"

    try:
        return MediaStream(
            media_path=path,
            audio_parameters=getattr(AudioQuality, "HIGH", AudioQuality),
            video_parameters=getattr(VideoQuality, "HD_720p", VideoQuality),
            video_flags=getattr(MediaStream, "Flags", type("F", (), {"REQUIRED": 1, "IGNORE": 0})).REQUIRED if video else getattr(MediaStream, "Flags", type("F", (), {"REQUIRED": 1, "IGNORE": 0})).IGNORE,
            audio_flags=getattr(MediaStream, "Flags", type("F", (), {"REQUIRED": 1})).REQUIRED,
            ffmpeg_parameters=titan_flags,
        )
    except Exception:
        # Fallback lightweight object so callers don't crash in test env
        class _S:
            def __init__(self, **kw):
                self.__dict__.update(kw)

        return _S(media_path=path, ffmpeg_parameters=titan_flags)


async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped:
        await auto_clean(popped)
    db[chat_id] = []
    await remove_active_video_chat(chat_id)
    await remove_active_chat(chat_id)
    await set_loop(chat_id, 0)


async def _invalidate_direct_cache_for_vid(videoid: Optional[str]) -> None:
    if not videoid:
        return
    try:
        fn = getattr(YouTube, "invalidate_direct_cache", None)
        if callable(fn):
            maybe = fn(videoid)
            if asyncio.iscoroutine(maybe):
                await maybe
    except Exception:
        pass


class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        self.one = PyTgCalls(self.userbot1, cache_duration=100) if self.userbot1 and TCALLS_BACKEND != "none" else None
        self.two = PyTgCalls(self.userbot2, cache_duration=100) if self.userbot2 and TCALLS_BACKEND != "none" else None
        self.three = PyTgCalls(self.userbot3, cache_duration=100) if self.userbot3 and TCALLS_BACKEND != "none" else None
        self.four = PyTgCalls(self.userbot4, cache_duration=100) if self.userbot4 and TCALLS_BACKEND != "none" else None
        self.five = PyTgCalls(self.userbot5, cache_duration=100) if self.userbot5 and TCALLS_BACKEND != "none" else None

        self.active_calls: set[int] = set()
        self.turbo_mode: dict = {}

    async def _send_log(self, text: str):
        if not getattr(config, "LOGGER_ID", None):
            return
        try:
            await app.send_message(config.LOGGER_ID, text, disable_web_page_preview=True)
        except Exception:
            pass

    async def _play_safe(self, chat_id, stream, force_join=False):
        assistant = await group_assistant(self, chat_id)
        cfg = GroupCallConfig(auto_start=bool(force_join))
        await assistant.play(chat_id, stream, config=cfg)

    @capture_internal_err
    async def pause_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try:
            await assistant.resume(chat_id)
        except Exception:
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
        except Exception:
            pass
        finally:
            self.active_calls.discard(chat_id)

    @capture_internal_err
    async def force_stop_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try:
            check = db.get(chat_id)
            if check:
                check.pop(0)
        except Exception:
            pass
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except Exception:
            pass
        finally:
            self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        if not link:
            try:
                check = db.get(chat_id)
                if check:
                    link = check[0].get("file")
            except Exception:
                pass
            if not link:
                return

        final_link = link
        vid_id = extract_video_id(str(link))
        await _invalidate_direct_cache_for_vid(vid_id)

        if os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a")):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=True)
                    if direct:
                        final_link = direct
                except Exception:
                    pass
        elif link and ("youtube" in str(link) or "http" in str(link)):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct:
                        final_link = direct
                except Exception:
                    pass

        new_is_video = bool(video)
        old_is_video = False
        try:
            check = db.get(chat_id)
            if check:
                old_is_video = str(check[0].get("streamtype")) == "video"
        except Exception:
            pass

        stream = dynamic_media_stream(path=final_link, video=new_is_video)
        assistant = await group_assistant(self, chat_id)

        if chat_id in self.active_calls:
            try:
                if old_is_video != new_is_video:
                    try:
                        await assistant.leave_call(chat_id)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
                    await self._play_safe(chat_id, stream, force_join=True)
                else:
                    await self._play_safe(chat_id, stream, force_join=False)
            except (NoActiveGroupCall, NotInCallError):
                await self._play_safe(chat_id, stream, force_join=True)
            except Exception:
                try:
                    await self.stop_stream(chat_id)
                except Exception:
                    pass
                await asyncio.sleep(0.2)
                await self._play_safe(chat_id, stream, force_join=True)
        else:
            await self._play_safe(chat_id, stream, force_join=True)

        if new_is_video:
            await add_active_video_chat(chat_id)
        else:
            await remove_active_video_chat(chat_id)

    # ==========================================================
    # Robust join logic (prevents instant leave + handles perms)
    # ==========================================================
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        lang = await get_lang(chat_id)
        _ = get_string(lang)

        final_link = link
        vid_id = extract_video_id(str(link)) if link else None
        await _invalidate_direct_cache_for_vid(vid_id)

        # Resolve direct urls for some patterns
        try:
            if link and os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a")):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=True)
                        if direct:
                            final_link = direct
                    except Exception:
                        pass
            elif link and ("youtube" in str(link) or "http" in str(link)):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=bool(video))
                        if direct:
                            final_link = direct
                    except Exception:
                        pass
        except Exception:
            pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))

        # If already active just change stream
        if chat_id in self.active_calls:
            try:
                await self._play_safe(chat_id, stream, force_join=False)
                return
            except Exception:
                pass

        # Determine if assistant is admin/can manage vc
        user_client = None
        try:
            # try obtain the underlying pyrogram client of the assistant
            ass = await group_assistant(self, chat_id)
            user_client = getattr(ass, "app", None) or getattr(ass, "client", None)
        except Exception:
            user_client = None

        is_admin = True
        if user_client:
            try:
                mem = await user_client.get_chat_member(chat_id, "me")
                status = getattr(mem, "status", "")
                if status not in ("creator", "administrator"):
                    is_admin = False
                else:
                    can_manage = getattr(mem, "can_manage_voice_chats", None)
                    if can_manage is False:
                        is_admin = False
            except Exception:
                # if we can't check, assume True to avoid false positives
                is_admin = True

        # If assistant not admin, check whether a group call exists and assistant is participant
        if not is_admin:
            try:
                parts = await assistant.get_participants(chat_id)
                # if call empty -> assistant can't create -> raise immediate call_8
                if not parts:
                    raise AssistantErr(_["call_8"])
            except AssistantErr:
                raise
            except Exception:
                raise AssistantErr(_["call_8"])

        # Attempt join with retries
        retries = 3
        for attempt in range(retries):
            try:
                # Auto-start join attempt
                await self._play_safe(chat_id, stream, force_join=True)

                # Let network settle and avoid instant-kick
                await asyncio.sleep(1.3)

                # audio wakeup (best-effort)
                try:
                    await assistant.mute(chat_id)
                    await asyncio.sleep(0.05)
                    await assistant.unmute(chat_id)
                except Exception:
                    pass

                # verify presence
                try:
                    parts = await assistant.get_participants(chat_id)
                    if not parts:
                        # if we have permission to create, create and retry once
                        if user_client and is_admin:
                            try:
                                await user_client.invoke(
                                    functions.phone.CreateGroupCall(
                                        peer=await user_client.resolve_peer(chat_id),
                                        random_id=randint(10000, 99999),
                                    )
                                )
                                await asyncio.sleep(2)
                                await self._play_safe(chat_id, stream, force_join=True)
                                parts = await assistant.get_participants(chat_id)
                            except Exception:
                                raise AssistantErr(_["call_8"])
                        else:
                            raise AssistantErr(_["call_8"])

                    # sometimes assistant enters as listener; ensure it's still present after short wait
                    await asyncio.sleep(0.8)
                    parts = await assistant.get_participants(chat_id)
                    if not parts:
                        raise AssistantErr(_["call_8"])

                except AssistantErr:
                    # propagate call_8 to caller so stream module can stop UI
                    raise
                except Exception:
                    # allow outer retry loop
                    pass

                # success
                self.active_calls.add(chat_id)
                await add_active_chat(chat_id)
                await music_on(chat_id)
                if video:
                    await add_active_video_chat(chat_id)

                if await is_autoend():
                    counter[chat_id] = {}
                    try:
                        users = len(await assistant.get_participants(chat_id))
                        if users == 1:
                            autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                    except Exception:
                        pass

                return

            except AssistantErr:
                # re-raise so caller (stream) shows UI message
                raise
            except Exception as e:
                err_str = str(e).lower()
                if isinstance(e, ChatAdminRequired) or "chat_admin_required" in err_str or "groupcall_forbidden" in err_str:
                    raise AssistantErr(_["call_8"])

                if isinstance(e, NoActiveGroupCall) or "noactivegroupcall" in err_str:
                    if user_client and is_admin:
                        try:
                            await user_client.invoke(
                                functions.phone.CreateGroupCall(
                                    peer=await user_client.resolve_peer(chat_id),
                                    random_id=randint(10000, 99999),
                                )
                            )
                            await asyncio.sleep(2)
                            continue
                        except Exception:
                            raise AssistantErr(_["call_8"])

                if isinstance(e, PyTgCallsAlreadyRunning) or "already joined" in err_str:
                    try:
                        await self._play_safe(chat_id, stream, force_join=False)
                        await asyncio.sleep(0.6)
                        continue
                    except Exception:
                        pass

                if attempt == retries - 1:
                    if isinstance(e, (NoAudioSourceFound, NoVideoSourceFound)):
                        raise AssistantErr(_["call_11"])
                    raise AssistantErr(_["call_10"])

                await asyncio.sleep(1)

        # fallback
        raise AssistantErr(_["call_10"])

    async def start(self) -> None:
        LOGGER(__name__).info("Starting Call Clients... Backend: %s" % TCALLS_BACKEND)
        if self.one and getattr(config, "STRING1", None):
            try:
                await self.one.start()
            except Exception:
                LOGGER(__name__).exception("Failed to start client one")
        if self.two and getattr(config, "STRING2", None):
            try:
                await self.two.start()
            except Exception:
                LOGGER(__name__).exception("Failed to start client two")
        if self.three and getattr(config, "STRING3", None):
            try:
                await self.three.start()
            except Exception:
                LOGGER(__name__).exception("Failed to start client three")
        if self.four and getattr(config, "STRING4", None):
            try:
                await self.four.start()
            except Exception:
                LOGGER(__name__).exception("Failed to start client four")
        if self.five and getattr(config, "STRING5", None):
            try:
                await self.five.start()
            except Exception:
                LOGGER(__name__).exception("Failed to start client five")

    async def ping(self) -> str:
        pings = []
        if self.one and getattr(config, "STRING1", None):
            pings.append(self.one.ping)
        if self.two and getattr(config, "STRING2", None):
            pings.append(self.two.ping)
        if self.three and getattr(config, "STRING3", None):
            pings.append(self.three.ping)
        if self.four and getattr(config, "STRING4", None):
            pings.append(self.four.ping)
        if self.five and getattr(config, "STRING5", None):
            pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        async def unified_update_handler(client, update: Update) -> None:
            try:
                if isinstance(update, StreamEnded):
                    try:
                        assistant = await group_assistant(self, update.chat_id)
                        await self.play(assistant, update.chat_id)
                    except Exception:
                        pass
                elif isinstance(update, ChatUpdate):
                    status = getattr(update, "status", 0)
                    CRITICAL = (getattr(ChatUpdate, "Status", type("S", (), {"KICKED": 1, "LEFT_GROUP": 2, "CLOSED_VOICE_CHAT": 4})).KICKED
                                | getattr(ChatUpdate, "Status", type("S", (), {"KICKED": 1, "LEFT_GROUP": 2, "CLOSED_VOICE_CHAT": 4})).LEFT_GROUP
                                | getattr(ChatUpdate, "Status", type("S", (), {"KICKED": 1, "LEFT_GROUP": 2, "CLOSED_VOICE_CHAT": 4})).CLOSED_VOICE_CHAT)
                    if (status & getattr(ChatUpdate, "Status", type("S", (), {"LEFT_CALL": 8})).LEFT_CALL) or (status & CRITICAL):
                        await self.stop_stream(update.chat_id)
            except Exception:
                pass

        for assistant in assistants:
            try:
                assistant.on_update()(unified_update_handler)
            except Exception:
                pass

    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        if not check:
            await _clear_(chat_id)
            try:
                await client.leave_call(chat_id)
            except Exception:
                pass
            return

        old_is_video = False
        try:
            if len(check) > 0:
                old_is_video = str(check[0].get("streamtype")) == "video"
        except Exception:
            pass

        popped = None
        loop = await get_loop(chat_id)
        try:
            if loop == 0:
                popped = check.pop(0)
            else:
                loop = loop - 1
                await set_loop(chat_id, loop)
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
                            if direct:
                                final_link = direct
                        except Exception:
                            pass
                if queued and ("live_" in str(queued) or "vid_" in str(queued) or "index_" in str(queued)):
                    try:
                        if vid_id:
                            direct_url = await get_direct_link(vid_id, video=new_is_video)
                            if direct_url:
                                final_link = direct_url
                            else:
                                path_direct = await YouTube.download(vid_id, None, video=new_is_video, videoid=vid_id)
                                if isinstance(path_direct, tuple) and path_direct[0]:
                                    final_link = path_direct[0]
                    except Exception:
                        pass

                stream = dynamic_media_stream(path=final_link, video=new_is_video)

                # join or play
                if old_is_video != new_is_video:
                    try:
                        await client.leave_call(chat_id)
                    except Exception:
                        pass
                    await self._play_safe(chat_id, stream, force_join=True)
                else:
                    if chat_id in self.active_calls:
                        try:
                            await self._play_safe(chat_id, stream, force_join=False)
                        except (NoActiveGroupCall, NotInCallError):
                            await self._play_safe(chat_id, stream, force_join=True)
                    else:
                        await self._play_safe(chat_id, stream, force_join=True)

                if new_is_video:
                    await add_active_video_chat(chat_id)
                else:
                    await remove_active_video_chat(chat_id)

                img = await get_thumb(videoid)
                button = stream_markup(_, chat_id)
                try:
                    if db[chat_id][0].get("mystic"):
                        await db[chat_id][0].get("mystic").delete()
                except Exception:
                    pass
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(f"https://t.me/{app.username}?start=info_{videoid}", title[:23], check[0].get("dur"), user),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
            except Exception as e:
                LOGGER(__name__).error(f"💣 [PLAY ERROR] Chat: {chat_id}
{traceback.format_exc()}")
                await _clear_(chat_id)
                try:
                    await client.leave_call(chat_id)
                except Exception:
                    pass
                return await app.send_message(original_chat_id, text=_["call_6"])


# singleton
StreamController = Call()
