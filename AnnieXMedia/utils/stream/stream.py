# Authored By Certified Coders © 2026
# System: Stream Controller (Compatible Edition)
# Fixed: stream_markup arguments & Telegram/Custom support

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
# ✅ Added telegram_markup to imports
from AnnieXMedia.utils.inline import aq_markup, close_markup, stream_markup, telegram_markup
# 🛑 Custom Markup Import
from AnnieXMedia.utils.inline.custom import custom_markup
from AnnieXMedia.utils.pastebin import ANNIEBIN
from AnnieXMedia.utils.stream.queue import put_queue, put_queue_index
from AnnieXMedia.utils.thumbnails import gen_thumb
from AnnieXMedia.utils.errors import capture_internal_err

# --- Helper Functions ---
async def safe_delete(message):
    try:
        if message: await message.delete()
    except: pass

async def safe_send_photo(chat_id: int, **kwargs):
    try: return await app.send_photo(chat_id, **kwargs)
    except:
        try:
            caption = kwargs.get("caption", "")
            if "photo" in kwargs: return await app.send_message(chat_id, caption)
        except: return None

async def safe_send_message(chat_id: int, **kwargs):
    try: return await app.send_message(chat_id, **kwargs)
    except: return None

async def _join_call_with_fallback(chat_id, original_chat_id, file_path, video=False, image=None):
    """Robust join function handling version differences."""
    candidates = ["join_call", "join_stream", "join", "start_stream"]
    for name in candidates:
        fn = getattr(StreamController, name, None)
        if callable(fn):
            try:
                res = fn(chat_id, original_chat_id, file_path, video=video, image=image)
                if asyncio.iscoroutine(res): return await res
                return res
            except Exception: continue
    # Fallback to positional args if kwargs fail
    try:
        res = StreamController.join_call(chat_id, original_chat_id, file_path, video, image)
        if asyncio.iscoroutine(res): return await res
    except: pass
    raise RuntimeError("Failed to join call via StreamController.")

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

    # Force Stop if needed
    if forceplay:
        try:
            stop_fn = getattr(StreamController, "force_stop_stream", None)
            if stop_fn: await stop_fn(chat_id)
        except: pass

    # -----------------------------
    # 0) CUSTOM MODE (Your Custom Logic)
    # -----------------------------
    if streamtype == "custom":
        vidid = result.get("vidid")
        title = (result.get("title")).title()
        duration_min = result.get("duration_min")
        thumbnail = result.get("thumb")

        try:
            file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=vidid)
        except:
            raise AssistantErr(_["play_14"])

        if not forceplay: db[chat_id] = []

        try:
            await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
        except:
            raise AssistantErr(_["play_14"])

        await put_queue(
            chat_id, original_chat_id, file_path if direct else f"vid_{vidid}",
            title, duration_min, user_name, vidid, user_id, "video" if is_video else "audio",
            forceplay=forceplay,
        )

        # Custom Buttons Logic
        button = custom_markup(_, chat_id, vidid)
        try:
            await mystic.edit_reply_markup(reply_markup=button)
            db[chat_id][0]["mystic"] = mystic
            db[chat_id][0]["markup"] = "custom"
        except: pass
        return

    # -----------------------------
    # 1) PLAYLIST MODE
    # -----------------------------
    elif streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0
        for search in result:
            if int(count) == config.PLAYLIST_FETCH_LIMIT: continue
            try:
                title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(search, videoid=search)
            except: continue

            if str(duration_min) == "None": continue
            if duration_sec and duration_sec > config.DURATION_LIMIT: continue

            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id, original_chat_id, f"vid_{vidid}", title, duration_min,
                    user_name, vidid, user_id, "video" if is_video else "audio"
                )
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}. {title[:70]}\n{_['play_20']} {position}\n\n"
            else:
                if not forceplay: db[chat_id] = []
                try:
                    file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=vidid)
                except: raise AssistantErr(_["play_14"])

                try:
                    await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
                except: raise AssistantErr(_["play_14"])

                await put_queue(
                    chat_id, original_chat_id, file_path if direct else f"vid_{vidid}",
                    title, duration_min, user_name, vidid, user_id,
                    "video" if is_video else "audio", forceplay=forceplay
                )

                img = await gen_thumb(vidid)
                # ✅ Fixed: 2 args only
                button = stream_markup(_, chat_id)
                await safe_delete(mystic)
                
                try:
                    run = await safe_send_photo(
                        original_chat_id, photo=img,
                        caption="🧚 " + _["stream_1"].format(
                            f"https://t.me/{app.username}?start=info_{vidid}",
                            title[:23], duration_min, user_name
                        ),
                        reply_markup=InlineKeyboardMarkup(button)
                    )
                    if run:
                        db[chat_id][0]["mystic"] = run
                        db[chat_id][0]["markup"] = "stream"
                except: pass

        if count == 0: return
        link = await ANNIEBIN(msg)
        try:
            carbon = await Carbon.generate(msg, randint(100, 10000000))
            playlist_photo = carbon
        except: playlist_photo = config.PLAYLIST_IMG_URL

        upl = close_markup(_)
        return await safe_send_photo(
            original_chat_id, photo=playlist_photo,
            caption="🧚 " + _["play_21"].format(max(len(db.get(chat_id) or []) - 1, 0), link),
            reply_markup=upl
        )

    # -----------------------------
    # 2) YOUTUBE SINGLE MODE
    # -----------------------------
    elif streamtype == "youtube":
        vidid = result.get("vidid")
        title = (result.get("title") or "").title()
        duration_min = result.get("duration_min")
        thumbnail = result.get("thumb")

        try:
            file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=vidid)
        except: raise AssistantErr(_["play_14"])

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id, original_chat_id, file_path if direct else f"vid_{vidid}",
                title, duration_min, user_name, vidid, user_id, "video" if is_video else "audio"
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_delete(mystic)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
            )
        else:
            if not forceplay: db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
            except: raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id, original_chat_id, file_path if direct else f"vid_{vidid}",
                title, duration_min, user_name, vidid, user_id,
                "video" if is_video else "audio", forceplay=forceplay
            )

            img = await gen_thumb(vidid)
            # ✅ Fixed: 2 args only
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)
            try:
                run = await safe_send_photo(
                    original_chat_id, photo=img,
                    caption="🧚 " + _["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{vidid}",
                        title[:23], duration_min, user_name
                    ),
                    reply_markup=InlineKeyboardMarkup(button)
                )
                if run:
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"
            except: pass

    # -----------------------------
    # 3) SOUNDCLOUD MODE
    # -----------------------------
    elif streamtype == "soundcloud":
        file_path = result.get("filepath")
        title = result.get("title")
        duration_min = result.get("duration_min")

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "audio"
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
            )
        else:
            if not forceplay: db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=False)
            except: raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "audio", forceplay=forceplay
            )
            
            # ✅ Use Telegram Markup for Audio
            button = telegram_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id, photo=config.SOUNCLOUD_IMG_URL,
                caption="🧚 " + _["stream_1"].format(config.SUPPORT_CHAT, title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
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

        if await is_active_chat(chat_id):
            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "video" if is_video else "audio"
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
            )
        else:
            if not forceplay: db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video)
            except: raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id, original_chat_id, file_path, title, duration_min,
                user_name, streamtype, user_id, "video" if is_video else "audio",
                forceplay=forceplay
            )
            if is_video: await add_active_video_chat(chat_id)
            
            # ✅ Use Telegram Markup
            button = telegram_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id,
                photo=config.TELEGRAM_VIDEO_URL if is_video else config.TELEGRAM_AUDIO_URL,
                caption="🧚 " + _["stream_1"].format(link, title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
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
                chat_id, original_chat_id, f"live_{vidid}", title, duration_min,
                user_name, vidid, user_id, "video" if is_video else "audio"
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await safe_send_message(
                original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
            )
        else:
            if not forceplay: db[chat_id] = []
            n, file_path = await YouTube.video(link)
            if n == 0 or not file_path: raise AssistantErr(_["str_3"])
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, file_path, video=is_video, image=thumbnail)
            except: raise AssistantErr(_["play_14"])

            await put_queue(
                chat_id, original_chat_id, f"live_{vidid}", title, duration_min,
                user_name, vidid, user_id, "video" if is_video else "audio",
                forceplay=forceplay
            )
            img = await gen_thumb(vidid)
            # ✅ Fixed: 2 args only
            button = stream_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id, photo=img,
                caption="🧚 " + _["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button)
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
                chat_id, original_chat_id, "index_url", title, duration_min,
                user_name, link, "video" if is_video else "audio"
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await mystic.edit_text(
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button)
            )
        else:
            if not forceplay: db[chat_id] = []
            try:
                await _join_call_with_fallback(chat_id, original_chat_id, link, video=is_video)
            except: raise AssistantErr(_["play_14"])

            await put_queue_index(
                chat_id, original_chat_id, "index_url", title, duration_min,
                user_name, link, "video" if is_video else "audio", forceplay=forceplay
            )
            # ✅ Use Telegram Markup for Index
            button = telegram_markup(_, chat_id)
            await safe_delete(mystic)
            run = await safe_send_photo(
                original_chat_id, photo=config.STREAM_IMG_URL,
                caption="🧚 " + _["stream_2"].format(user_name),
                reply_markup=InlineKeyboardMarkup(button)
            )
            if run:
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
