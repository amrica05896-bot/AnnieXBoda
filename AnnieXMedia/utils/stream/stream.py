# Authored By Certified Coders © 2026
# System: Stream Controller (Logic & Queue Bridge)
# Updated: Python 3.13 Native, DRY Code, Direct Link Expiration Fix

import asyncio
from random import randint
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from AnnieXMedia import Carbon, YouTube, app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import (
    add_active_video_chat,
    is_active_chat,
)
from AnnieXMedia.utils.exceptions import AssistantErr
from AnnieXMedia.utils.inline import aq_markup, close_markup, stream_markup
from AnnieXMedia.utils.inline.custom import custom_markup 
from AnnieXMedia.utils.pastebin import ANNIEBIN
from AnnieXMedia.utils.stream.queue import put_queue, put_queue_index
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err


# --- Helper: Python 3.13 Safe Message Deletion ---
async def safe_delete(message):
    try:
        if message:
            await message.delete()
    except Exception:
        pass


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
    is_video = bool(video)

    # Force Stop logic
    if forceplay:
        await StreamController.force_stop_stream(chat_id)

    def get_download_id(vid):
        return f"{vid}_v" if is_video else vid

    # ==========================
    # 1. CUSTOM MODE (Inline File Playback)
    # ==========================
    if streamtype == "custom":
        link = result["link"]
        vidid = result["vidid"]
        title = result["title"].title()
        duration_min = result["duration_min"]
        
        try:
            file_path, direct = await YouTube.download(
                vidid, None, video=is_video, videoid=get_download_id(vidid)
            )
        except Exception:
            return await app.send_message(original_chat_id, text=_["play_14"])
        
        if not file_path:
            return await app.send_message(original_chat_id, text=_["play_14"])

        try:
            await StreamController.join_call(chat_id, original_chat_id, file_path, video=is_video)
        except AssistantErr as e:
            return await app.send_message(original_chat_id, text=str(e))
        except Exception as e:
            return await app.send_message(original_chat_id, text=f"Error: {e}")

        db[chat_id] = [] 
        await put_queue(
            chat_id, original_chat_id, file_path if direct else f"vid_{vidid}",
            title, duration_min, user_name, vidid, user_id,
            "video" if is_video else "audio", forceplay=True,
        )

        button = custom_markup(_, chat_id, vidid)
        try:
            await mystic.edit_reply_markup(reply_markup=button)
        except Exception:
            await app.send_message(original_chat_id, text="✅ ᴘʟᴀʏɪɴɢ", reply_markup=button)

        db[chat_id][0]["mystic"] = mystic
        db[chat_id][0]["markup"] = "custom"
        return

    # ==========================
    # 2. PLAYLIST MODE
    # ==========================
    if streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0
        for search in result:
            if count == config.PLAYLIST_FETCH_LIMIT:
                break
            try:
                title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(search, videoid=search)
            except Exception:
                continue

            if str(duration_min) == "None": continue
            if duration_sec and duration_sec > config.DURATION_LIMIT: continue

            if await is_active_chat(chat_id):
                # Save identifier 'vid_{vidid}' NOT direct link
                await put_queue(
                    chat_id, original_chat_id, f"vid_{vidid}", title, duration_min,
                    user_name, vidid, user_id, "video" if is_video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}. {title[:70]}\n{_['play_20']} {position}\n\n"
            else:
                if not forceplay: db[chat_id] = []
                try:
                    file_path, direct = await YouTube.download(vidid, mystic, video=is_video, videoid=get_download_id(vidid))
                    if not file_path: continue
                    await StreamController.join_call(chat_id, original_chat_id, file_path, video=is_video)
                except Exception as e:
                    continue

                await put_queue(
                    chat_id, original_chat_id, f"vid_{vidid}", title, duration_min,
                    user_name, vidid, user_id, "video" if is_video else "audio", forceplay=forceplay,
                )
                
                img = await get_thumb(vidid)
                button = stream_markup(_, chat_id)
                await safe_delete(mystic)

                run = await app.send_photo(
                    original_chat_id, photo=img,
                    caption=_["stream_1"].format(f"https://t.me/{app.username}?start=info_{vidid}", title[:23], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
                count += 1

        if count == 0: return
        link = await ANNIEBIN(msg)
        try:
            playlist_photo = await Carbon.generate(msg, randint(100, 10000000))
        except:
            playlist_photo = config.PLAYLIST_IMG_URL
            
        upl = close_markup(_)
        final_position = len(db.get(chat_id) or []) - 1
        return await app.send_photo(
            original_chat_id, photo=playlist_photo,
            caption=_["play_21"].format(final_position, link), reply_markup=upl,
        )

    # ==========================
    # 3. UNIFIED MEDIA MODE (YT, SC, TG, LIVE, INDEX)
    # ==========================
    # Extract details safely
    is_index = (streamtype == "index")
    is_live = (streamtype == "live")
    
    if is_index:
        link = file_path = vidid = result
        title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"
        duration_min = "00:00"
    else:
        link = result.get("link", "")
        vidid = result.get("vidid", "")
        title = result.get("title", "").title()
        duration_min = "Live Track" if is_live else result.get("duration_min", result.get("dur", "00:00"))
        file_path = result.get("path", result.get("filepath", ""))

    # --- Handle Queue Path ---
    # Crucial Fix: Store 'vid_id' instead of expiring direct URLs for YouTube
    if streamtype == "youtube":
        q_path = f"vid_{vidid}"
    elif is_live:
        q_path = f"live_{vidid}"
    elif is_index:
        q_path = "index_url"
    else:
        q_path = file_path

    is_active = await is_active_chat(chat_id)

    # --- ACTION 1: ADD TO QUEUE ---
    if is_active and not forceplay:
        if is_index:
            await put_queue_index(chat_id, original_chat_id, q_path, title, duration_min, user_name, link, "video" if is_video else "audio")
        else:
            await put_queue(chat_id, original_chat_id, q_path, title, duration_min, user_name, vidid, user_id, "video" if is_video else "audio")
        
        position = len(db.get(chat_id)) - 1
        button = aq_markup(_, chat_id)
        
        if is_index:
            await mystic.edit_text(text=_["queue_4"].format(position, title[:27], duration_min, user_name), reply_markup=InlineKeyboardMarkup(button))
        else:
            await safe_delete(mystic)
            await app.send_message(original_chat_id, text=_["queue_4"].format(position, title[:27], duration_min, user_name), reply_markup=InlineKeyboardMarkup(button))
        return

    # --- ACTION 2: PLAY IMMEDIATELY ---
    if not forceplay: db[chat_id] = []

    # Get streamable direct path based on type
    play_path = file_path
    try:
        if streamtype == "youtube":
            play_path, _ = await YouTube.download(vidid, mystic, video=is_video, videoid=get_download_id(vidid))
        elif is_live:
            n, play_path = await YouTube.video(link)
            if n == 0: raise AssistantErr(_["str_3"])
        elif is_index:
            play_path = link

        if not play_path: raise AssistantErr(_["play_14"])
        await StreamController.join_call(chat_id, original_chat_id, play_path, video=is_video)
    except AssistantErr as e:
        await safe_delete(mystic)
        return await app.send_message(original_chat_id, text=str(e))
    except Exception as e:
        await safe_delete(mystic)
        return await app.send_message(original_chat_id, text=f"Error: {e}")

    # Register in DB as currently playing
    if is_index:
        await put_queue_index(chat_id, original_chat_id, q_path, title, duration_min, user_name, link, "video" if is_video else "audio", forceplay=True)
    else:
        await put_queue(chat_id, original_chat_id, q_path, title, duration_min, user_name, vidid, user_id, "video" if is_video else "audio", forceplay=True)

    if streamtype == "telegram" and is_video:
        await add_active_video_chat(chat_id)

    # UI Setup
    await safe_delete(mystic)
    button = stream_markup(_, chat_id)

    if streamtype == "soundcloud":
        photo = config.SOUNCLOUD_IMG_URL
        caption = _["stream_1"].format(config.SUPPORT_CHAT, title[:23], duration_min, user_name)
    elif streamtype == "telegram":
        photo = config.TELEGRAM_VIDEO_URL if is_video else config.TELEGRAM_AUDIO_URL
        caption = _["stream_1"].format(link, title[:23], duration_min, user_name)
    elif streamtype == "index":
        photo = config.STREAM_IMG_URL
        caption = _["stream_2"].format(user_name)
    else: # YouTube & Live
        photo = await get_thumb(vidid)
        caption = _["stream_1"].format(f"https://t.me/{app.username}?start=info_{vidid}", title[:23], duration_min, user_name)

    run = await app.send_photo(
        original_chat_id, photo=photo, caption=caption, reply_markup=InlineKeyboardMarkup(button)
    )
    
    db[chat_id][0]["mystic"] = run
    db[chat_id][0]["markup"] = "tg" if streamtype in ["soundcloud", "telegram", "live", "index"] else "stream"
