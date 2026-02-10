# Authored By Certified Coders © 2026
# System: Call Controller (Crash Fixes & Strict Type Safety)
# Notes: Compatible with py-tgcalls (module name: pytgcalls) / version 2.2.11
# Fixes included: NoneType checks, audio/video switching, retries, safe handler registration
# Changes: added cache invalidation helper, safe stream restart helper, stronger fallbacks

import asyncio
import os
import re
import traceback
import yt_dlp
from datetime import datetime, timedelta
from typing import Union, Optional

from ntgcalls import TelegramServerError, ConnectionNotFound
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired
from pyrogram.types import InlineKeyboardMarkup
from pytgcalls import PyTgCalls
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NoAudioSourceFound,
    NoVideoSourceFound,
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
from AnnieXMedia.utils.formatters import check_duration, seconds_to_min, speed_converter
from AnnieXMedia.utils.inline.play import stream_markup
from AnnieXMedia.utils.stream.autoclear import auto_clean
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

autoend = {}
counter = {}

# --- [1] Robust Helpers ---


def clean_vidid(vid):
    """Sanitizes Video ID to ensure it's a valid string."""
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
    """Fetches direct URL with strict format selection."""
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
        # fallback: return watch link so calling code can try download fallback
        return link


def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    """
    Build MediaStream compatible with pytgcalls 2.2.11 structure.
    Uses robust ffmpeg flags for URL/local paths and prevents audio-as-video crashes.
    """
    if not path:
        path = ""
    path = str(path)
    is_url = path.startswith("http")

    # Prevent trying to stream a local audio file as video
    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")):
        video = False

    # Titan flags (tuned)
    if is_url:
        titan_flags = (
            "-threads 4 -probesize 10M -analyzeduration 10M -rtbufsize 15M "
            "-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 "
            "-fflags +genpts+igndts+nobuffer -sync ext"
        )
    else:
        titan_flags = "-threads 4 -probesize 10M -analyzeduration 10M -fflags +genpts+igndts+nobuffer -sync ext"

    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    # NOTE: signature may vary depending on installed version; this form is compatible with 2.2.11 structure
    try:
        # Try the named-args style (some builds)
        return MediaStream(
            media_path=path,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
            video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
            audio_flags=MediaStream.Flags.REQUIRED,
            ffmpeg_parameters=titan_flags,
        )
    except TypeError:
        # Fallback constructor signature used by some releases
        return MediaStream(
            path,
            audio_quality=AudioQuality.HIGH,
            video_quality=VideoQuality.HD_720p if video else None,
            ffmpeg_parameters=titan_flags,
        )


async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped:
        await auto_clean(popped)
    db[chat_id] = []
    await remove_active_video_chat(chat_id)
    await remove_active_chat(chat_id)
    await set_loop(chat_id, 0)


# ---- cache invalidation helper (tries multiple safe attempts) ----
async def _invalidate_direct_cache_for_vid(videoid: Optional[str]) -> None:
    """Try to remove direct-cache entries related to a vid from YouTube helper caches."""
    if not videoid:
        return
    try:
        # If YouTube exposes a method (preferred)
        fn = getattr(YouTube, "invalidate_direct_cache", None)
        if callable(fn):
            try:
                # call sync or async
                maybe = fn(videoid)
                if asyncio.iscoroutine(maybe):
                    await maybe
                return
            except Exception:
                pass

        # fallback: try to access internals (best-effort)
        cache = getattr(YouTube, "_direct_cache", None)
        lock = getattr(YouTube, "_direct_cache_lock", None)
        if cache is None:
            # sometimes cache is module-level variable in platform module, try attribute on class
            cache = getattr(YouTube, "direct_cache", None)

        if cache and isinstance(cache, dict):
            if lock and hasattr(lock, "__aenter__"):
                try:
                    async with lock:
                        keys = list(cache.keys())
                        prefix = f"https://www.youtube.com/watch?v={videoid}"
                        for k in keys:
                            if videoid in k or prefix in k:
                                cache.pop(k, None)
                except Exception:
                    # last resort: mutate without lock
                    keys = list(cache.keys())
                    prefix = f"https://www.youtube.com/watch?v={videoid}"
                    for k in keys:
                        if videoid in k or prefix in k:
                            cache.pop(k, None)
            else:
                keys = list(cache.keys())
                prefix = f"https://www.youtube.com/watch?v={videoid}"
                for k in keys:
                    if videoid in k or prefix in k:
                        cache.pop(k, None)
    except Exception:
        # don't raise; it's a best-effort invalidation
        pass


# safe stream play/change helper
async def _safe_apply_stream(assistant, chat_id: int, stream_obj, prefer_restart: bool = False):
    """
    Try change_stream first. If type change or failure, do leave+play to ensure correct stream type.
    prefer_restart: force leave+play (useful when switching audio<->video).
    """
    try:
        if prefer_restart:
            try:
                await assistant.leave_call(chat_id)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            await assistant.play(chat_id, stream_obj, config=GroupCallConfig(auto_start=False))
            return

        # try changing stream (fast)
        try:
            await assistant.change_stream(chat_id, stream_obj)
            return
        except Exception:
            # fallback: try play (some builds require play instead)
            try:
                await assistant.play(chat_id, stream_obj, config=GroupCallConfig(auto_start=False))
                return
            except Exception:
                # last resort: leave then play
                try:
                    await assistant.leave_call(chat_id)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                await assistant.play(chat_id, stream_obj, config=GroupCallConfig(auto_start=False))
                return
    except Exception as e:
        raise


# --- [2] Call Controller ---


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
        except (IndexError, KeyError):
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
        assistant = await group_assistant(self, chat_id)

        # Handle NoneType link to prevent crash
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

        # invalidate direct cache for this vid (best-effort)
        await _invalidate_direct_cache_for_vid(vid_id)

        # SMART SWITCH: local audio + video requested -> try fetch direct video
        if os.path.exists(str(link)) and video:
            if str(link).endswith((".mp3", ".m4a", ".flac", ".opus")):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=True)
                        if direct:
                            final_link = direct
                    except Exception:
                        pass

        elif link and ("youtube" in str(link) or "youtu.be" in str(link)):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct:
                        final_link = direct
                except Exception:
                    pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))

        # determine if we need a restart: check queued/current streamtype
        prefer_restart = False
        try:
            current = db.get(chat_id) and db.get(chat_id)[0]
            current_type = current.get("streamtype") if current else None
            new_type = "video" if bool(video) else "audio"
            if current_type and str(current_type) != str(new_type):
                prefer_restart = True
        except Exception:
            prefer_restart = False

        if chat_id in self.active_calls:
            try:
                await _safe_apply_stream(assistant, chat_id, stream, prefer_restart=prefer_restart)
            except Exception:
                try:
                    # last-ditch: force leave and play
                    try:
                        await assistant.leave_call(chat_id)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
                    await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=False))
                except Exception:
                    pass
        else:
            await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=False))

    @capture_internal_err
    async def vc_users(self, chat_id: int) -> list:
        assistant = await group_assistant(self, chat_id)
        try:
            participants = await assistant.get_participants(chat_id)
            return [p.user_id for p in participants if not getattr(p, "is_muted", False)]
        except Exception:
            return []

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        ffmpeg_params = f"-ss {to_seek} -to {duration}"
        is_video = mode == "video"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ffmpeg_params)
        await assistant.change_stream(chat_id, stream)

    @capture_internal_err
    async def speedup_stream(self, chat_id: int, file_path: str, speed: float, playing: list) -> None:
        if not isinstance(playing, list) or not playing or not isinstance(playing[0], dict):
            raise AssistantErr("Invalid stream info for speedup.")
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
        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            await assistant.change_stream(chat_id, stream)
            db[chat_id][0].update({
                "played": con_seconds,
                "dur": duration_min,
                "seconds": dur,
                "speed_path": out,
                "speed": speed,
            })
        else:
            raise AssistantErr("Stream mismatch.")

    @capture_internal_err
    async def stream_call(self, link: str) -> None:
        assistant = await group_assistant(self, config.LOGGER_ID)
        stream = dynamic_media_stream(link)
        try:
            await assistant.play(config.LOGGER_ID, stream)
            await asyncio.sleep(8)
        except Exception:
            pass
        finally:
            try:
                await assistant.leave_call(config.LOGGER_ID)
            except Exception:
                pass

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
        vid_id = extract_video_id(str(link)) if link else None

        # invalidate direct cache for this vid (best-effort)
        await _invalidate_direct_cache_for_vid(vid_id)

        # SMART JOIN: local audio + video requested -> refetch direct video
        if link and os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a", ".flac", ".opus")):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=True)
                    if direct:
                        final_link = direct
                except Exception:
                    pass

        elif link and ("youtube" in str(link) or "youtu.be" in str(link)):
            if vid_id:
                try:
                    direct = await get_direct_link(vid_id, video=bool(video))
                    if direct:
                        final_link = direct
                except Exception:
                    pass

        stream = dynamic_media_stream(path=final_link, video=bool(video))
        ksk = GroupCallConfig(auto_start=False)

        # if already active and we only need to change stream, try change with restart decision
        if chat_id in self.active_calls:
            # check queued/current streamtype to decide restart
            prefer_restart = False
            try:
                current = db.get(chat_id) and db.get(chat_id)[0]
                current_type = current.get("streamtype") if current else None
                new_type = "video" if bool(video) else "audio"
                if current_type and str(current_type) != str(new_type):
                    prefer_restart = True
            except Exception:
                prefer_restart = False

            try:
                await _safe_apply_stream(assistant, chat_id, stream, prefer_restart=prefer_restart)
                return
            except Exception:
                pass

        retries = 3
        for attempt in range(retries):
            try:
                await assistant.play(chat_id, stream, config=ksk)
                break
            except NoActiveGroupCall:
                raise AssistantErr(_["call_8"])
            except (NoAudioSourceFound, NoVideoSourceFound):
                # Fallback: try audio-only on last attempt
                if video and attempt == retries - 1:
                    try:
                        stream = dynamic_media_stream(path=final_link, video=False)
                        await assistant.play(chat_id, stream, config=ksk)
                        break
                    except Exception:
                        pass
                raise AssistantErr(_["call_11"])
            except (ConnectionNotFound, TelegramServerError):
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                raise AssistantErr(_["call_10"])
            except Exception as e:
                if "already joined" in str(e).lower() or "active call" in str(e).lower():
                    try:
                        await assistant.change_stream(chat_id, stream)
                        break
                    except Exception:
                        pass
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                raise AssistantErr(f"Error: {e}")

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

            exis = (check[0]).get("old_dur")
            if exis:
                db[chat_id][0]["dur"] = exis
                db[chat_id][0]["seconds"] = check[0].get("old_second")
                db[chat_id][0]["speed_path"] = None
                db[chat_id][0]["speed"] = 1.0

            video = True if str(streamtype) == "video" else False

            async def _play_stream(stream_obj):
                try:
                    # compute if we must force restart (audio<->video)
                    prefer_restart = False
                    try:
                        curr = db.get(chat_id) and db.get(chat_id)[0]
                        curr_type = curr.get("streamtype") if curr else None
                        new_type = "video" if video else "audio"
                        if curr_type and str(curr_type) != str(new_type):
                            prefer_restart = True
                    except Exception:
                        prefer_restart = False

                    if chat_id in self.active_calls and not prefer_restart:
                        await client.change_stream(chat_id, stream_obj)
                    else:
                        # if prefer_restart or not active, use safe apply
                        await _safe_apply_stream(client, chat_id, stream_obj, prefer_restart=prefer_restart)
                except Exception:
                    try:
                        await client.leave_call(chat_id)
                        await asyncio.sleep(0.5)
                        await client.play(chat_id, stream_obj)
                    except Exception:
                        await _clear_(chat_id)
                        return await app.send_message(original_chat_id, text=_["call_6"])

            # Logic starts here
            try:
                final_link = queued
                vid_id = extract_video_id(str(queued)) or videoid

                # invalidate direct cache for vid before resolving to force fresh type URL
                await _invalidate_direct_cache_for_vid(vid_id)

                # QUEUE SMART CHECK: cached local audio but video requested
                if queued and os.path.exists(str(queued)) and video:
                    if str(queued).endswith((".mp3", ".m4a", ".flac", ".opus")):
                        if vid_id:
                            try:
                                direct_url = await get_direct_link(vid_id, video=True)
                                if direct_url:
                                    final_link = direct_url
                            except Exception:
                                pass

                # Live / vid / index prefixes
                if queued and ("live_" in str(queued) or "vid_" in str(queued) or "index_" in str(queued)):
                    try:
                        if vid_id:
                            direct_url = await get_direct_link(vid_id, video=video)
                            if direct_url:
                                final_link = direct_url
                            else:
                                try:
                                    # Attempt YouTube.download fallback
                                    path, direct = await YouTube.download(
                                        vid_id,
                                        None,
                                        video=video,
                                        videoid=vid_id
                                    )
                                    if path:
                                        final_link = path
                                except Exception:
                                    pass
                    except Exception:
                        pass

                stream = dynamic_media_stream(path=final_link, video=video)
                await _play_stream(stream)

                img = await get_thumb(videoid)
                button = stream_markup(_, chat_id)

                try:
                    mystic_msg = db[chat_id][0].get("mystic")
                    if mystic_msg:
                        try:
                            await mystic_msg.delete()
                        except Exception:
                            pass
                except Exception:
                    pass

                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{videoid}",
                        title[:23],
                        check[0].get("dur"),
                        user,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"

            except Exception:
                LOGGER(__name__).error(f"💣 [PLAY ERROR] Chat: {chat_id}\n{traceback.format_exc()}")
                await _clear_(chat_id)
                try:
                    await client.leave_call(chat_id)
                except Exception:
                    pass
                return await app.send_message(original_chat_id, text=_["call_6"])

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients...")
        if self.one and config.STRING1:
            await self.one.start()
        if self.two and config.STRING2:
            await self.two.start()
        if self.three and config.STRING3:
            await self.three.start()
        if self.four and config.STRING4:
            await self.four.start()
        if self.five and config.STRING5:
            await self.five.start()

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if self.one and config.STRING1:
            pings.append(self.one.ping)
        if self.two and config.STRING2:
            pings.append(self.two.ping)
        if self.three and config.STRING3:
            pings.append(self.three.ping)
        if self.four and config.STRING4:
            pings.append(self.four.ping)
        if self.five and config.STRING5:
            pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    @capture_internal_err
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        CRITICAL = (ChatUpdate.Status.KICKED | ChatUpdate.Status.LEFT_GROUP | ChatUpdate.Status.CLOSED_VOICE_CHAT)

        async def unified_update_handler(client, update: Update) -> None:
            try:
                if isinstance(update, StreamEnded):
                    # StreamEnded.stream_type may be enum or int - compare safely
                    try:
                        if update.stream_type == StreamEnded.Type.AUDIO or (hasattr(update.stream_type, "name") and update.stream_type == StreamEnded.Type.AUDIO):
                            assistant = await group_assistant(self, update.chat_id)
                            await self.play(assistant, update.chat_id)
                    except Exception:
                        # fallback: if bitwise flags used
                        try:
                            if update.stream_type & StreamEnded.Type.AUDIO:
                                assistant = await group_assistant(self, update.chat_id)
                                await self.play(assistant, update.chat_id)
                        except Exception:
                            pass

                elif isinstance(update, ChatUpdate):
                    status = update.status
                    if (status & ChatUpdate.Status.LEFT_CALL) or (status & CRITICAL):
                        await self.stop_stream(update.chat_id)
                        return
            except Exception:
                LOGGER(__name__).error("Error in unified_update_handler:\n" + traceback.format_exc())

        for assistant in assistants:
            try:
                # preferred registration: decorator style supported by pytgcalls (on_update returns decorator)
                assistant.on_update()(unified_update_handler)
            except Exception:
                LOGGER(__name__).warning("Failed to register unified_update_handler via on_update(); trying fallback add_handler if available.")
                try:
                    if hasattr(assistant, "add_handler"):
                        # handlers holder style: add_handler(filter, handler) — using internal handlers if present
                        from pytgcalls import filters
                        try:
                            assistant.add_handler(filters.stream_end(StreamEnded.Type.AUDIO), unified_update_handler)
                        except Exception:
                            # final fallback: register raw on_update
                            assistant.on_update()(unified_update_handler)
                except Exception:
                    LOGGER(__name__).error("Failed to register call handlers:\n" + traceback.format_exc())


StreamController = Call()
