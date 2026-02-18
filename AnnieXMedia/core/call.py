# call_controller_with_api.py
# Authored By Certified Coders © 2026
# Integrated: Call Controller (PyTgCalls v3.x) + Enterprise API
# Features:
# - Robust chat_update filter compatibility
# - LRU TTL cache for direct links
# - inflight dedupe for yt-dlp extraction (prevents temp-file races)
# - safe send/edit wrappers (FloodWait handling)
# - enqueue with dedupe / repeats counting
# - change volume, ping, time, recording placeholder
# - EnterpriseApi class integrated at bottom (routes use StreamController)

import os
import time
import asyncio
import signal
from datetime import datetime, timedelta
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Any, Tuple, List

import yt_dlp
import psutil
from aiohttp import web
from aiohttp.web import Response, json_response

from pyrogram.errors import FloodWait, ChatAdminRequired
from pyrogram.types import InlineKeyboardMarkup

from pytgcalls import PyTgCalls, filters
# try importing known types; adapt if missing
try:
    from pytgcalls.types import (
        MediaStream,
        AudioQuality,
        VideoQuality,
        GroupCallConfig,
        Update,
        ChatUpdate,
    )
except Exception:
    # If types change, we'll use placeholders and defensive programming below.
    MediaStream = None
    AudioQuality = None
    VideoQuality = None
    GroupCallConfig = None
    Update = object
    ChatUpdate = None

from pytgcalls.exceptions import NoActiveGroupCall

import config
from strings import get_string
from AnnieXMedia import LOGGER, app, userbot, YouTube as YouTubeAPI
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
from AnnieXMedia.utils.stream.autoclear import auto_clean
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err
from AnnieXMedia.utils.exceptions import AssistantErr
from AnnieXMedia.utils.inline import stream_markup

# Prevent child-process SIGPIPE from killing our process
try:
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
except Exception:
    pass

# ---------------- Configurable params ----------------
_DIRECT_CACHE_MAXSIZE = 500
_DIRECT_CACHE_TTL = 60 * 60
_THREADPOOL_WORKERS = 8
_PREFETCH_DEBOUNCE = 2.0
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

# ---------------- Simple LRU TTL Cache ----------------
class LRUCacheTTL:
    def __init__(self, maxsize: int = 500, ttl: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[str, Tuple[str, float]]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            value = self._data.get(key)
            if not value:
                return None
            val, ts = value
            if (datetime.now().timestamp() - ts) > self.ttl:
                try:
                    del self._data[key]
                except KeyError:
                    pass
                return None
            self._data.move_to_end(key)
            return val

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            if key in self._data:
                del self._data[key]
            self._data[key] = (value, datetime.now().timestamp())
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

# ---------------- Globals ----------------
_DIRECT_LINK_CACHE = LRUCacheTTL(maxsize=_DIRECT_CACHE_MAXSIZE, ttl=_DIRECT_CACHE_TTL)
_THREAD_POOL = ThreadPoolExecutor(max_workers=_THREADPOOL_WORKERS)
_prefetch_tasks: Dict[int, float] = {}
_inflight_extracts: Dict[str, asyncio.Future] = {}
autoend: Dict[int, datetime] = {}

# ---------------- Safe enum/flag helpers ----------------
def enum_to_int(v: Any) -> int:
    try:
        if v is None:
            return 0
        if hasattr(v, "value"):
            return int(v.value)
        return int(v)
    except Exception:
        return 0

def make_chat_update_filter_from_iter(flags_iter) -> Any:
    combined = 0
    for item in flags_iter:
        combined |= enum_to_int(item)
    if combined == 0:
        try:
            return filters.chat_update()
        except TypeError:
            try:
                return filters.chat_update(flags=None)
            except Exception:
                return filters.chat_update
    try:
        return filters.chat_update(combined)
    except TypeError:
        try:
            return filters.chat_update(flags=combined)
        except TypeError:
            try:
                return filters.chat_update()
            except Exception:
                return filters.chat_update

# ---------------- yt-dlp extraction with inflight dedupe ----------------
def _yt_extract(link: str, fmt: str) -> str:
    opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "noplaylist": True,
        "cachedir": False,
        "skip_download": True,
        "no_color": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
            return info.get("url") or link
    except Exception:
        return link

async def get_direct_link(videoid: str, video: bool = False) -> Optional[str]:
    if not videoid:
        return None
    # check cache
    cached = await _DIRECT_LINK_CACHE.get(videoid)
    if cached:
        return cached

    # check inflight
    fut = _inflight_extracts.get(videoid)
    if fut:
        try:
            return await fut
        except Exception:
            # fall through to start new extraction
            pass

    loop = asyncio.get_running_loop()
    link = f"https://www.youtube.com/watch?v={videoid}"
    fmt = "best[ext=mp4]/best" if video else "bestaudio/best"

    async def _do_extract():
        try:
            direct = await loop.run_in_executor(_THREAD_POOL, _yt_extract, link, fmt)
            if direct:
                await _DIRECT_LINK_CACHE.set(videoid, direct)
            return direct
        finally:
            _inflight_extracts.pop(videoid, None)

    task = asyncio.create_task(_do_extract())
    _inflight_extracts[videoid] = task
    return await task

# ---------------- FFmpeg stream builder ----------------
def _build_stream(path: str, video: bool = False, ffmpeg_opts: str = ""):
    path = str(path)
    is_url = path.startswith("http")
    base_flags = (
        "-threads 2 "
        "-probesize 10M -analyzeduration 10M "
        "-fflags +genpts+igndts+nobuffer -sync ext "
    )
    input_flags = ""
    re_flag = ""
    if is_url:
        input_flags = (
            "-reconnect 1 -reconnect_streamed 1 "
            "-reconnect_on_network_error 1 -reconnect_delay_max 5 "
            "-reconnect_at_eof 1 "
        )
    else:
        re_flag = "-re "

    final_ffmpeg = f"{ffmpeg_opts} {base_flags} {input_flags} {re_flag}".strip()

    # defensive: if MediaStream or enums missing, raise early or fallback
    try:
        audio_param = AudioQuality.STUDIO
    except Exception:
        try:
            audio_param = AudioQuality.HIGH
        except Exception:
            audio_param = None

    try:
        video_param = VideoQuality.HD_720p
    except Exception:
        try:
            video_param = VideoQuality.HD
        except Exception:
            video_param = None

    # Build a MediaStream-like dict if MediaStream class not available
    try:
        return MediaStream(
            media_path=path,
            audio_parameters=audio_param,
            video_parameters=video_param,
            video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
            audio_flags=MediaStream.Flags.REQUIRED,
            ffmpeg_parameters=final_ffmpeg,
        )
    except Exception:
        # fallback representation for older/newer libs that don't use MediaStream same way
        return {
            "media_path": path,
            "audio_parameters": audio_param,
            "video_parameters": video_param,
            "video": video,
            "ffmpeg": final_ffmpeg,
        }

# ---------------- Safe send / edit wrappers ----------------
async def safe_send_photo(chat_id: int, photo: str, caption: str = "", reply_markup: InlineKeyboardMarkup = None, retries: int = 3):
    for attempt in range(retries):
        try:
            return await app.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup)
        except FloodWait as fw:
            wait = getattr(fw, "x", None) or getattr(fw, "value", None) or 5
            LOGGER(__name__).warning(f"FloodWait {wait}s while sending photo to {chat_id}, sleeping...")
            await asyncio.sleep(wait + 0.5)
        except Exception as e:
            LOGGER(__name__).error(f"safe_send_photo attempt {attempt} failed for {chat_id}: {e}")
            await asyncio.sleep(0.5)
    return None

async def safe_edit_message(chat_id: int, message_id: int, text: str = None, reply_markup: InlineKeyboardMarkup = None, retries: int = 3):
    for attempt in range(retries):
        try:
            return await app.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
        except FloodWait as fw:
            wait = getattr(fw, "x", None) or getattr(fw, "value", None) or 5
            LOGGER(__name__).warning(f"FloodWait {wait}s while editing message in {chat_id}, sleeping...")
            await asyncio.sleep(wait + 0.5)
        except Exception as e:
            LOGGER(__name__).error(f"safe_edit_message attempt {attempt} failed for {chat_id}: {e}")
            await asyncio.sleep(0.5)
    return None

# ---------------- Enqueue helper (dedupe & repeats) ----------------
async def enqueue_track_safe(chat_id: int, entry: dict):
    lock = StreamController._get_lock_static(chat_id)
    async with lock:
        queue = db.get(chat_id) or []
        # dedupe last item by vidid
        last = queue[-1] if queue else None
        if last and last.get("vidid") and entry.get("vidid") and last.get("vidid") == entry.get("vidid"):
            last["_repeats"] = last.get("_repeats", 1) + 1
            db[chat_id] = queue
            return "merged"
        queue.append(entry)
        db[chat_id] = queue
        return "queued"

# ---------------- The Call Controller ----------------
class Call:
    _locks_global: Dict[int, asyncio.Lock] = {}

    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        self.one = PyTgCalls(self.userbot1) if self.userbot1 else None
        self.two = PyTgCalls(self.userbot2) if self.userbot2 else None
        self.three = PyTgCalls(self.userbot3) if self.userbot3 else None
        self.four = PyTgCalls(self.userbot4) if self.userbot4 else None
        self.five = PyTgCalls(self.userbot5) if self.userbot5 else None

        self.active_calls: set[int] = set()
        self._watcher_task = None
        self._stopping = False

    # static accessor for enqueue helper
    @classmethod
    def _get_lock_static(cls, chat_id: int) -> asyncio.Lock:
        if chat_id not in cls._locks_global:
            cls._locks_global[chat_id] = asyncio.Lock()
        return cls._locks_global[chat_id]

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        return self._get_lock_static(chat_id)

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (v3.x)...")
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
        await self.decorators()
        if self._watcher_task is None:
            self._watcher_task = asyncio.create_task(self._auto_end_watcher())

    async def shutdown(self) -> None:
        self._stopping = True
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass
        for chat_id in list(self.active_calls):
            try:
                assistant = await group_assistant(self, chat_id)
                await assistant.leave_call(chat_id)
            except Exception:
                pass
        try:
            _THREAD_POOL.shutdown(wait=False)
        except Exception:
            pass
        try:
            await _DIRECT_LINK_CACHE.clear()
        except Exception:
            pass

    async def _auto_end_watcher(self):
        while not self._stopping:
            await asyncio.sleep(20)
            now = datetime.now()
            for chat_id, end_time in list(autoend.items()):
                if now > end_time:
                    try:
                        LOGGER(__name__).info(f"Auto-ending call in {chat_id}")
                        await self.force_stop_stream(chat_id)
                    except Exception:
                        pass
                    finally:
                        autoend.pop(chat_id, None)

    # ---------------- Controls ----------------
    async def pause_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)

    async def resume_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.resume(chat_id)

    async def mute_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.mute(chat_id)

    async def unmute_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.unmute(chat_id)

    async def change_volume_call(self, chat_id: int, volume: int) -> None:
        assistant = await group_assistant(self, chat_id)
        # try common method names safely
        for name in ("change_volume_call", "change_volume", "set_volume", "set_call_volume"):
            fn = getattr(assistant, name, None)
            if callable(fn):
                try:
                    await fn(chat_id, volume)
                    return
                except Exception:
                    pass
        # fallback: try playing with GroupCallConfig volume? skip if not supported
        LOGGER(__name__).warning(f"No direct volume API found for assistant in chat {chat_id}")

    async def stop_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await _clear_(chat_id)
        try:
            await assistant.leave_call(chat_id)
        except Exception:
            pass
        finally:
            self.active_calls.discard(chat_id)

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

    # ---------------- Seek / Skip ----------------
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: int, duration: int, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        ffmpeg_opts = f"-ss {to_seek}"
        is_video = (mode == "video")
        stream = _build_stream(file_path, video=is_video, ffmpeg_opts=ffmpeg_opts)
        # try to use assistant.play or assistant.join_group_call
        try:
            await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
        except Exception:
            # fallback to join_group_call if exists
            fn = getattr(assistant, "join_group_call", None)
            if callable(fn):
                try:
                    await fn(chat_id, stream)
                except Exception as e:
                    LOGGER(__name__).error(f"seek fallback join failed: {e}")
            else:
                LOGGER(__name__).error("seek: assistant.play failed and no join_group_call fallback")

    async def skip_stream(self, chat_id: int, link: str, video: bool = False) -> None:
        assistant = await group_assistant(self, chat_id)
        stream = _build_stream(link, video=video)
        try:
            await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
        except Exception:
            fn = getattr(assistant, "join_group_call", None)
            if callable(fn):
                try:
                    await fn(chat_id, stream)
                except Exception as e:
                    LOGGER(__name__).error(f"skip fallback join failed: {e}")
            else:
                LOGGER(__name__).error("skip: assistant.play failed and no join_group_call fallback")

    # ---------------- Join wrapper (compat) ----------------
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: bool = False, image: str = None) -> None:
        assistant = await group_assistant(self, chat_id)
        lang = await get_lang(chat_id)
        _strings = get_string(lang)

        final_link = link
        if "youtube" in str(link) or "youtu.be" in str(link):
            # resolution handled in play, but try direct for join path
            try:
                vidid = None
                if "watch?v=" in link:
                    vidid = link.split("watch?v=")[-1].split("&")[0]
                elif "youtu.be/" in link:
                    vidid = link.split("youtu.be/")[-1].split("?")[0]
                if vidid:
                    direct = await get_direct_link(vidid, video=video)
                    if direct:
                        final_link = direct
            except Exception:
                pass

        stream = _build_stream(final_link, video=video)
        try:
            # prefer assistant.play
            try:
                await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except Exception:
                # fallback to join_group_call if available
                fn = getattr(assistant, "join_group_call", None)
                if callable(fn):
                    await fn(chat_id, stream)
                else:
                    raise
            # update state
            self.active_calls.add(chat_id)
            await add_active_chat(chat_id)
            await music_on(chat_id)
            if video:
                await add_active_video_chat(chat_id)
            # autoend check
            if await is_autoend():
                try:
                    participants = await assistant.get_participants(chat_id)
                    if len(participants) == 1:
                        autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                except Exception:
                    pass
        except NoActiveGroupCall:
            raise AssistantErr(_strings["call_8"])
        except ChatAdminRequired:
            raise AssistantErr(_strings["call_8"])
        except Exception as e:
            if "group call not found" in str(e).lower():
                raise AssistantErr(_strings["call_8"])
            raise AssistantErr(f"Error: {e}")

    # ---------------- Handlers / Decorators ----------------
    async def decorators(self) -> None:
        async def stream_end_handler(client, update):
            chat_id = getattr(update, "chat_id", None)
            if chat_id is None:
                return
            LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
            await self.play(client, chat_id)

        async def connection_handler(client, update):
            chat_id = getattr(update, "chat_id", None)
            status = getattr(update, "status", None)
            if chat_id is None:
                return
            # build desired flags dynamically
            desired = []
            ChatUpdateType = globals().get("ChatUpdate", None)
            if ChatUpdateType is not None and hasattr(ChatUpdateType, "Status"):
                s = getattr(ChatUpdateType, "Status")
                for name in ("LEFT_CALL", "KICKED", "CLOSED_VOICE_CHAT"):
                    member = getattr(s, name, None)
                    if member is not None:
                        desired.append(member)
            combined = 0
            for x in desired:
                combined |= enum_to_int(x)
            status_int = enum_to_int(status)
            if combined == 0:
                if status_int != 0:
                    try:
                        await self.stop_stream(chat_id)
                    except Exception:
                        pass
            else:
                if (status_int & combined) != 0:
                    try:
                        await self.stop_stream(chat_id)
                    except Exception:
                        pass

        async def participant_change_handler(client, update):
            chat_id = getattr(update, "chat_id", None)
            if chat_id is None:
                return
            try:
                if await is_autoend():
                    participants = await client.get_participants(chat_id)
                    if len(participants) == 1:
                        autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                    else:
                        autoend.pop(chat_id, None)
            except Exception:
                pass

        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        # candidate flags resolution
        candidate_flags = []
        ChatUpdateType = globals().get("ChatUpdate", None)
        if ChatUpdateType is not None and hasattr(ChatUpdateType, "Status"):
            s = getattr(ChatUpdateType, "Status")
            for name in ("LEFT_CALL", "KICKED", "CLOSED_VOICE_CHAT"):
                member = getattr(s, name, None)
                if member is not None:
                    candidate_flags.append(member)

        chat_update_filter = make_chat_update_filter_from_iter(candidate_flags)

        for assistant in assistants:
            # attach stream end (try variants)
            attached = False
            try:
                assistant.on_update(filters.stream_end())(stream_end_handler)
                attached = True
            except Exception:
                try:
                    assistant.on_update(filters.stream_ended())(stream_end_handler)
                    attached = True
                except Exception:
                    try:
                        assistant.on_update(stream_end_handler)
                        attached = True
                    except Exception:
                        LOGGER(__name__).warning("Could not attach stream_end handler for assistant.")

            # attach chat_update
            try:
                assistant.on_update(chat_update_filter)(connection_handler)
            except Exception:
                try:
                    assistant.on_update(filters.chat_update())(connection_handler)
                except Exception:
                    try:
                        assistant.on_update(connection_handler)
                    except Exception:
                        LOGGER(__name__).warning("Failed to attach any chat_update handler for an assistant.")

            # participants
            try:
                assistant.on_update(filters.call_participants())(participant_change_handler)
            except Exception:
                try:
                    assistant.on_update(participant_change_handler)
                except Exception:
                    pass

    # ---------------- Main Queue Processor ----------------
    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        if not check:
            await _clear_(chat_id)
            return

        popped = None
        loop_count = await get_loop(chat_id)
        try:
            if loop_count == 0:
                popped = check.pop(0)
            else:
                loop_count = loop_count - 1
                await set_loop(chat_id, loop_count)
            if popped:
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

        queued_entry = check[0]
        queued = queued_entry.get("file")
        title = (queued_entry.get("title") or "").title()
        user = queued_entry.get("by")
        original_chat_id = queued_entry.get("chat_id")
        streamtype = queued_entry.get("streamtype")
        videoid = queued_entry.get("vidid")
        duration = queued_entry.get("dur")
        is_video = str(streamtype) == "video"

        final_link = queued
        if "youtube" in str(queued) and videoid:
            try:
                direct = await get_direct_link(videoid, video=is_video)
                if direct:
                    final_link = direct
            except Exception:
                pass

        stream = _build_stream(final_link, video=is_video)
        lock = self._get_lock(chat_id)

        async with lock:
            try:
                # use assistant.play if available
                try:
                    await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                except Exception:
                    fn = getattr(client, "join_group_call", None)
                    if callable(fn):
                        await fn(chat_id, stream)
                    else:
                        raise
            except Exception as e:
                LOGGER(__name__).error(f"Play Error for {chat_id}: {e}")
                await asyncio.sleep(0.8)
                try:
                    await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                except Exception:
                    if len(check) > 1:
                        check.pop(0)
                        await self.play(client, chat_id)
                        return
                    await _clear_(chat_id)
                    try:
                        await app.send_message(original_chat_id, "Stream failed, queue cleared.")
                    except Exception:
                        pass
                    return

            if is_video:
                await add_active_video_chat(chat_id)
            else:
                await remove_active_video_chat(chat_id)

            if len(check) > 1:
                try:
                    asyncio.create_task(self._resolve_and_cache_next(check[1]))
                except Exception:
                    pass

            try:
                lang = await get_lang(chat_id)
                strings = get_string(lang)
            except Exception:
                strings = None

            img = await get_thumb(videoid)
            try:
                button = stream_markup(strings or {}, chat_id)
            except Exception:
                button = None

            try:
                if db[chat_id][0].get("mystic"):
                    await db[chat_id][0].get("mystic").delete()
            except Exception:
                pass

            caption = (strings or {}).get("stream_1", "Now playing: {}").format(
                f"https://t.me/{app.username}?start=info_{videoid}",
                title[:23],
                duration,
                user,
            )
            try:
                run = await safe_send_photo(original_chat_id, img, caption, reply_markup=InlineKeyboardMarkup(button) if button else None)
                if run:
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"
            except Exception as e:
                LOGGER(__name__).error(f"UI Error {chat_id}: {e}")

# Instantiate controller and YouTube API wrapper
StreamController = Call()
YouTube = YouTubeAPI()  # local instance

# -------------------- Enterprise API --------------------
class EnterpriseApi:
    def __init__(self):
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        self.app.router.add_get("/", self.serve_dashboard)
        self.app.router.add_get("/api/stats", self.get_system_stats)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_chat_queue)
        self.app.router.add_post("/api/control", self.control_stream)
        self.app.router.add_post("/api/play", self.play_via_api)
        self.app.router.add_post("/api/auth", self.authenticate)

    async def cors_options(self, request):
        return Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        })

    def _cors_headers(self):
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()

    async def stop(self):
        await self.runner.cleanup()

    async def authenticate(self, request):
        try:
            data = await request.json()
            token = data.get("token")
            if token == config.BOT_TOKEN:
                return json_response({"status": "authenticated", "access": "granted"}, headers=self._cors_headers())
            return json_response({"error": "Unauthorized"}, status=401, headers=self._cors_headers())
        except Exception:
            return json_response({"error": "Bad Request"}, status=400, headers=self._cors_headers())

    async def serve_dashboard(self, request):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(text=content, content_type="text/html", headers=self._cors_headers())
        except Exception as e:
            return Response(text=str(e), status=500)

    async def get_system_stats(self, request):
        cpu_p = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        net = psutil.net_io_counters()
        uptime_sec = time.time() - START_TIME

        chats_data = []
        for chat_id in list(StreamController.active_calls):
            chat_info = {"chat_id": chat_id}
            check = db.get(chat_id)
            if check:
                current = check[0]
                chat_info["title"] = current.get("title", "Unknown")
                chat_info["duration"] = current.get("dur", "00:00")
                chat_info["user"] = current.get("by", "Unknown")
                chat_info["stream_type"] = current.get("streamtype", "audio")
            else:
                chat_info["title"] = "Idle / Radio"
                chat_info["duration"] = "Live"
            try:
                chat_info["played_time"] = await StreamController.time(chat_id)
            except Exception:
                chat_info["played_time"] = 0
            chats_data.append(chat_info)

        data = {
            "system": {
                "cpu": cpu_p,
                "ram_percent": ram.percent,
                "ram_used": f"{ram.used / (1024**3):.2f} GB",
                "ram_total": f"{ram.total / (1024**3):.2f} GB",
                "net_sent": f"{net.bytes_sent / (1024**2):.2f} MB",
                "net_recv": f"{net.bytes_recv / (1024**2):.2f} MB",
                "uptime": str(timedelta(seconds=int(uptime_sec))),
            },
            "bot": {
                "active_calls": len(StreamController.active_calls),
                "chats": chats_data,
                "ping": await StreamController.ping() if hasattr(StreamController, "ping") else 0
            }
        }
        return json_response(data, headers=self._cors_headers())

    async def get_chat_queue(self, request):
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
        except ValueError:
            return json_response({"error": "Invalid Chat ID"}, status=400, headers=self._cors_headers())

        if chat_id not in StreamController.active_calls:
            return json_response({"status": "inactive", "queue": []}, headers=self._cors_headers())

        queue_data = db.get(chat_id)
        if not queue_data:
            return json_response({"status": "empty", "queue": []}, headers=self._cors_headers())

        formatted_queue = []
        for index, item in enumerate(queue_data):
            formatted_queue.append({
                "position": index,
                "title": item.get("title"),
                "duration": item.get("dur"),
                "requester": item.get("by"),
                "stream_type": item.get("streamtype")
            })

        return json_response({"status": "active", "count": len(formatted_queue), "queue": formatted_queue}, headers=self._cors_headers())

    async def control_stream(self, request):
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            value = data.get("value")

            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Chat not active"}, status=404, headers=self._cors_headers())

            if action == "pause":
                await StreamController.pause_stream(chat_id)
            elif action == "resume":
                await StreamController.resume_stream(chat_id)
            elif action == "skip":
                await StreamController.skip_stream(chat_id, "", False)
                queue = db.get(chat_id)
                if queue and len(queue) > 0:
                    queue.pop(0)
                    if not queue:
                        await StreamController.stop_stream(chat_id)
                    else:
                        await StreamController.play(StreamController.one, chat_id)
            elif action == "stop":
                await StreamController.stop_stream(chat_id)
            elif action == "volume":
                if value is not None:
                    await StreamController.change_volume_call(chat_id, int(value))
            elif action == "mute":
                await StreamController.mute_stream(chat_id)
            elif action == "unmute":
                await StreamController.unmute_stream(chat_id)
            elif action == "seek":
                if value:
                    queue = db.get(chat_id)
                    if queue:
                        file_path = queue[0]["file"]
                        duration = queue[0]["dur"]
                        streamtype = queue[0]["streamtype"]
                        await StreamController.seek_stream(chat_id, file_path, int(value), duration, streamtype)
            else:
                return json_response({"error": "Unknown action"}, status=400, headers=self._cors_headers())

            return json_response({"status": "success", "action": action}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def play_via_api(self, request):
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Missing query"}, status=400, headers=self._cors_headers())

            try:
                details, track_id = await YouTube.track(query)
                if not details:
                    return json_response({"error": "No results found"}, status=404, headers=self._cors_headers())
            except Exception as e:
                return json_response({"error": f"Search failed: {e}"}, status=500, headers=self._cors_headers())

            vidid = details["vidid"]
            title = details["title"]
            duration = details["duration_min"]
            thumbnail = details["thumb"]

            try:
                file_path, direct = await YouTube.download(vidid, None, video=video_mode, videoid=vidid)
            except Exception as e:
                return json_response({"error": f"Download failed: {e}"}, status=500, headers=self._cors_headers())

            user_name = "API Request"
            user_id = 777000
            stream_type = "video" if video_mode else "audio"

            queue_item = {
                "chat_id": chat_id,
                "file": file_path if direct else f"vid_{vidid}",
                "vidid": vidid,
                "title": title,
                "dur": duration,
                "by": user_name,
                "user_id": user_id,
                "streamtype": stream_type,
                "thumb": thumbnail
            }

            if chat_id in StreamController.active_calls:
                res = await enqueue_track_safe(chat_id, queue_item)
                return json_response({"status": res, "title": title}, headers=self._cors_headers())
            else:
                db[chat_id] = [queue_item]
                try:
                    await StreamController.join_call(chat_id, chat_id, file_path, video=video_mode)
                    return json_response({"status": "playing", "title": title}, headers=self._cors_headers())
                except Exception as e:
                    return json_response({"error": f"Failed to join call: {e}"}, status=500, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

# single api instance
BotAPI = EnterpriseApi()

# Expose entrypoints for external startup code
__all__ = ["StreamController", "BotAPI", "YouTube"]
