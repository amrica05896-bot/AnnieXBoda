# Authored By Certified Coders © 2026
# Fixed for utils/stream/stream.py
# FIX: Smart Button Logic added safely to Original Code

import asyncio
import os
from typing import Union
from random import randint

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

import config
from AnnieXMedia import Carbon, YouTube, app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import (
    add_active_video_chat,
    is_active_chat,
)
from AnnieXMedia.utils.exceptions import AssistantErr
# استدعاء الدوال الأصلية
from AnnieXMedia.utils.inline import aq_markup, close_markup, stream_markup
from AnnieXMedia.utils.pastebin import ANNIEBIN
from AnnieXMedia.utils.stream.queue import put_queue, put_queue_index
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

async def safe_delete(message):
    try:
        await message.delete()
    except:
        pass

# 🛑 دالة الأزرار الـ 4 (للأغاني Song) - أضيفت هنا لعدم تغيير ملف inline
def get_custom_buttons(chat_id, vidid):
    return [
        [
            InlineKeyboardButton(text="▷", callback_data=f"stream_admin Resume|{chat_id}"),
            InlineKeyboardButton(text="II", callback_data=f"stream_admin Pause|{chat_id}"),
            InlineKeyboardButton(text="↻", callback_data=f"stream_admin Replay|{chat_id}"),
            InlineKeyboardButton(text="▢", callback_data=f"song_stop_custom|{chat_id}|{vidid}"),
        ]
    ]

# 🛑 دالة أزرار الأذان (إغلاق فقط)
def get_adhan_buttons():
    return [[InlineKeyboardButton(text="إغلاق", callback_data="close")]]

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
        await StreamController.force_stop_stream(chat_id)

    # ==========================
    # 0. ADHAN MODE (الجديد - بدون أزرار)
    # ==========================
    if streamtype == "adhan":
        link = result.get("link")
        vidid = result.get("vidid", "adhan_call")
        title = result.get("title", "Adhan")
        duration_min = result.get("duration_min", "04:00")
        
        if not link: return

        if not forceplay:
            db[chat_id] = []
            
        file_path = None
        try:
            if "youtube" in link or "youtu.be" in link:
                try:
                    file_path, direct = await YouTube.download(vidid, mystic, video=False, videoid=vidid)
                except:
                    file_path = link
            else:
                file_path = link
        except:
            file_path = link
            
        if not file_path: return

        await StreamController.join_call(chat_id, original_chat_id, file_path, video=False, image=None)
        
        await put_queue(
            chat_id, original_chat_id, f"adhan_{vidid}", title, duration_min, "System", vidid, user_id, "audio", forceplay=True
        )
        
        # استخدام أزرار الأذان (إغلاق فقط)
        button = get_adhan_buttons()
        await safe_delete(mystic)
        
        caption_text = f"<b>🕋 {title}</b>\n\nالله أكبر، الله أكبر."
        
        try:
            img = result.get("thumb") or config.STREAM_IMG_URL
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=caption_text,
                reply_markup=InlineKeyboardMarkup(button),
            )
            # حفظ النوع "adhan"
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "adhan" 
        except Exception:
            pass
        return

    # ==========================
    # 1. PLAYLIST MODE (أصلي - أزرار كاملة)
    # ==========================
    elif streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0
        for search in result:
            if int(count) == config.PLAYLIST_FETCH_LIMIT:
                continue
            try:
                title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(
                    search, videoid=search
                )
            except Exception:
                continue

            if str(duration_min) == "None":
                continue
            if duration_sec and duration_sec > config.DURATION_LIMIT:
                continue

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
                try:
                    file_path, direct = await YouTube.download(
                        vidid, mystic, video=is_video, videoid=vidid
                    )
                except Exception:
                    raise AssistantErr(_["play_14"])

                await StreamController.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=is_video,
                    image=thumbnail,
                )
                
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
                # استخدام stream_markup الأصلية (كل الأزرار)
                button = stream_markup(_, chat_id)
                
                await safe_delete(mystic)
                
                caption_text = "🧚 " + _["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                )
                try:
                    run = await app.send_photo(
                        original_chat_id,
                        photo=img,
                        caption=caption_text,
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "stream"
                except Exception:
                    pass

        if count == 0:
            return
        
        link = await ANNIEBIN(msg)
        try:
            carbon = await Carbon.generate(msg, randint(100, 10000000))
            playlist_photo = carbon
        except:
            playlist_photo = config.PLAYLIST_IMG_URL
            
        upl = close_markup(_)
        final_position = len(db.get(chat_id) or []) - 1
        return await app.send_photo(
            original_chat_id,
            photo=playlist_photo,
            caption="🧚 " + _["play_21"].format(final_position, link),
            reply_markup=upl,
        )

    # ==========================
    # 2. YOUTUBE MODE (يدعم Custom و Original)
    # ==========================
    elif streamtype == "youtube" or streamtype == "custom":
        link = result.get("link")
        vidid = result.get("vidid")
        title = (result.get("title")).title()
        duration_min = result.get("duration_min")
        thumbnail = result.get("thumb")

        try:
            file_path, direct = await YouTube.download(
                vidid, mystic, video=is_video, videoid=vidid
            )
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
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            await StreamController.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
                image=thumbnail,
            )
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
            
            # 🛑 التحكم في الأزرار بناءً على الطلب
            if streamtype == "custom":
                # لو جاي من song.py بكلمة custom -> 4 زرارير
                button = get_custom_buttons(chat_id, vidid)
                markup_type = "custom"
            else:
                # لو يوتيوب عادي -> كل الزرارير
                button = stream_markup(_, chat_id)
                markup_type = "stream"
            
            await safe_delete(mystic)
            
            caption_text = "🧚 " + _["stream_1"].format(
                f"https://t.me/{app.username}?start=info_{vidid}",
                title[:23],
                duration_min,
                user_name,
            )
            try:
                run = await app.send_photo(
                    original_chat_id,
                    photo=img,
                    caption=caption_text,
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                # 🛑 حفظ النوع للتايمر
                db[chat_id][0]["markup"] = markup_type
            except Exception:
                pass

    # ==========================
    # 3. SOUNDCLOUD MODE
    # ==========================
    elif streamtype == "soundcloud":
        # ... (نفس الكود الأصلي)
        # فقط تأكد في النهاية من حفظ markup="stream"
        file_path = result.get("filepath")
        title = result.get("title")
        duration_min = result.get("duration_min")
        
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
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await StreamController.join_call(chat_id, original_chat_id, file_path, video=False)
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
            
            run = await app.send_photo(
                original_chat_id,
                photo=config.SOUNCLOUD_IMG_URL,
                caption="🧚 " + _["stream_1"].format(
                    config.SUPPORT_CHAT, title[:23], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"

    # ==========================
    # 4. TELEGRAM FILES
    # ==========================
    elif streamtype == "telegram":
        # ... (نفس الكود الأصلي)
        # فقط تأكد في النهاية من حفظ markup="stream"
        file_path = result.get("path")
        link = result.get("link")
        title = (result.get("title")).title()
        duration_min = result.get("dur", result.get("duration_min", "00:00"))

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
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await StreamController.join_call(chat_id, original_chat_id, file_path, video=is_video)
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
            
            run = await app.send_photo(
                original_chat_id,
                photo=config.TELEGRAM_VIDEO_URL if is_video else config.TELEGRAM_AUDIO_URL,
                caption="🧚 " + _["stream_1"].format(link, title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"

    # ==========================
    # 5. LIVE / INDEX MODE
    # ==========================
    elif streamtype == "live" or streamtype == "index":
        link = result.get("link") if streamtype == "live" else result
        vidid = result.get("vidid") if streamtype == "live" else link
        title = (result.get("title", "رابط خارجي")).title()
        thumbnail = result.get("thumb") if streamtype == "live" else config.STREAM_IMG_URL
        duration_min = "Live Track" if streamtype == "live" else "00:00"

        if await is_active_chat(chat_id):
            if streamtype == "live":
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
            else:
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
            
            if streamtype == "live":
                await app.send_message(
                    chat_id=original_chat_id,
                    text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                await mystic.edit_text(
                    text="🧚 " + _["queue_4"].format(position, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
        else:
            if not forceplay:
                db[chat_id] = []
            
            if streamtype == "live":
                n, file_path = await YouTube.video(link)
                if n == 0:
                    raise AssistantErr(_["str_3"])
            else:
                file_path = link

            await StreamController.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
                image=thumbnail or None,
            )
            
            if streamtype == "live":
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
            else:
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
            
            img = (await get_thumb(vidid)) if streamtype == "live" else config.STREAM_IMG_URL
            caption = _["stream_1"].format(f"https://t.me/{app.username}?start=info_{vidid}", title[:23], duration_min, user_name) if streamtype == "live" else _["stream_2"].format(user_name)
            
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption="🧚 " + caption,
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
