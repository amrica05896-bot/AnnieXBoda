# Call controller + minimal API for change_stream
# Authored By Certified Coders © 2026
# System: Call Controller (PyTgCalls v3.0 Native)
# Features added: change_stream (safe), API endpoint /api/change_stream (token-protected)

import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Union, Optional

import yt_dlp
from pyrogram.types import InlineKeyboardMarkup
from pyrogram.errors import ChatAdminRequired, FloodWait

# Imports based on PyTgCalls v3.0 Docs
from pytgcalls import PyTgCalls, filters
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality,
    GroupCallConfig,
    Update,
    ChatUpdate,
    StreamEnded,
)
from pytgcalls.exceptions import (
    NoActiveGroupCall,
    NotInCallError,
    NoAudioSourceFound,
    NoVideoSourceFound,
    PyTgCallsAlreadyRunning,
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

# For API
from aiohttp import web
from aiohttp.web import Response, json_response

# ---------------- Globals ----------------
autoend = {}
counter = {}
# prevent rapid duplicate change_streams: {(chat_id, vidid): timestamp}
_recent_change_streams: dict[tuple[int, str], float] = {}

# ===============================
# Helper Functions
# ===============================

async def get_direct_link(videoid: str, video: bool = False):
    if not videoid:
        return None
    link = f"https://www.youtube.com/watch?v={videoid}"
    fmt = "best[ext=mp4]/best" if video else "bestaudio/best"
    opts = {
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True
    }
    try:
        loop = asyncio.get_running_loop()
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=False)
                return info.get("url")
        return await loop.run_in_executor(None, _extract)
    except: 
        return link

def _build_stream(path: str, video: bool = False, ffmpeg_opts: str = "") -> MediaStream:
    """
    Constructs a MediaStream object compatible with PyTgCalls v3.0.
    Handles Audio/Video flags and FFmpeg parameters.
    """
    path = str(path)
    is_url = path.startswith("http")
    
    # 1. Base FFmpeg parameters
    base_flags = (
        "-threads 2 "
        "-probesize 10M -analyzeduration 10M "
        "-fflags +genpts+igndts+nobuffer -sync ext "
    )
    
    # 2. Input specific flags
    if is_url:
        base_flags += "-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 "
    else:
        base_flags += "-re "

    final_ffmpeg = base_flags + ffmpeg_opts

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.HD_720p,
        video_flags=MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE,
        audio_flags=MediaStream.Flags.REQUIRED,
        ffmpeg_parameters=final_ffmpeg,
    )

def extract_vidid_from_link(link: str) -> Optional[str]:
    if not link: return None
    try:
        if "watch?v=" in link:
            return link.split("watch?v=")[-1].split("&")[0]
        if "youtu.be/" in link:
            return link.split("youtu.be/")[-1].split("?")[0]
    except Exception:
        return None
    return None

async def _clear_(chat_id: int) -> None:
    popped = db.pop(chat_id, None)
    if popped: await auto_clean(popped)
    db[chat_id] = []
    try:
        await remove_active_video_chat(chat_id)
        await remove_active_chat(chat_id)
        await set_loop(chat_id, 0)
    except: pass

# ===============================
# The Controller Class
# ===============================

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

        self.active_calls: set[int] = set()
        self._locks: dict[int, asyncio.Lock] = {}

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    # --- Standard Controls ---
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
        except: pass
        finally:
            self.active_calls.discard(chat_id)

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
        except: pass
        finally:
            self.active_calls.discard(chat_id)

    # --- Advanced Controls (Seek & Skip) ---
    async def seek_stream(self, chat_id: int, file_path: str, to_seek: int, duration: int, mode: str) -> None:
        assistant = await group_assistant(self, chat_id)
        ffmpeg_opts = f"-ss {to_seek} "
        is_video = (mode == "video")
        stream = _build_stream(file_path, video=is_video, ffmpeg_opts=ffmpeg_opts)
        await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))

    async def skip_stream(self, chat_id: int, link: str, video: bool = False) -> None:
        assistant = await group_assistant(self, chat_id)
        stream = _build_stream(link, video=video)
        await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))

    # --- NEW: change_stream (safe switching) ---
    async def change_stream(self, chat_id: int, link: str, video: bool = False, title: str = None) -> None:
        """
        Immediately switch current playing stream to `link` safely.
        - dedupes very-rapid duplicate requests for same vidid (2s window).
        - acquires per-chat lock to avoid race.
        - updates db[chat_id][0] if present so UI messages stay consistent.
        """
        lock = self._get_lock(chat_id)
        async with lock:
            vidid = extract_vidid_from_link(link)
            key = (chat_id, vidid or link)
            now_ts = time.time()
            # dedupe: if same request within 2 seconds, ignore
            recent = _recent_change_streams.get(key)
            if recent and (now_ts - recent) < 2.0:
                LOGGER(__name__).info(f"Duplicate rapid change_stream ignored for {key}")
                return
            _recent_change_streams[key] = now_ts

            assistant = await group_assistant(self, chat_id)
            final_link = link
            if vidid:
                try:
                    direct = await get_direct_link(vidid, video=video)
                    if direct:
                        final_link = direct
                except Exception:
                    pass

            stream = _build_stream(final_link, video=video)
            try:
                # try the preferred play API
                await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
            except Exception as e:
                # fallback to join_group_call if available
                fn = getattr(assistant, "join_group_call", None)
                if callable(fn):
                    try:
                        await fn(chat_id, stream)
                    except Exception as e2:
                        LOGGER(__name__).error(f"change_stream fallback join failed: {e2}")
                        raise AssistantErr(f"Failed to switch stream: {e2}")
                else:
                    LOGGER(__name__).error(f"change_stream failed: {e}")
                    raise AssistantErr(f"Failed to switch stream: {e}")

            # update internal state + db UI entry if any
            self.active_calls.add(chat_id)
            q = db.get(chat_id)
            if isinstance(q, list) and len(q) > 0:
                # update current entry to reflect new stream so UI/queue match
                q[0]["file"] = final_link
                if vidid:
                    q[0]["vidid"] = vidid
                if title:
                    q[0]["title"] = title
                db[chat_id] = q

            # mark video state
            if video:
                await add_active_video_chat(chat_id)
            else:
                await remove_active_video_chat(chat_id)

    # --- Core Join/Play Logic ---
    async def join_call(self, chat_id: int, original_chat_id: int, link: str, video: bool = False, image: str = None) -> None:
        assistant = await group_assistant(self, chat_id)
        lang = await get_lang(chat_id)
        _ = get_string(lang)

        final_link = link
        if "youtube" in str(link) or "youtu.be" in str(link):
            pass

        stream = _build_stream(final_link, video=video)

        try:
            await assistant.play(chat_id, stream, config=GroupCallConfig(auto_start=True))
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
                except: pass
        except NoActiveGroupCall:
             raise AssistantErr(_["call_8"])
        except ChatAdminRequired:
            raise AssistantErr(_["call_8"])
        except Exception as e:
            if "group call not found" in str(e).lower():
                raise AssistantErr(_["call_8"])
            raise AssistantErr(f"Error: {e}")

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients (v3.0)...")
        if self.one and config.STRING1: await self.one.start()
        if self.two and config.STRING2: await self.two.start()
        if self.three and config.STRING3: await self.three.start()
        if self.four and config.STRING4: await self.four.start()
        if self.five and config.STRING5: await self.five.start()

    # --- Decorators / Filters System ---
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))
        
        for assistant in assistants:
            
            # 1. Stream Ended -> Play Next (Queue)
            @assistant.on_update(filters.stream_end())
            async def stream_end_handler(client, update: Update):
                chat_id = getattr(update, "chat_id", None)
                if chat_id is None:
                    return
                LOGGER(__name__).info(f"Stream ended for chat {chat_id}")
                await self.play(client, chat_id)

            # attach chat_update handlers defensively
            try:
                assistant.on_update(filters.chat_update())(lambda c, u: asyncio.create_task(self.stop_stream(getattr(u, "chat_id", None))))
            except Exception:
                try:
                    assistant.on_update(lambda c, u: asyncio.create_task(self.stop_stream(getattr(u, "chat_id", None))))
                except Exception:
                    LOGGER(__name__).warning("Could not attach chat_update handler for an assistant")

    # --- Queue Processing ---
    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
        if not check:
            await _clear_(chat_id)
            return

        popped = None
        loop = await get_loop(chat_id)
        try:
            if loop == 0:
                popped = check.pop(0)
            else:
                loop = loop - 1
                await set_loop(chat_id, loop)
            
            if popped: await auto_clean(popped)
            
            if not check:
                await _clear_(chat_id)
                try: await client.leave_call(chat_id)
                except: pass
                finally: self.active_calls.discard(chat_id)
                return
        except:
            try: await _clear_(chat_id); return await client.leave_call(chat_id)
            except: return

        # Get Next Track Info
        queued = check[0].get("file")
        title = (check[0].get("title") or "").title()
        user = check[0].get("by")
        original_chat_id = check[0].get("chat_id")
        streamtype = check[0].get("streamtype")
        videoid = check[0].get("vidid")
        duration = check[0].get("dur")
        
        is_video = str(streamtype) == "video"
        
        # Link Handling
        final_link = queued
        if "youtube" in str(queued):
             try:
                direct = await get_direct_link(videoid, video=is_video)
                if direct: final_link = direct
             except: pass

        # Build & Play Next Stream
        stream = _build_stream(final_link, video=is_video)

        try:
            await client.play(
                chat_id,
                stream,
                config=GroupCallConfig(auto_start=True)
            )
            
            if is_video:
                await add_active_video_chat(chat_id)
            else:
                await remove_active_video_chat(chat_id)

            # Notifications
            img = await get_thumb(videoid)
            from AnnieXMedia.utils.inline import stream_markup
            button = stream_markup(get_string(await get_lang(chat_id)), chat_id)
            
            try:
                if db[chat_id][0].get("mystic"):
                    await db[chat_id][0].get("mystic").delete()
            except: pass
            
            run = await app.send_photo(
                chat_id=original_chat_id,
                photo=img,
                caption=get_string(await get_lang(chat_id))["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{videoid}", 
                    title[:23], 
                    duration, 
                    user
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
            
        except Exception as e:
            LOGGER(__name__).error(f"Queue Play Error: {e}")
            await _clear_(chat_id)
            await app.send_message(original_chat_id, "Failed to switch stream.")

# global instance (keep existing name)
StreamController = Call()

# ---------------- Minimal API for change_stream ----------------
class MinimalApi:
    def __init__(self):
        self.app = web.Application(client_max_size=1024**2*50)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        self.app.router.add_post("/api/change_stream", self.change_stream_api)
        self.app.router.add_post("/api/auth", self.authenticate)
        self.app.router.add_get("/", self.ping)

    async def authenticate(self, request):
        try:
            data = await request.json()
            token = data.get("token")
            if token == getattr(config, "BOT_TOKEN", None):
                return json_response({"status": "ok"}, headers={"Access-Control-Allow-Origin":"*"})
            return json_response({"error": "Unauthorized"}, status=401, headers={"Access-Control-Allow-Origin":"*"})
        except Exception:
            return json_response({"error":"Bad Request"}, status=400, headers={"Access-Control-Allow-Origin":"*"})

    async def change_stream_api(self, request):
        try:
            data = await request.json()
            token = data.get("token")
            if token != getattr(config, "BOT_TOKEN", None):
                return json_response({"error":"Unauthorized"}, status=401, headers={"Access-Control-Allow-Origin":"*"})
            chat_id = int(data.get("chat_id"))
            link = data.get("link")
            video = bool(data.get("video", False))
            title = data.get("title", None)

            if not link:
                return json_response({"error":"Missing link"}, status=400, headers={"Access-Control-Allow-Origin":"*"})
            # If chat not active we can attempt a join_call instead of change_stream
            try:
                if chat_id not in StreamController.active_calls:
                    # create minimal queue entry so UI doesn't break
                    db[chat_id] = [{
                        "chat_id": chat_id,
                        "file": link,
                        "vidid": extract_vidid_from_link(link) or "",
                        "title": title or "API Stream",
                        "dur": "00:00",
                        "by": "API",
                        "streamtype": "video" if video else "audio"
                    }]
                    await StreamController.join_call(chat_id, chat_id, link, video=video)
                    return json_response({"status":"playing", "chat_id": chat_id}, headers={"Access-Control-Allow-Origin":"*"})
                else:
                    await StreamController.change_stream(chat_id, link, video=video, title=title)
                    return json_response({"status":"changed", "chat_id": chat_id}, headers={"Access-Control-Allow-Origin":"*"})
            except Exception as e:
                return json_response({"error": str(e)}, status=500, headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers={"Access-Control-Allow-Origin":"*"})

    async def ping(self, request):
        return json_response({"status":"ok"}, headers={"Access-Control-Allow-Origin":"*"})

    async def start(self, host="0.0.0.0", port=8080):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()

# instantiate api (optional - only start it where you normally start services)
BotAPI = MinimalApi()
