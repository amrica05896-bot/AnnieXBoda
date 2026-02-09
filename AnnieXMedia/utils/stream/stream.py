# Authored By Certified Coders © 2026
# System: Stream Controller (Full Version - Direct Button Edit)
# Updated 2026 - Compatibility layer for pytgcalls / ntgcalls newer versions
# - preserves original logic while enabling direct inline button switching

import asyncio
import os
from random import randint
from typing import Union, Any

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

import config
from AnnieXMedia import Carbon, YouTube, app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import add_active_video_chat, is_active_chat
from AnnieXMedia.utils.exceptions import AssistantErr
from AnnieXMedia.utils.inline import aq_markup, close_markup, stream_markup
# 🛑 استيراد ملف الكوستوم
from AnnieXMedia.utils.inline.custom import custom_markup
from AnnieXMedia.utils.pastebin import ANNIEBIN
from AnnieXMedia.utils.stream.queue import put_queue, put_queue_index
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

# small helper safe-delete/send wrappers to avoid crashes when message id invalid
async def safe_delete(message):
    try:
        if message:
            await message.delete()
    except Exception:
        # ignore everything (MessageIdInvalid, RPCError, etc.)
        return

async def safe_send_photo(chat_id: int, **kwargs):
    try:
        return await app.send_photo(chat_id, **kwargs)
    except Exception:
        # fallback to send_message with photo URL if send_photo fails
        try:
            caption = kwargs.get("caption", "")
            if "photo" in kwargs and isinstance(kwargs["photo"], str):
                return await app.send_message(chat_id, caption)
        except Exception:
            return None

async def safe_send_message(chat_id: int, **kwargs):
    try:
        return await app.send_message(chat_id, **kwargs)
    except Exception:
        return None

# Utility: attempt to call the join method on StreamController with fallbacks
async def _join_call_with_fallback(chat_id, original_chat_id, file_path, video=False, image=None):
    """
    Calls the appropriate StreamController join function while handling
    possible API name changes across pytgcalls/ntgcalls versions.
    """
    # list of candidate method names in preference order
    candidates = [
        "join_call",
        "join_stream",
        "join",
        "start_stream",
        "start_call",
    ]
    excs = []
    for name in candidates:
        fn = getattr(StreamController, name, None)
        if callable(fn):
            try:
                # detect if method is static or coroutine function
                result = fn(chat_id, original_chat_id, file_path, video=video, image=image)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except TypeError:
                # maybe signature differs (e.g., lacks named args) - try positional
                try:
                    result = fn(chat_id, original_chat_id, file_path, video, image)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                except Exception as e:
                    excs.append(e)
                    continue
            except Exception as e:
                excs.append(e)
                continue
    # If we reach here, nothing worked
    raise RuntimeError(f"Could not call StreamController join method, tried: {candidates}. Errors: {excs}")

@capture_internal_err
async def stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
) -> None:
    if not result:
        return

    forceplay = bool(forceplay)
    is_video = True if video else False

    if forceplay:
        # try to stop previous stream; keep safe if API changed
        stop_fn = getattr(StreamController, "force_stop_stream", None) or getattr(StreamController, "stop_stream", None) or getattr(StreamController, "force_stop", None)
        if callable(stop_fn):
            try:
                res = stop_fn(chat_id)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                # ignore stop failure
                pass

    # -----------------------------
    # 🛑 0) CUSTOM SONG MODE (Switching Buttons on Current Message)
    # -----------------------------
    if streamtype == "custom":
        vidid = result.get("vidid")
        title = (result.get("title")).title()
        duration_min = result.get("duration_min")
        thumbnail = result.get("thumb")

        try:
            # mystic هنا هي الرسالة اللي فيها زر "تشغيل الآن"
            file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=vidid)
        except Exception:
            raise AssistantErr(_["play_14"])

        if not forceplay:
            db[chat_id] = []

        try:
            await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
        except Exception:
            raise AssistantErr(_["play_14"])

        await put_queue(
            chat_id,
            original_chat_id,
            file_path if direct else f"vid_{vidid}",
            title,
            duration_min,
            user_name,
            vidid,
            user_id,
            "video" if is_video else "audio",
            forceplay=forceplay,
        )

        # 🛑 تعديل الأزرار تحت الملف نفسه بدلاً من إرسال رسالة جديدة
        button = custom_markup(_, chat_id, vidid)
        try:
            # تبديل زرار "تشغيل الآن" بالـ 4 زرارير الكوستوم
            await mystic.edit_reply_markup(reply_markup=button)
            
            # حفظ الرسالة في الداتابيز عشان التايمر يكمل تحديث عليها
            db[chat_id][0]["mystic"] = mystic
            db[chat_id][0]["markup"] = "custom"
        except Exception:
            pass
        return

    # -----------------------------
    # 1) PLAYLIST MODE
    # -----------------------------
    elif streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0

        for search in result:
            if int(count) == config.PLAYLIST_FETCH_LIMIT:
                continue
            try:
                title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(search, videoid=search)
            except Exception:
                continue

            if str(duration_min) == "None":
                continue
            if duration_sec and duration_sec > config.DURATION_LIMIT:
                continue

            # if already active, just queue
            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if is_video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}. {title[:70]}\n"
                msg += f"{_['play_20']} {position}\n\n"
            else:
                if not forceplay:
                    db[chat_id] = []
                # attempt download - YouTube.download must accept videoid kwarg
                try:
                    file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=vidid)
                except Exception:
                    raise AssistantErr(_["play_14"])

                if not file_path:
                    raise AssistantErr(_["play_14"])

                # join with fallback
                try:
                    await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
                except Exception:
                    # If join failed, try to cleanup and raise
                    raise AssistantErr(_["play_14"])

                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if is_video else "audio",
                    forceplay=forceplay,
                )

                img = await get_thumb(vidid)
                button = stream_markup(_, chat_id)

                # delete the "loading" message if exists
                await safe_delete(mystic)

                caption_text = "🧚 " + _["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                )

                try:
                    run = await safe_send_photo(
                        original_chat_id,
                        photo=img,
                        caption=caption_text,
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    if run:
                        db[chat_id][0]["mystic"] = run
                        db[chat_id][0]["markup"] = "stream"
                except Exception:
                    # don't crash if message sending fails
                    pass

        if count == 0:
            return

        # send playlist summary
        link = await ANNIEBIN(msg)
        try:
            carbon = await Carbon.generate(msg, randint(100, 10000000))
            playlist_photo = carbon
        except Exception:
            playlist_photo = config.PLAYLIST_IMG_URL

        upl = close_markup(_)
        final_position = max(len(db.get(chat_id) or []) - 1, 0)
        return await safe_send_photo(
            original_chat_id,
            photo=playlist_photo,
            caption="🧚 " + _["play_21"].format(final_position, link),
            reply_markup=upl,
        )

    # -----------------------------
    # 2) YOUTUBE SINGLE MODE
    # -----------------------------
    elif streamtype == "youtube":
        link = result.get("link")
        vidid = result.get("vidid")
        title = (result.get("title") or "").title()
        duration_min = result.get("duration_min")
        thumbnail = result.get("thumb")

        try:
            file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=vidid)
        except Exception:
            raise AssistantErr(_["play_14"])

        if not file_path:
            raise AssistantErr(_["play_14"])

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if is_video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_delete(mystic)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []

            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
            except Exception:
                raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if is_video else "audio",
                forceplay=forceplay,
            )

            img = await get_thumb(vidid)
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)

            caption_text = "🧚 " + _["stream_1"].format(
                f"https://t.me/{app.username}?start=info_{vidid}",
                title[:23],
                duration_min,
                user_name,
            )
            try:
                run = await safe_send_photo(
                    original_chat_id,
                    photo=img,
                    caption=caption_text,
                    reply_markup=InlineKeyboardMarkup(button),
                )
                if run:
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"
            except Exception:
                pass

    # -----------------------------
    # 3) SOUNDCLOUD MODE
    # -----------------------------
    elif streamtype == "soundcloud":
        file_path = result.get("filepath")
        title = result.get("title")
        duration_min = result.get("duration_min")

        if not file_path:
            raise AssistantErr(_["play_14"])

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=False)
            except Exception:
                raise AssistantErr(_["play_14"])
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
                forceplay=forceplay,
            )
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id,
                photo=config.SOUNCLOUD_IMG_URL,
                caption="🧚 " + _["stream_1"].format(config.SUPPORT_CHAT, title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            if run:
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"

    # -----------------------------
    # 4) TELEGRAM FILE MODE
    # -----------------------------
    elif streamtype == "telegram":
        file_path = result.get("path")
        link = result.get("link")
        title = (result.get("title") or "").title()
        duration_min = result.get("dur", result.get("duration_min", "00:00"))

        if not file_path:
            raise AssistantErr(_["play_14"])

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if is_video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video)
            except Exception:
                raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if is_video else "audio",
                forceplay=forceplay,
            )
            if is_video:
                await add_active_video_chat(chat_id)
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id,
                photo=config.TELEGRAM_VIDEO_URL if is_video else config.TELEGRAM_AUDIO_URL,
                caption="🧚 " + _["stream_1"].format(link, title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            if run:
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"

    # -----------------------------
    # 5) LIVE MODE
    # -----------------------------
    elif streamtype == "live":
        link = result.get("link")
        vidid = result.get("vidid")
        title = (result.get("title") or "").title()
        thumbnail = result.get("thumb")
        duration_min = "Live Track"

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if is_video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            # delegate to YouTube.video (user had this in original code)
            n, file_path = await YouTube.video(link)
            if n == 0 or not file_path:
                raise AssistantErr(_["str_3"])
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
            except Exception:
                raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if is_video else "audio",
                forceplay=forceplay,
            )
            img = await get_thumb(vidid)
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id,
                photo=img,
                caption="🧚 " + _["stream_1"].format(f"https://t.me/{app.username}?start=info_{vidid}", title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            if run:
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"

    # -----------------------------
    # 6) INDEX MODE
    # -----------------------------
    elif streamtype == "index":
        link = result
        title = "رابط خارجي"
        duration_min = "00:00"

        if await is_active_chat(chat_id):
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if is_video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await mystic.edit_text(
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, link, video=is_video)
            except Exception:
                raise AssistantErr(_["play_14"])
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if is_video else "audio",
                forceplay=forceplay,
            )
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption="🧚 " + _["stream_2"].format(user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            if run:
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
