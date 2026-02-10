# Authored By Certified Coders © 2026
import asyncio
import os
import traceback
from datetime import datetime, timedelta
from typing import Union

from ntgcalls import TelegramServerError, ConnectionNotFound
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired
from pyrogram.types import InlineKeyboardMarkup
from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall, NoAudioSourceFound, NoVideoSourceFound
from pytgcalls.types import (
    AudioQuality, 
    ChatUpdate, 
    MediaStream, 
    StreamEnded, 
    Update, 
    VideoQuality, 
    GroupCallConfig
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

# --- Helper Function for Streams ---
def dynamic_media_stream(path: str, video: bool = False, ffmpeg_params: str = None) -> MediaStream:
    titan_flags = "-threads 16 -ac 2"
    if str(path).startswith("http"):
        titan_flags += " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    
    if ffmpeg_params:
        titan_flags += f" {ffmpeg_params}"

    video_flags = MediaStream.Flags.REQUIRED if video else MediaStream.Flags.IGNORE
    audio_flags = MediaStream.Flags.REQUIRED

    return MediaStream(
        media_path=path,
        audio_parameters=AudioQuality.STUDIO,
        video_parameters=VideoQuality.HD_720p, 
        audio_flags=audio_flags,
        video_flags=video_flags,
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

class Call:
    def __init__(self):
        self.userbot1 = userbot.one
        self.userbot2 = userbot.two
        self.userbot3 = userbot.three
        self.userbot4 = userbot.four
        self.userbot5 = userbot.five

        self.one = PyTgCalls(self.userbot1, cache_duration=100)
        self.two = PyTgCalls(self.userbot2, cache_duration=100)
        self.three = PyTgCalls(self.userbot3, cache_duration=100)
        self.four = PyTgCalls(self.userbot4, cache_duration=100)
        self.five = PyTgCalls(self.userbot5, cache_duration=100)

        self.active_calls: set[int] = set()
        self.turbo_mode = {} 

    @capture_internal_err
    async def pause_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        await assistant.pause(chat_id)

    @capture_internal_err
    async def resume_stream(self, chat_id: int) -> None:
        assistant = await group_assistant(self, chat_id)
        try:
            await assistant.resume(chat_id)
        except:
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
        if chat_id not in self.active_calls:
            return
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
        if chat_id not in self.active_calls:
            return
        try:
            await assistant.leave_call(chat_id)
        except Exception:
            pass
        finally:
            self.active_calls.discard(chat_id)

    @capture_internal_err
    async def skip_stream(self, chat_id: int, link: str, video: Union[bool, str] = None, image: Union[bool, str] = None) -> None:
        assistant = await group_assistant(self, chat_id)
        ksk = GroupCallConfig(auto_start=False)
        stream = dynamic_media_stream(path=link, video=bool(video))
        await assistant.play(chat_id, stream, config=ksk)

    @capture_internal_err
    async def vc_users(self, chat_id: int) -> list:
        assistant = await group_assistant(self, chat_id)
        try:
            participants = await assistant.get_participants(chat_id)
            return [p.user_id for p in participants if not p.is_muted]
        except:
            return []

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
            vs = str(2.0 / float(speed))
            cmd = f'ffmpeg -i "{file_path}" -filter:v "setpts={vs}*PTS" -filter:a atempo={speed} -y "{out}"'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        dur = int(await asyncio.get_event_loop().run_in_executor(None, check_duration, out))
        played, con_seconds = speed_converter(playing[0]["played"], speed)
        duration_min = seconds_to_min(dur)
        is_video = playing[0]["streamtype"] == "video"
        ffmpeg_params = f"-ss {played} -to {duration_min}"
        stream = dynamic_media_stream(path=out, video=is_video, ffmpeg_params=ffmpeg_params)

        if chat_id in db and db[chat_id] and db[chat_id][0].get("file") == file_path:
            await assistant.play(chat_id, stream)
            db[chat_id][0].update({
                "played": con_seconds,
                "dur": duration_min,
                "seconds": dur,
                "speed_path": out,
                "speed": speed,
                "old_dur": db[chat_id][0].get("dur"),
                "old_second": db[chat_id][0].get("seconds"),
            })
        else:
            raise AssistantErr("Stream mismatch during speedup.")

    @capture_internal_err
    async def stream_call(self, link: str) -> None:
        assistant = await group_assistant(self, config.LOGGER_ID)
        stream = dynamic_media_stream(link)
        try:
            await assistant.play(config.LOGGER_ID, stream)
            await asyncio.sleep(8)
        except (NoActiveGroupCall, ConnectionNotFound):
            LOGGER(__name__).warning("⚠️ لم يتمكن البوت من الانضمام لمجموعة السجل (تأكد أن المكالمة مفتوحة).")
        except Exception:
            pass
        finally:
            try:
                await assistant.leave_call(config.LOGGER_ID)
            except:
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
        stream = dynamic_media_stream(path=link, video=bool(video))
        ksk = GroupCallConfig(auto_start=False)

        try:
            await assistant.play(chat_id, stream, config=ksk)
        except NoActiveGroupCall:
            raise AssistantErr(_["call_8"])
        except (NoAudioSourceFound, NoVideoSourceFound):
            raise AssistantErr(_["call_11"])
        except (ConnectionNotFound, TelegramServerError):
            raise AssistantErr(_["call_10"])
        # 🔥 إضافة معالجة لخطأ AttributeError (NoneType)
        except AttributeError:
             try:
                 # محاولة الخروج ثم الدخول كحل أخير
                 await assistant.leave_call(chat_id)
                 await asyncio.sleep(1)
                 await assistant.play(chat_id, stream, config=ksk)
             except:
                 LOGGER(__name__).error(f"💣 [JOIN ERROR - RETRY FAILED] Chat: {chat_id}")
                 raise AssistantErr("حدث خطأ في الاتصال، يرجى إعادة المحاولة.")
        except Exception as e:
            LOGGER(__name__).error(f"💣 [JOIN ERROR] Chat: {chat_id}\n{traceback.format_exc()}")
            try:
                 await asyncio.sleep(1)
                 await assistant.play(chat_id, stream, config=ksk)
            except:
                 raise AssistantErr(f"ᴜɴᴀʙʟᴇ ᴛᴏ ᴊᴏɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴄᴀʟʟ.\nRᴇᴀsᴏɴ: {e}")
                 
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
            except:
                pass

    @capture_internal_err
    async def play(self, client, chat_id: int) -> None:
        check = db.get(chat_id)
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
                if chat_id in self.active_calls:
                    try:
                        await client.leave_call(chat_id)
                    except Exception:
                        pass
                    finally:
                        self.active_calls.discard(chat_id)
                return
        except:
            try:
                await _clear_(chat_id)
                return await client.leave_call(chat_id)
            except:
                return
        else:
            queued = check[0]["file"]
            language = await get_lang(chat_id)
            _ = get_string(language)
            title = (check[0]["title"]).title()
            user = check[0]["by"]
            original_chat_id = check[0]["chat_id"]
            streamtype = check[0]["streamtype"]
            videoid = check[0]["vidid"]
            db[chat_id][0]["played"] = 0

            exis = (check[0]).get("old_dur")
            if exis:
                db[chat_id][0]["dur"] = exis
                db[chat_id][0]["seconds"] = check[0]["old_second"]
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
                    except:
                        return await app.send_message(original_chat_id, text=_["call_6"])

            try:
                if "live_" in queued:
                    n, link = await YouTube.video(videoid, True)
                    if n == 0:
                        return await app.send_message(original_chat_id, text=_["call_6"])
                    stream = dynamic_media_stream(path=link, video=video)
                    await _play_stream(stream)
                    img = await get_thumb(videoid)
                    button = stream_markup(_, chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=img,
                        caption=_["stream_1"].format(
                            f"https://t.me/{app.username}?start=info_{videoid}",
                            title[:23],
                            check[0]["dur"],
                            user,
                        ),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"

                elif "vid_" in queued:
                    mystic = await app.send_message(original_chat_id, _["call_7"])
                    try:
                        file_path, direct = await YouTube.download(
                            videoid,
                            mystic,
                            videoid=True,
                            video=video,
                        )
                    except:
                        return await mystic.edit_text(_["call_6"], disable_web_page_preview=True)

                    stream = dynamic_media_stream(path=file_path, video=video)
                    await _play_stream(stream)

                    img = await get_thumb(videoid)
                    button = stream_markup(_, chat_id)
                    await mystic.delete()
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=img,
                        caption=_["stream_1"].format(
                            f"https://t.me/{app.username}?start=info_{videoid}",
                            title[:23],
                            check[0]["dur"],
                            user,
                        ),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"

                elif "index_" in queued:
                    stream = dynamic_media_stream(path=videoid, video=video)
                    await _play_stream(stream)

                    button = stream_markup(_, chat_id)
                    run = await app.send_photo(
                        chat_id=original_chat_id,
                        photo=config.STREAM_IMG_URL,
                        caption=_["stream_2"].format(user),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"

                else:
                    stream = dynamic_media_stream(path=queued, video=video)
                    await _play_stream(stream)

                    if videoid == "telegram":
                        button = stream_markup(_, chat_id)
                        run = await app.send_photo(
                            chat_id=original_chat_id,
                            photo=(
                                config.TELEGRAM_AUDIO_URL
                                if str(streamtype) == "audio"
                                else config.TELEGRAM_VIDEO_URL
                            ),
                            caption=_["stream_1"].format(
                                config.SUPPORT_CHAT, title[:23], check[0]["dur"], user
                            ),
                            reply_markup=InlineKeyboardMarkup(button),
                        )
                        db[chat_id][0]["mystic"] = run
                        db[chat_id][0]["markup"] = "tg"

                    elif videoid == "soundcloud":
                        button = stream_markup(_, chat_id)
                        run = await app.send_photo(
                            chat_id=original_chat_id,
                            photo=config.SOUNCLOUD_IMG_URL,
                            caption=_["stream_1"].format(
                                config.SUPPORT_CHAT, title[:23], check[0]["dur"], user
                            ),
                            reply_markup=InlineKeyboardMarkup(button),
                        )
                        db[chat_id][0]["mystic"] = run
                        db[chat_id][0]["markup"] = "tg"

                    else:
                        img = await get_thumb(videoid)
                        button = stream_markup(_, chat_id)
                        try:
                            run = await app.send_photo(
                                chat_id=original_chat_id,
                                photo=img,
                                caption=_["stream_1"].format(
                                    f"https://t.me/{app.username}?start=info_{videoid}",
                                    title[:23],
                                    check[0]["dur"],
                                    user,
                                ),
                                reply_markup=InlineKeyboardMarkup(button),
                            )
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                            run = await app.send_photo(
                                chat_id=original_chat_id,
                                photo=img,
                                caption=_["stream_1"].format(
                                    f"https://t.me/{app.username}?start=info_{videoid}",
                                    title[:23],
                                    check[0]["dur"],
                                    user,
                                ),
                                reply_markup=InlineKeyboardMarkup(button),
                            )
                        db[chat_id][0]["mystic"] = run
                        db[chat_id][0]["markup"] = "stream"
            except Exception:
                LOGGER(__name__).error(f"💣 [PLAY ERROR] Chat: {chat_id}\n{traceback.format_exc()}")
                return await app.send_message(original_chat_id, text=_["call_6"])

    async def start(self) -> None:
        LOGGER(__name__).info("Starting PyTgCalls Clients...")
        if config.STRING1:
            await self.one.start()
        if config.STRING2:
            await self.two.start()
        if config.STRING3:
            await self.three.start()
        if config.STRING4:
            await self.four.start()
        if config.STRING5:
            await self.five.start()

    @capture_internal_err
    async def ping(self) -> str:
        pings = []
        if config.STRING1:
            pings.append(self.one.ping)
        if config.STRING2:
            pings.append(self.two.ping)
        if config.STRING3:
            pings.append(self.three.ping)
        if config.STRING4:
            pings.append(self.four.ping)
        if config.STRING5:
            pings.append(self.five.ping)
        return str(round(sum(pings) / len(pings), 3)) if pings else "0.0"

    @capture_internal_err
    async def decorators(self) -> None:
        assistants = list(filter(None, [self.one, self.two, self.three, self.four, self.five]))

        CRITICAL = (
            ChatUpdate.Status.KICKED
            | ChatUpdate.Status.LEFT_GROUP
            | ChatUpdate.Status.CLOSED_VOICE_CHAT
        )

        async def unified_update_handler(client, update: Update) -> None:
            if isinstance(update, StreamEnded):
                if update.stream_type == StreamEnded.Type.AUDIO:
                    assistant = await group_assistant(self, update.chat_id)
                    await self.play(assistant, update.chat_id)
            
            elif isinstance(update, ChatUpdate):
                status = update.status
                if (status & ChatUpdate.Status.LEFT_CALL) or (status & CRITICAL):
                    await self.stop_stream(update.chat_id)
                    return

        for assistant in assistants:
            assistant.on_update()(unified_update_handler)

StreamController = Call()
