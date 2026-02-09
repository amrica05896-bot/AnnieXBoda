# Authored By Certified Coders © 2026
# System: Call Controller (Custom PyTgCalls Implementation)
# Updated: optimized for performance, safety, and compatibility with rest of repo

import asyncio
import os
import re
import traceback
import yt_dlp
from datetime import datetime, timedelta
from typing import Union, Optional, Dict, Any, List

from ntgcalls import TelegramServerError, ConnectionNotFound
from pyrogram import Client
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

# Local concurrency primitives
_locks: Dict[int, asyncio.Lock] = {}

autoend: Dict[int, datetime] = {}
counter: Dict[int, Dict[str, Any]] = {}

# --- [1] Helpers ---


def clean_vidid(vid: Optional[Union[str, bool]]) -> Optional[str]:
    if vid is None or vid is True or vid is False:
        return None
    return str(vid)


def extract_video_id(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    # Handle typical youtube links and short links
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)"
    match = re.search(pattern, url)
    return match.group(1) if match else None


async def _ydl_extract_info(link: str, opts: dict) -> Optional[dict]:
    """
    Run yt_dlp.extract_info in executor and return info dict or None on error.
    """
    loop = asyncio.get_running_loop()

    def _extract():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(link, download=False)
        except Exception:
            return None

    return await loop.run_in_executor(None, _extract)


def _choose_best_format(info: dict, video: bool) -> Optional[str]:
    """
    Given yt_dlp info dict, choose the best direct URL for audio or video.
    Preference:
     - video=True: prefer formats with both audio & video; fallback to video-only or audio-only
     - video=False: prefer audio-only formats
    Returns direct format 'url' or None.
    """
    if not info:
        return None
    # direct url (sometimes provided at top-level)
    top_url = info.get("url")
    if top_url and not info.get("formats"):
        return top_url

    formats: List[dict] = info.get("formats") or []
    if not formats:
        return top_url

    try:
        if video:
            # Prefer combined formats (vcodec != 'none' and acodec != 'none'), highest resolution/bitrate
            combined = [
                f
                for f in formats
                if f.get("vcodec") and f.get("vcodec") != "none" and f.get("acodec") and f.get("acodec") != "none"
            ]
            if combined:
                # sort by height then by tbr/abr
                combined.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0, x.get("abr") or 0), reverse=True)
                return combined[0].get("url")
            # fallback to best video-only with highest height
            video_only = [f for f in formats if f.get("vcodec") and f.get("vcodec") != "none"]
            if video_only:
                video_only.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
                return video_only[0].get("url")
            # final fallback to best audio
            audio = [f for f in formats if f.get("acodec") and f.get("acodec") != "none"]
            if audio:
                audio.sort(key=lambda x: (x.get("abr") or x.get("tbr") or 0), reverse=True)
                return audio[0].get("url")
        else:
            # audio desired: prefer audio-only formats (acodec != 'none')
            audio = [f for f in formats if f.get("acodec") and f.get("acodec") != "none"]
            if audio:
                audio.sort(key=lambda x: (x.get("abr") or x.get("tbr") or 0), reverse=True)
                return audio[0].get("url")
            # fallback to combined formats if no pure audio
            combined = [f for f in formats if (f.get("vcodec") and f.get("vcodec") != "none")]
            if combined:
                combined.sort(key=lambda x: (x.get("abr") or x.get("tbr") or 0), reverse=True)
                return combined[0].get("url")
    except Exception:
        LOGGER(__name__).warning("Failed to choose best format from yt_dlp info", exc_info=True)
    return top_url


async def get_direct_link(videoid: str, video: bool = False) -> Optional[str]:
    """
    Get a direct playable url from yt_dlp for a given youtube id.
    Returns None if cannot resolve.
    """
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
        # Do not auto-download; we only want URLs
        "skip_download": True,
        # reduce logging noise
        "logger": yt_dlp.utils.std_logger,
    }
    try:
        info = await _ydl_extract_info(link, opts)
        url = _choose_best_format(info or {}, video)
        # return url if possible, otherwise fallback to watch link
        return url or link
    except Exception:
        LOGGER(__name__).warning("get_direct_link failed", exc_info=True)
        return link


def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: Optional[str] = None) -> MediaStream:
    """
    Build MediaStream with tuned ffmpeg flags. Keep parameters compact and fast.
    """
    if not path:
        path = ""
    path = str(path)
    is_url = path.startswith("http")

    if not is_url and path.endswith((".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus")):
        video = False

    if is_url:
        titan_flags = (
            "-threads 4 "
            "-probesize 10M "
            "-analyzeduration 10M "
            "-rtbufsize 15M "
            "-reconnect 1 "
            "-reconnect_streamed 1 "
            "-reconnect_on_network_error 1 "
            "-reconnect_delay_max 5 "
            "-fflags +genpts+igndts+nobuffer "
            "-sync ext"
        )
    else:
        titan_flags = (
            "-threads 4 "
            "-probesize 10M "
            "-analyzeduration 10M "
            "-fflags +genpts+igndts+nobuffer "
            "-sync ext"
        )

    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.HD_720p,
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=titan_flags,
    )


async def _clear_(chat_id: int) -> None:
    """
    Clear queue, cleanup thumbnails/messages, and reset db state for chat.
    Protected by lock for race-safety.
    """
    lock = _locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        try:
            popped = db.pop(chat_id, None)
            if popped:
                try:
                    await auto_clean(popped)
                except Exception:
                    LOGGER(__name__).warning("auto_clean failed", exc_info=True)
            db[chat_id] = []
            await remove_active_video_chat(chat_id)
            await remove_active_chat(chat_id)
            await set_loop(chat_id, 0)
        except Exception:
            LOGGER(__name__).error(f"Error clearing chat {chat_id}\n{traceback.format_exc()}")


# --- [2] Call Controller ---


class Call:
    def __init__(self):
        self.userbot1 = userbot.one
        self.userbot2 = userbot.two
        self.userbot3 = userbot.three
        self.userbot4 = userbot.four
        self.userbot5 = userbot.five

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
            LOGGER(__name__).debug(f"resume failed, trying unmute for chat {chat_id}", exc_info=True)
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
            LOGGER(__name__).debug(f"leave_call failed during stop_stream for chat {chat_id}", exc_info=True)
        finally:
            self.active_calls.discard(chat_id)

    @capture_internal_err
    async def force_stop_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        lock = _locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            try:
                check = db.get(chat_id)
                if check:
                    check.pop(0)
            except (IndexError, KeyError, Exception):
                pass
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except Exception:
            LOGGER(__name__).debug(f"leave_call failed during force_stop for chat {chat_id}", exc_info=True)
        finally:
            self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        if not link:
            try:
                check = db.get(chat_id)
                if check:
                    link = check[0].get("file")
            except Exception:
                LOGGER(__name__).debug("skip_stream: failed reading db", exc_info=True)
            if not link:
                return

        final_link = link
        vid_id = extract_video_id(str(link))

        try:
            # Local file and request for video -> try direct from yt_dlp if vid_id present
            if os.path.exists(str(link)) and video:
                if str(link).endswith((".mp3", ".m4a", ".flac", ".opus")) and vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=True)
                        if direct:
                            final_link = direct
                    except Exception:
                        LOGGER(__name__).debug("skip_stream: get_direct_link failed", exc_info=True)

            elif link and ("youtube" in str(link) or "youtu.be" in str(link)):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=bool(video))
                        if direct:
                            final_link = direct
                    except Exception:
                        LOGGER(__name__).debug("skip_stream: get_direct_link failed for youtube", exc_info=True)
        except Exception:
            LOGGER(__name__).warning("skip_stream pre-processing error", exc_info=True)

        stream = dynamic_media_stream(path=final_link, video=bool(video))

        # Use play; if already exists attempt fallback config
        if chat_id in self.active_calls:
            try:
                await assistant.play(chat_id, stream)
            except Exception:
                LOGGER(__name__).debug("skip_stream: play failed, trying fallback config", exc_info=True)
                try:
                    await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=False))
                except Exception:
                    LOGGER(__name__).warning("skip_stream: fallback play failed", exc_info=True)
        else:
            try:
                await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=False))
            except Exception as e:
                LOGGER(__name__).error(f"skip_stream: failed to start play for chat {chat_id}: {e}", exc_info=True)

    @capture_internal_err
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: str, duration: str, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        ffmpeg_params = f"-ss {to_seek} -to {duration}"
        is_video = mode == "video"
        stream = dynamic_media_stream(path=file_path, video=is_video, ffmpeg_params=ffmpeg_params)
        await assistant.play(chat_id, stream)

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
            # compute video pts multiplier
            vs = str(2.0 / float(speed))
            # build ffmpeg args safely (no shell)
            ffmpeg_args = [
                "ffmpeg",
                "-i",
                file_path,
                "-filter:v",
                f"setpts={vs}*PTS",
                "-filter:a",
                f"atempo={speed}",
                "-y",
                out,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(*ffmpeg_args, stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()
            except Exception:
                LOGGER(__name__).error("speedup_stream ffmpeg failed", exc_info=True)
                raise AssistantErr("FFmpeg processing failed for speed change.")
        try:
            dur = int(await asyncio.get_event_loop().run_in_executor(None, check_duration, out))
        except Exception:
            LOGGER(__name__).warning("speedup_stream: failed to get duration", exc_info=True)
            dur = 0
        played, con_seconds = speed_converter(playing[0].get("played", 0), speed)
        duration_min = seconds_to_min(dur)
        is_video = playing[0].get("streamtype") == "video"
        ffmpeg_params = f"-ss {played} -to {duration_min}"
        stream = dynamic_media_stream(path=out, video=is_video, ffmpeg_params=ffmpeg_params)

        lock = _locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            try:
                if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
                    await assistant.play(chat_id, stream)
                    db[chat_id][0].update({"played": con_seconds, "dur": duration_min, "seconds": dur, "speed_path": out, "speed": speed})
                else:
                    raise AssistantErr("Stream mismatch.")
            except AssistantErr:
                raise
            except Exception:
                LOGGER(__name__).error("speedup_stream failed to update or play", exc_info=True)
                raise AssistantErr("Failed to apply speedup.")

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

        try:
            if os.path.exists(str(link)) and video and str(link).endswith((".mp3", ".m4a", ".flac", ".opus")):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=True)
                        if direct:
                            final_link = direct
                    except Exception:
                        LOGGER(__name__).debug("join_call: get_direct_link failed (local file case)", exc_info=True)

            elif link and ("youtube" in str(link) or "youtu.be" in str(link)):
                if vid_id:
                    try:
                        direct = await get_direct_link(vid_id, video=bool(video))
                        if direct:
                            final_link = direct
                    except Exception:
                        LOGGER(__name__).debug("join_call: get_direct_link failed for youtube", exc_info=True)
        except Exception:
            LOGGER(__name__).warning("join_call pre-processing error", exc_info=True)

        stream = dynamic_media_stream(path=final_link, video=bool(video))
        ksk = GroupCallConfig(auto_start=False)

        if chat_id in self.active_calls:
            try:
                await assistant.play(chat_id, stream)
                return
            except Exception:
                LOGGER(__name__).debug("join_call: already active call play attempt failed, continuing to retry", exc_info=True)

        retries = 3
        for attempt in range(retries):
            try:
                await assistant.play(chat_id, stream, config=ksk)
                break
            except NoActiveGroupCall:
                raise AssistantErr(_["call_8"])
            except (NoAudioSourceFound, NoVideoSourceFound):
                if video and attempt == retries - 1:
                    try:
                        stream = dynamic_media_stream(path=final_link, video=False)
                        await assistant.play(chat_id, stream, config=ksk)
                        break
                    except Exception:
                        LOGGER(__name__).debug("join_call: fallback to audio-only failed", exc_info=True)
                raise AssistantErr(_["call_11"])
            except (ConnectionNotFound, TelegramServerError):
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                raise AssistantErr(_["call_10"])
            except Exception as e:
                msg = str(e).lower()
                if "already joined" in msg or "active call" in msg:
                    try:
                        await assistant.play(chat_id, stream)
                        break
                    except Exception:
                        LOGGER(__name__).debug("join_call: attempted play after 'already joined' message failed", exc_info=True)
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                    continue
                LOGGER(__name__).error(f"join_call final error: {e}", exc_info=True)
                raise AssistantErr(f"Error: {e}")

        self.active_calls.add(chat_id)
        await add_active_chat(chat_id)
        await music_on(chat_id)
        if video:
            await add_active_video_chat(chat_id)

        if await is_autoend():
            counter[chat_id] = {}
            try:
                participants = await assistant.get_participants(chat_id)
                users = len(participants) if participants else 0
                if users == 1:
                    autoend[chat_id] = datetime.now() + timedelta(minutes=1)
            except Exception:
                LOGGER(__name__).debug("join_call: get_participants failed", exc_info=True)

    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        lock = _locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            check = db.get(chat_id)
            popped = None
            loop_val = await get_loop(chat_id)
            try:
                if not check:
                    await _clear_(chat_id)
                    try:
                        return await client.leave_call(chat_id)
                    except Exception:
                        return
                if loop_val == 0:
                    popped = check.pop(0)
                else:
                    loop_val = loop_val - 1
                    await set_loop(chat_id, loop_val)
                try:
                    await auto_clean(popped)
                except Exception:
                    LOGGER(__name__).debug("play: auto_clean failed", exc_info=True)

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
                LOGGER(__name__).warning("play: failed during queue handling", exc_info=True)
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
                        await client.play(chat_id, stream_obj)
                    except Exception:
                        try:
                            await client.leave_call(chat_id)
                            await asyncio.sleep(0.5)
                            await client.play(chat_id, stream_obj)
                        except Exception:
                            await _clear_(chat_id)
                            return await app.send_message(original_chat_id, text=_["call_6"])

                try:
                    final_link = queued
                    vid_id = extract_video_id(str(queued)) or videoid

                    if os.path.exists(str(queued)) and video:
                        if str(queued).endswith((".mp3", ".m4a", ".flac", ".opus")) and vid_id:
                            try:
                                direct_url = await get_direct_link(vid_id, video=True)
                                if direct_url:
                                    final_link = direct_url
                            except Exception:
                                LOGGER(__name__).debug("play: get_direct_link failed for local audio with vid_id", exc_info=True)

                    elif "live_" in queued or "vid_" in queued or "index_" in queued:
                        try:
                            if vid_id:
                                direct_url = await get_direct_link(vid_id, video=video)
                                if direct_url:
                                    final_link = direct_url
                                else:
                                    try:
                                        path, is_direct = await YouTube.download(
                                            f"https://www.youtube.com/watch?v={vid_id}",
                                            None,
                                            video=video,
                                            videoid=vid_id,
                                        )
                                        if path:
                                            final_link = path
                                    except Exception:
                                        LOGGER(__name__).debug("play: YouTube.download fallback failed", exc_info=True)
                        except Exception:
                            LOGGER(__name__).debug("play: error handling live/index/vid", exc_info=True)

                    stream = dynamic_media_stream(path=final_link, video=video)
                    await _play_stream(stream)

                    img = await get_thumb(videoid)
                    button = stream_markup(_, chat_id)

                    try:
                        mystic = db[chat_id][0].get("mystic")
                        if mystic:
                            await mystic.delete()
                    except Exception:
                        LOGGER(__name__).debug("play: clearing previous mystic failed", exc_info=True)

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
        if config.STRING1 and self.one:
            await self.one.start()
        if config.STRING2 and self.two:
            await self.two.start()
        if config.STRING3 and self.three:
            await self.three.start()
        if config.STRING4 and self.four:
            await self.four.start()
        if config.STRING5 and self.five:
            await self.five.start()

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if config.STRING1 and self.one:
            pings.append(self.one.ping)
        if config.STRING2 and self.two:
            pings.append(self.two.ping)
        if config.STRING3 and self.three:
            pings.append(self.three.ping)
        if config.STRING4 and self.four:
            pings.append(self.four.ping)
        if config.STRING5 and self.five:
            pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    @capture_internal_err
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        CRITICAL = (ChatUpdate.Status.KICKED | ChatUpdate.Status.LEFT_GROUP | ChatUpdate.Status.CLOSED_VOICE_CHAT)

        async def unified_update_handler(client, update: Update) -> None:
            try:
                if isinstance(update, StreamEnded):
                    if update.stream_type == StreamEnded.Type.AUDIO:
                        assistant = await group_assistant(self, update.chat_id)
                        await self.play(assistant, update.chat_id)
                elif isinstance(update, ChatUpdate):
                    status = update.status
                    if (status & ChatUpdate.Status.LEFT_CALL) or (status & CRITICAL):
                        await self.stop_stream(update.chat_id)
                        return
            except Exception:
                LOGGER(__name__).warning("decorators unified_update_handler crashed", exc_info=True)

        for assistant in assistants:
            assistant.on_update()(unified_update_handler)


StreamController = Call()
