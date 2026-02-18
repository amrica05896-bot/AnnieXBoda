# Authored By Certified Coders © 2026
# System: Call Controller (PyTgCalls v3.0) - FULL OPTION Edition
# Fixes: robust enum->int flag handling, safe chat_update filter creation, defensive status checks

import asyncio
import os
import signal
from datetime import datetime, timedelta
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Set, Tuple, Any

import yt_dlp
from pyrogram.types import InlineKeyboardMarkup
from pyrogram.errors import ChatAdminRequired

from pytgcalls import PyTgCalls, filters
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality,
    GroupCallConfig,
    Update,
    ChatUpdate,
)
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NotInCallError
)

import config
from strings import get_string
from AnnieXMedia import LOGGER, app, userbot
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

# ignore SIGPIPE to reduce child-process crashes propagation
try:
    import signal as _sig
    _sig.signal(_sig.SIGPIPE, _sig.SIG_IGN)
except Exception:
    pass

# -------------------- Configurable Parameters --------------------
_DIRECT_CACHE_MAXSIZE = 500
_DIRECT_CACHE_TTL = 60 * 60
_THREADPOOL_WORKERS = 8
_PREFETCH_DEBOUNCE = 2.0

# -------------------- Utilities --------------------
class LRUCacheTTL:
    def __init__(self, maxsize: int = 500, ttl: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[str, Tuple[str, float]]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            value = self._data.get(key)
            if not value: return None
            val, ts = value
            if (datetime.now().timestamp() - ts) > self.ttl:
                try: del self._data[key]
                except KeyError: pass
                return None
            self._data.move_to_end(key)
            return val

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            if key in self._data: del self._data[key]
            self._data[key] = (value, datetime.now().timestamp())
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock: self._data.clear()

_DIRECT_LINK_CACHE = LRUCacheTTL(maxsize=_DIRECT_CACHE_MAXSIZE, ttl=_DIRECT_CACHE_TTL)
_THREAD_POOL = ThreadPoolExecutor(max_workers=_THREADPOOL_WORKERS)
_prefetch_tasks: Dict[int, float] = {}
autoend: Dict[int, datetime] = {}

# -------------------- Blocking Extractor --------------------
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
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
            return info.get("url") or link
    except Exception:
        return link

async def get_direct_link(videoid: str, video: bool = False) -> Optional[str]:
    if not videoid: return None
    cached = await _DIRECT_LINK_CACHE.get(videoid)
    if cached: return cached

    link = f"https://www.youtube.com/watch?v={videoid}"
    fmt = "best[ext=mp4]/best" if video else "bestaudio/best"

    loop = asyncio.get_running_loop()
    try:
        direct = await loop.run_in_executor(_THREAD_POOL, _yt_extract, link, fmt)
        if direct: await _DIRECT_LINK_CACHE.set(videoid, direct)
        return direct
    except Exception:
        return link

def _build_stream(path: str, video: bool = False, ffmpeg_opts: str = "") -> MediaStream:
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

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.STUDIO,
        video_parameters=VideoQuality.HD_720p,
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=final_ffmpeg,
    )

async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped:
        try: await auto_clean(popped)
        except: pass
    db[chat_id] = []
    try:
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except: pass

# -------------------- Enum/Flag helpers --------------------
def enum_to_int(v: Any) -> int:
    """
    Safely convert Enum-like or int-like to int for bitmasking.
    Returns 0 on failure.
    """
    try:
        if v is None:
            return 0
        # If Enum with .value
        if hasattr(v, "value"):
            return int(v.value)
        # If IntFlag class itself passed (not instance), try to convert to int
        if hasattr(v, "__int__"):
            return int(v)
        # Last resort: try int()
        return int(v)
    except Exception:
        return 0

def make_chat_update_filter_from_iter(flags_iter) -> Any:
    """
    Build a compatible filters.chat_update(...) with a combined integer flag.
    Accepts iterable of enum members / ints.
    """
    combined = 0
    for item in flags_iter:
        try:
            combined |= enum_to_int(item)
        except Exception:
            pass

    # If nothing to pass, try default call
    if combined == 0:
        try:
            return filters.chat_update()
        except TypeError:
            try:
                return filters.chat_update(flags=None)
            except Exception:
                return filters.chat_update

    # Try positional then keyword, then fallback
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

# -------------------- Controller Class --------------------
class Call:
    def __init__(self):
        self.userbot1 = getattr(userbot, "one", None)
        self.userbot2 = getattr(userbot, "two", None)
        self.userbot3 = getattr(userbot, "three", None)
        self.userbot4 = getattr(userbot, "four", None)
        self.userbot5 = getattr(userbot, "five", None)

        # Clients Initialization with potential CustomAPI placeholders
        self.one = PyTgCalls(self.userbot1) if self.userbot1 else None
        self.two = PyTgCalls(self.userbot2) if self.userbot2 else None
        self.three = PyTgCalls(self.userbot3) if self.userbot3 else None
        self.four = PyTgCalls(self.userbot4) if self.userbot4 else None
        self.five = PyTgCalls(self.userbot5) if self.userbot5 else None

        self.active_calls: Set[int] = set()
        self._locks: Dict[int, asyncio.Lock] = {}
        self._watcher_task: Optional[asyncio.Task] = None
        self._stopping = False

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    async def _resolve_and_cache_next(self, queued_entry: dict):
        try:
            queued_file = queued_entry.get("file")
            vidid = queued_entry.get("vidid")
            is_video = str(queued_entry.get("streamtype")) == "video"
            if vidid and "youtube" in str(queued_file):
                chat_id = queued_entry.get("chat_id") or 0
                last = _prefetch_tasks.get(chat_id)
                now = datetime.now().timestamp()
                if last and (now - last) < _PREFETCH_DEBOUNCE:
                    return
                _prefetch_tasks[chat_id] = now
                await get_direct_link(vidid, video=is_video)
        except: pass

    async def _auto_end_watcher(self):
        while not self._stopping:
            await asyncio.sleep(20)
            now = datetime.now()
            for chat_id, end_time in list(autoend.items()):
                if now > end_time:
                    try:
                        LOGGER(__name__).info(f"Auto-ending call in {chat_id}")
                        await self.force_stop_stream(chat_id)
                    except: pass
                    finally:
                        autoend.pop(chat_id, None)

    # -------------------- Lifecycle --------------------
    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (v3.0 - Full Option)...")
        if self.one and config.STRING1: await self.one.start()
        if self.two and config.STRING2: await self.two.start()
        if self.three and config.STRING3: await self.three.start()
        if self.four and config.STRING4: await self.four.start()
        if self.five and config.STRING5: await self.five.start()

        await self.decorators()

        if self._watcher_task is None:
            self._watcher_task = asyncio.create_task(self._auto_end_watcher())

    async def shutdown(self) -> None:
        self._stopping = True
        if self._watcher_task:
            self._watcher_task.cancel()
            try: await self._watcher_task
            except asyncio.CancelledError: pass

        for chat_id in list(self.active_calls):
            try:
                assistant = await group_assistant(self, chat_id)
                await assistant.leave_call(chat_id)
            except: pass

        try: _THREAD_POOL.shutdown(wait=False)
        except: pass
        try: await _DIRECT_LINK_CACHE.clear()
        except: pass

    # -------------------- Full Control Suite --------------------
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

    # 🔥 NEW FEATURE: Volume Control
    async def change_volume_call(self, chat_id: int, volume: int) -> None:
        """Changes the volume of the stream (e.g., 200 for 200%)"""
        assistant = await group_assistant(self, chat_id)
        await assistant.change_volume_call(chat_id, volume)

    async def stop_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await _clear_(chat_id)
        try: await assistant.leave_call(chat_id)
        except: pass
        finally: self.active_calls.discard(chat_id)

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
        finally: self.active_calls.discard(chat_id)

    # -------------------- Handlers (Decorators) --------------------
    async def decorators(self) -> None:
        async def stream_end_handler(client, update: Update):
            chat_id = update.chat_id
            LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
            await self.play(client, chat_id)

        # define desired status flags safely (as ints)
        desired_status_flags = [
            getattr(ChatUpdate, "Status", None) and getattr(ChatUpdate, "Status", "LEFT_CALL"),
            getattr(ChatUpdate, "Status", None) and getattr(ChatUpdate, "Status", "KICKED"),
            getattr(ChatUpdate, "Status", None) and getattr(ChatUpdate, "Status", "CLOSED_VOICE_CHAT"),
        ]
        # convert to actual enum members if available
        resolved_flags = []
        for f in desired_status_flags:
            # if ChatUpdate.Status is an enum class, getattr above will return the member
            if isinstance(f, str):
                # fallback: try attribute on ChatUpdate.Status by name
                try:
                    member = getattr(ChatUpdate.Status, f)
                    resolved_flags.append(member)
                except Exception:
                    pass
            elif f is not None:
                resolved_flags.append(f)

        combined_flags_int = 0
        for rf in resolved_flags:
            combined_flags_int |= enum_to_int(rf)

        async def connection_handler(client, update: Update):
            # defensive: sometimes update may not have status attribute or it's an Enum
            chat_id = getattr(update, "chat_id", None)
            status = getattr(update, "status", None)
            if chat_id is None:
                return
            status_int = enum_to_int(status)
            if (status_int & combined_flags_int) != 0:
                try:
                    await self.stop_stream(chat_id)
                except Exception:
                    pass

        async def participant_change_handler(client, update: Update):
            try:
                chat_id = update.chat_id
                if await is_autoend():
                    participants = await client.get_participants(chat_id)
                    if len(participants) == 1:
                        autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                    else:
                        autoend.pop(chat_id, None)
            except: pass

        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        # build a compatible chat_update filter instance from resolved enum members
        chat_update_filter = make_chat_update_filter_from_iter(resolved_flags)

        for assistant in assistants:
            assistant.on_update(filters.stream_end())(stream_end_handler)
            # use the compatibility filter
            try:
                assistant.on_update(chat_update_filter)(connection_handler)
            except Exception:
                try:
                    assistant.on_update(filters.chat_update())(connection_handler)
                except Exception:
                    try:
                        assistant.on_update(connection_handler)
                    except Exception:
                        LOGGER(__name__).warning("Failed to attach chat_update handler for an assistant.")
            try:
                assistant.on_update(filters.call_participants())(participant_change_handler)
            except: pass

    # -------------------- Play (Queue) --------------------
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
            if popped: await auto_clean(popped)
            if not check:
                await _clear_(chat_id)
                try:
                    await client.leave_call(chat_id)
                except: pass
                finally: self.active_calls.discard(chat_id)
                return
        except:
            try: await _clear_(chat_id); return await client.leave_call(chat_id)
            except: return

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
                if direct: final_link = direct
            except: pass

        stream = _build_stream(final_link, video=is_video)
        lock = self._get_lock(chat_id)
        
        async with lock:
            try:
                await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except Exception as e:
                LOGGER(__name__).error(f"Play Error for {chat_id}: {e}")
                await asyncio.sleep(0.8)
                try:
                    await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                except:
                    if len(check) > 1:
                        check.pop(0)
                        await self.play(client, chat_id)
                        return
                    await _clear_(chat_id)
                    try: await app.send_message(original_chat_id, "Stream failed, queue cleared.")
                    except: pass
                    return

            if is_video: await add_active_video_chat(chat_id)
            else: await remove_active_video_chat(chat_id)

            if len(check) > 1:
                try: asyncio.create_task(self._resolve_and_cache_next(check[1]))
                except: pass

            try:
                lang = await get_lang(chat_id)
                strings = get_string(lang)
            except: strings = None

            img = await get_thumb(videoid)
            from AnnieXMedia.utils.inline import stream_markup
            button = stream_markup(strings or {}, chat_id)

            try:
                if db[chat_id][0].get("mystic"):
                    await db[chat_id][0].get("mystic").delete()
            except: pass

            try:
                run = await app.send_photo(
                    chat_id=original_chat_id,
                    photo=img,
                    caption=(strings or {}).get("stream_1", "Now playing: {}").format(
                        f"https://t.me/{app.username}?start=info_{videoid}",
                        title[:23],
                        duration,
                        user,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
            except Exception as e:
                LOGGER(__name__).error(f"UI Error {chat_id}: {e}")

StreamController = Call()
