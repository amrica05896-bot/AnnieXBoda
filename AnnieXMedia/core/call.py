
"""
Call Controller (PyTgCalls v3.0) - Pro Max Enterprise Edition
Adds:
- Bounded LRU+TTL cache for direct links
- Per-chat asyncio locks and safe enqueue to prevent race conditions when multiple users request the same track at the same time
- Participant change monitoring to keep autoend accurate
- Graceful shutdown that cancels watcher, leaves calls and shuts down threadpool
- Retry logic that skips to next track on persistent failures instead of clearing queue
- Improvements: fewer repeated DB/lang lookups, safe prefetch dedupe, threadpool shutdown
"""

import asyncio
import os
import signal
from datetime import datetime, timedelta
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Set, Tuple

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

# -------------------- Configurable Parameters --------------------
_DIRECT_CACHE_MAXSIZE = 500    # max entries in direct link cache
_DIRECT_CACHE_TTL = 60 * 60   # seconds (1 hour)
_THREADPOOL_WORKERS = 8       # tune to your server cores
_PREFETCH_DEBOUNCE = 2.0      # seconds to debounce duplicate prefetch tasks

# -------------------- Utilities --------------------
class LRUCacheTTL:
    """Simple ordered LRU cache with TTL eviction."""
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
                # expired
                try:
                    del self._data[key]
                except KeyError:
                    pass
                return None
            # move to end
            self._data.move_to_end(key)
            return val

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            if key in self._data:
                del self._data[key]
            self._data[key] = (value, datetime.now().timestamp())
            self._data.move_to_end(key)
            # evict if over size
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()


# Global structures
_DIRECT_LINK_CACHE = LRUCacheTTL(maxsize=_DIRECT_CACHE_MAXSIZE, ttl=_DIRECT_CACHE_TTL)
_THREAD_POOL = ThreadPoolExecutor(max_workers=_THREADPOOL_WORKERS)
_prefetch_tasks: Dict[int, float] = {}  # chat_id -> last prefetch timestamp

# autoend keeps track of scheduled end times
autoend: Dict[int, datetime] = {}

# -------------------- Blocking extractor --------------------
def _yt_extract(link: str, fmt: str) -> str:
    opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
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

    # try cache
    cached = await _DIRECT_LINK_CACHE.get(videoid)
    if cached:
        return cached

    link = f"https://www.youtube.com/watch?v={videoid}"
    fmt = "best[ext=mp4]/best" if video else "bestaudio/best"

    loop = asyncio.get_running_loop()
    try:
        direct = await loop.run_in_executor(_THREAD_POOL, _yt_extract, link, fmt)
        if direct:
            await _DIRECT_LINK_CACHE.set(videoid, direct)
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
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.HD_720p,
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=final_ffmpeg,
    )


async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped:
        try:
            await auto_clean(popped)
        except Exception:
            pass
    db[chat_id] = []
    try:
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except Exception:
        pass


# -------------------- Controller --------------------
class Call:
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
                # Debounce per chat to avoid duplicate prefetches
                chat_id = queued_entry.get("chat_id") or 0
                last = _prefetch_tasks.get(chat_id)
                now = datetime.now().timestamp()
                if last and (now - last) < _PREFETCH_DEBOUNCE:
                    return
                _prefetch_tasks[chat_id] = now
                await get_direct_link(vidid, video=is_video)
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
                    except Exception as e:
                        LOGGER(__name__).error(f"Auto-end failed for {chat_id}: {e}")
                    finally:
                        autoend.pop(chat_id, None)

    # Safe enqueue: prevents race when two users request same song simultaneously
    async def enqueue_track(self, chat_id: int, entry: dict) -> None:
        """Append entry to db[chat_id] using per-chat lock to avoid concurrent mutations."""
        lock = self._get_lock(chat_id)
        async with lock:
            try:
                queue = db.get(chat_id) or []
                queue.append(entry)
                db[chat_id] = queue
            except Exception as e:
                LOGGER(__name__).error(f"Enqueue failed for {chat_id}: {e}")

    # -------------------- lifecycle --------------------
    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (v3.0)...")
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
        """Graceful shutdown: stop watcher, leave calls, shutdown threadpool, clear caches."""
        self._stopping = True
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        # attempt to leave active calls
        for chat_id in list(self.active_calls):
            try:
                assistant = await group_assistant(self, chat_id)
                await assistant.leave_call(chat_id)
            except Exception:
                pass

        # shutdown threadpool
        try:
            _THREAD_POOL.shutdown(wait=False)
        except Exception:
            pass

        # clear caches
        try:
            await _DIRECT_LINK_CACHE.clear()
        except Exception:
            pass

    # -------------------- Controls --------------------
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

    # -------------------- Seek & Skip --------------------
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: int, duration: int, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        lock = self._get_lock(chat_id)

        async with lock:
            if chat_id not in self.active_calls:
                return

            ffmpeg_opts = f"-ss {to_seek}"
            is_video = (mode == "video")
            stream = _build_stream(file_path, video=is_video, ffmpeg_opts=ffmpeg_opts)

            try:
                await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except Exception as e:
                LOGGER(__name__).error(f"Seek failed for {chat_id}: {e}")

    async def skip_stream(self, chat_id: int, link: str, video: bool = False) -> None:
        assistant = await group_assistant(self, chat_id)
        lock = self._get_lock(chat_id)

        async with lock:
            stream = _build_stream(link, video=video)
            try:
                await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except Exception as e:
                LOGGER(__name__).error(f"Skip failed for {chat_id}: {e}")

    # -------------------- Join/Play --------------------
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: bool = False, image: str = None) -> None:
        assistant = await group_assistant(self, chat_id)
        lang = await get_lang(chat_id)
        _strings = get_string(lang)

        lock = self._get_lock(chat_id)
        async with lock:
            stream = _build_stream(link, video=video)
            try:
                await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))

                self.active_calls.add(chat_id)
                await add_active_chat(chat_id)
                await music_on(chat_id)
                if video:
                    await add_active_video_chat(chat_id)

                # Auto-End Logic Init
                if await is_autoend():
                    try:
                        participants = await assistant.get_participants(chat_id)
                        if len(participants) == 1:
                            autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                        else:
                            autoend.pop(chat_id, None)
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

    async def decorators(self) -> None:
        async def stream_end_handler(client, update: Update):
            chat_id = update.chat_id
            LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
            await self.play(client, chat_id)

        async def left_call_handler(client, update: Update):
            chat_id = update.chat_id
            await self.stop_stream(chat_id)

        async def kicked_handler(client, update: Update):
            chat_id = update.chat_id
            await self.stop_stream(chat_id)

        # Monitor participants changes if available to keep autoend accurate
        async def participant_change_handler(client, update: Update):
            try:
                chat_id = update.chat_id
                if await is_autoend():
                    participants = await client.get_participants(chat_id)
                    if len(participants) == 1:
                        autoend[chat_id] = datetime.now() + timedelta(minutes=1)
                    else:
                        autoend.pop(chat_id, None)
            except Exception:
                pass

        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        for assistant in assistants:
            assistant.on_update(filters.stream_end())(stream_end_handler)
            assistant.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))(left_call_handler)
            assistant.on_update(filters.chat_update(ChatUpdate.Status.KICKED))(kicked_handler)
            # Attach participants handler if the version of pytgcalls supports it
            try:
                assistant.on_update(filters.call_participants())(participant_change_handler)
            except Exception:
                # older versions may not have call_participants filter
                pass

    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        """Master queue processor with robust retry & skip-on-failure behavior."""
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

        # Resolve final link (prefer cached direct link)
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
                await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except Exception as e:
                LOGGER(__name__).error(f"Play Error for {chat_id}: {e}")
                # Retry once, then attempt skip to next track instead of clearing everything
                await asyncio.sleep(0.8)
                try:
                    await client.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
                except Exception as e2:
                    LOGGER(__name__).error(f"Play Retry failed for {chat_id}: {e2}")
                    # Try skip to next item if exists
                    try:
                        if len(check) > 1:
                            # pop the failed track and move on
                            check.pop(0)
                            # recursively call play to attempt next track
                            await self.play(client, chat_id)
                            return
                    except Exception:
                        pass
                    await _clear_(chat_id)
                    try:
                        await app.send_message(original_chat_id, "Failed to switch stream.")
                    except Exception:
                        pass
                    return

            # Update DB state
            if is_video:
                await add_active_video_chat(chat_id)
            else:
                await remove_active_video_chat(chat_id)

            # Pre-fetch next track to reduce latency
            if len(check) > 1:
                try:
                    asyncio.create_task(self._resolve_and_cache_next(check[1]))
                except Exception:
                    pass

            # UI Update (minimized repeated calls)
            try:
                lang = await get_lang(chat_id)
                strings = get_string(lang)
            except Exception:
                strings = None

            img = await get_thumb(videoid)
            from AnnieXMedia.utils.inline import stream_markup
            button = stream_markup(strings or {}, chat_id)

            try:
                if db[chat_id][0].get("mystic"):
                    await db[chat_id][0].get("mystic").delete()
            except Exception:
                pass

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
                LOGGER(__name__).error(f"Failed to send stream UI for {chat_id}: {e}")


StreamController = Call()
