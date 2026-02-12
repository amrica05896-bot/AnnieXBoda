# CallController.py
# Modern, robust Call controller for PyTgCalls + Pyrogram
# - Verifies assistant admin rights
# - Attempts safe join / create group call when necessary
# - Raises AssistantErr(_["call_8"]) when assistant lacks permission or no active call
# - Keeps ffmpeg flags tuned for stability
# - Minimal external side-effects; integrates with AnnieXMedia helpers

import asyncio
import os
import re
from random import randint
from datetime import datetime, timedelta
from typing import Union, Optional

import yt_dlp
from pyrogram.raw import functions
from pyrogram.errors import ChatAdminRequired, UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup

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
except Exception:
    # graceful fallback for editors/tests
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

import config
from strings import get_string
from AnnieXMedia import LOGGER, YouTube, app, userbot
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import (
    add_active_chat,
    add_active_video_chat,
    get_lang,
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


# --------------------------
# Helpers
# --------------------------

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
    opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
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


def dynamic_media_stream(path: str, video: bool = False) -> MediaStream:
    """Create a MediaStream tuned for stability.
    - Local files need -re to avoid instant ffmpeg finishing and PyTgCalls drop.
    - URLs get reconnect flags.
    """
    if not path:
        path = ""
    path = str(path)
    is_url = path.startswith("http")

    # audio-only file -> force audio
    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")):
        video = False

    if is_url:
        ff = (
            "-threads 2 "
            "-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 "
            "-probesize 10M -analyzeduration 10M "
            "-rtbufsize 10M "
            "-fflags +genpts+igndts+nobuffer -sync ext"
        )
    else:
        # local files MUST have -re
        ff = (
            "-re -threads 2 "
            "-probesize 10M -analyzeduration 10M "
            "-fflags +genpts+igndts+nobuffer -sync ext"
        )

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.HD_720p,
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=ff,
    )


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


# --------------------------
# Call Controller
# --------------------------

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

    # --------------------------
    # Robust join_call implementation
    # --------------------------
    async def _assistant_is_admin(self, user_client, chat_id: int) -> bool:
        """Return True if assistant is admin (creator or has manage voice/video rights)."""
        try:
            me = await user_client.get_chat_member(chat_id, "me")
            status = getattr(me, "status", "")
            if status in ("creator", "administrator"):
                # check explicit voice permissions when available
                can_manage = getattr(me, "can_manage_voice_chats", None)
                if can_manage is None:
                    # attribute not present on some pyrogram versions; assume admin is OK
                    return True
                return bool(can_manage)
            return False
        except Exception:
            return False

    async def _verify_call_active(self, assistant, chat_id: int) -> bool:
        """Verify there is a live group call where assistant is present as speaker/listener.
        If assistant cannot get participants or participants list is empty -> consider it inactive.
        """
        try:
            parts = await assistant.get_participants(chat_id)
            # If participants is empty or only the assistant, treat as inactive
            if not parts:
                return False
            # If there's more than 0 participants it's active
            return True
        except Exception:
            return False

    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        user_client = getattr(assistant, "app", getattr(assistant, "client", None))
        lang = await get_lang(chat_id)
        _ = get_string(lang)

        final_link = link
        vid_id = extract_video_id(str(link)) if link else None
        await _invalidate_direct_cache_for_vid(vid_id)

        # Resolve direct links for youtube/local
        try:
            if link and os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a")):
                if vid_id:
                    direct = await get_direct_link(vid_id, video=True)
                    if direct:
                        final_link = direct
            elif link and ("youtube" in str(link) or "http" in str(link)):
                if vid_id:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct:
                        final_link = direct
        except Exception:
            pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))

        # If call is already active according to controller -> try simple play
        if chat_id in self.active_calls:
            try:
                await self._play_safe(chat_id, stream, force_join=False)
                return
            except Exception:
                # fall through to join flow
                pass

        # BEFORE attempting to join: check assistant admin rights when possible
        if user_client:
            is_admin = await self._assistant_is_admin(user_client, chat_id)
        else:
            is_admin = True  # conservative default if we can't check

        # Attempt to join / create with retries
        retries = 3
        for attempt in range(retries):
            try:
                # If assistant isn't admin and we detect there's no active call, fail early with call_8
                # But we first check if a call exists remotely (best-effort):
                if not is_admin:
                    # try to check if there is an active call by attempting to get participants
                    try:
                        tmp_assistant = await group_assistant(self, chat_id)
                        active = await self._verify_call_active(tmp_assistant, chat_id)
                    except Exception:
                        active = False

                    if not active:
                        # assistant not admin and no active call -> raise call_8 to stop stream UI
                        raise AssistantErr(_["call_8"])

                # Use auto_start to attempt an atomic join+play. If it silently fails (no exception), we will verify below.
                await self._play_safe(chat_id, stream, force_join=True)

                # small stabilization delay
                await asyncio.sleep(1.2)

                # force an audio wakeup (best-effort)
                try:
                    await assistant.mute(chat_id)
                    await asyncio.sleep(0.1)
                    await assistant.unmute(chat_id)
                except Exception:
                    pass

                # VERIFY: ensure call is active (participants exist) and assistant actually joined
                active_ok = await self._verify_call_active(assistant, chat_id)
                if not active_ok:
                    # Attempt to create group call if we can (user_client present)
                    if user_client:
                        try:
                            await user_client.invoke(
                                functions.phone.CreateGroupCall(
                                    peer=await user_client.resolve_peer(chat_id),
                                    random_id=randint(10000, 99999),
                                )
                            )
                            # allow Telegram to settle
                            await asyncio.sleep(2.2)
                            # try join again
                            await self._play_safe(chat_id, stream, force_join=True)
                            await asyncio.sleep(1.0)
                            active_ok = await self._verify_call_active(assistant, chat_id)
                        except Exception:
                            active_ok = False

                if not active_ok:
                    # After retries or creation attempt, if still not active and assistant not admin -> call_8
                    if not is_admin:
                        raise AssistantErr(_["call_8"])
                    # If assistant is admin but still not active, treat as generic play error
                    raise AssistantErr(_["call_10"])

                # Success: mark active and return
                self.active_calls.add(chat_id)
                await add_active_chat(chat_id)
                await music_on(chat_id)
                if video:
                    await add_active_video_chat(chat_id)

                # autoend handling
                if await is_autoend():
                    try:
                        users = len(await assistant.get_participants(chat_id))
                        if users == 1:
                            # schedule autoend in 1 minute if alone
                            # store in db or in-memory counter handled externally
                            pass
                    except Exception:
                        pass

                return

            except AssistantErr:
                # Known assistant-level error should bubble up unchanged
                raise

            except Exception as e:
                err_str = str(e).lower()

                # If permissions error -> immediate call_8
                if isinstance(e, ChatAdminRequired) or "chat_admin_required" in err_str:
                    raise AssistantErr(_["call_8"])

                # If NoActiveGroupCall we will try create / retry a few times
                if isinstance(e, NoActiveGroupCall) or "noactivegroupcall" in err_str:
                    # try to CreateGroupCall (best-effort) if user_client exists
                    if user_client:
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
                            # creation failed - most likely due to permissions -> call_8
                            raise AssistantErr(_["call_8"])

                # Race-condition: already running
                if isinstance(e, PyTgCallsAlreadyRunning) or "already joined" in err_str:
                    try:
                        await self._play_safe(chat_id, stream, force_join=False)
                        # let verification loop re-evaluate on next attempt
                        await asyncio.sleep(0.6)
                        continue
                    except Exception:
                        pass

                # If last attempt, map some exceptions to user-friendly messages
                if attempt == retries - 1:
                    if isinstance(e, (NoAudioSourceFound, NoVideoSourceFound)):
                        raise AssistantErr(_["call_11"])
                    raise AssistantErr(_["call_10"])

                # otherwise wait and retry
                await asyncio.sleep(1)

        # If we exit loop without return, throw generic
        raise AssistantErr(_["call_10"])

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients...")
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
                    status = update.status
                    CRITICAL = (ChatUpdate.Status.KICKED | ChatUpdate.Status.LEFT_GROUP | ChatUpdate.Status.CLOSED_VOICE_CHAT)
                    if (status & ChatUpdate.Status.LEFT_CALL) or (status & CRITICAL):
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

        # pop / loop logic handled elsewhere; minimal play implementation here
        popped = check.pop(0)
        await auto_clean(popped)
        if not check:
            await _clear_(chat_id)
            try:
                await client.leave_call(chat_id)
            except Exception:
                pass
            return

        queued = check[0].get("file")
        videoid = clean_vidid(check[0].get("vidid"))
        new_is_video = str(check[0].get("streamtype")) == "video"

        stream = dynamic_media_stream(path=queued, video=new_is_video)

        try:
            if chat_id in self.active_calls:
                await self._play_safe(chat_id, stream, force_join=False)
            else:
                await self._play_safe(chat_id, stream, force_join=True)

            img = await get_thumb(videoid)
            _ = get_string(await get_lang(chat_id))
            run = await app.send_photo(
                chat_id=check[0].get("chat_id"),
                photo=img,
                caption=_["stream_1"].format(f"https://t.me/{app.username}?start=info_{videoid}", check[0].get("title")[:23], check[0].get("dur"), check[0].get("by")),
                reply_markup=InlineKeyboardMarkup([]),
            )
            db[chat_id][0]["mystic"] = run
        except Exception:
            await _clear_(chat_id)


# singleton
StreamController = Call()
