# Authored By Certified Coders © 2026
# Fixed for utils/stream/stream.py
# SYSTEM: Universal Stream Handler (Adhan / Songs / Playlists)

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
# 🛑 Removed external markup imports to ensure independence
from AnnieXMedia.utils.pastebin import ANNIEBIN
from AnnieXMedia.utils.stream.queue import put_queue, put_queue_index
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

async def safe_delete(message):
    try:
        await message.delete()
    except:
        pass

def get_safe_text(dictionary, key, default):
    try:
        if isinstance(dictionary, dict) and key in dictionary:
            return dictionary[key]
        return default
    except:
        return default

# ==========================================================
# 🛑 نظام الأزرار الذكي (Smart Button System)
# ==========================================================

# 1. أزرار الموسيقى الكاملة (للبلاي ليست واليوتيوب العادي)
def get_full_buttons(chat_id, vidid):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="▷", callback_data=f"stream_admin Resume|{chat_id}"),
                InlineKeyboardButton(text="II", callback_data=f"stream_admin Pause|{chat_id}"),
                InlineKeyboardButton(text="↻", callback_data=f"stream_admin Replay|{chat_id}"),
                InlineKeyboardButton(text="‣‣I", callback_data=f"stream_admin Skip|{chat_id}"), 
                InlineKeyboardButton(text="▢", callback_data=f"stream_admin Stop|{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="إغلاق", callback_data="close")
            ]
        ]
    )

# 2. أزرار الأغنية المباشرة (4 أزرار فقط)
def get_song_buttons(chat_id, vidid):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="▷", callback_data=f"stream_admin Resume|{chat_id}"),
                InlineKeyboardButton(text="II", callback_data=f"stream_admin Pause|{chat_id}"),
                InlineKeyboardButton(text="↻", callback_data=f"stream_admin Replay|{chat_id}"),
                InlineKeyboardButton(text="▢", callback_data=f"song_stop_custom|{chat_id}|{vidid}"),
            ]
        ]
    )

# 3. أزرار الأذان (زر إغلاق فقط)
def get_adhan_buttons():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="إغلاق", callback_data="close"),
            ]
        ]
    )

# دالة اختيار الأزرار حسب النوع
def select_buttons(ctype, cid, vid):
    if ctype == "adhan":
        return get_adhan_buttons()
    elif ctype == "custom" or ctype == "song_custom": 
        return get_song_buttons(cid, vid)
    else: 
        return get_full_buttons(cid, vid)

# ==========================================================
# 🛑 المحرك الرئيسي (Stream Engine)
# ==========================================================

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

    # إيقاف التشغيل السابق إذا كان إجبارياً (مثل الأذان)
    if forceplay:
        try:
            await StreamController.force_stop_stream(chat_id)
        except:
            pass

    # نصوص احتياطية
    TXT_STREAM_1 = "<b>بدأ التشغيل</b>\n\n<b>العنوان:</b> <a href={0}>{1}</a>\n<b>المدة:</b> {2} دقيقة\n<b>بواسطة:</b> {3}"
    TXT_STREAM_2 = "<b>بدأ التشغيل (مباشر)</b>\n\n<b>النوع:</b> بث مباشر\n<b>بواسطة:</b> {0}"
    TXT_QUEUE_4 = "<b>تمت الإضافة للقائمة #{0}</b>\n\n<b>العنوان:</b> {1}\n<b>المدة:</b> {2} دقيقة\n<b>بواسطة:</b> {3}"
    TXT_PLAY_19 = "قائمة التشغيل المضافة:"
    TXT_PLAY_20 = "الموضع في القائمة -"
    TXT_PLAY_21 = "تمت إضافة {0} مقاطع.\n\n<b>تحقق:</b> <a href={1}>اضغط هنا</a>"

    # ==========================
    # 1. ADHAN MODE (نظام الأذان)
    # ==========================
    if streamtype == "adhan":
        # استخراج البيانات القادمة من az_utils
        link = result.get("link")
        vidid = result.get("vidid", "adhan_call")
        title = result.get("title", "Adhan")
        duration_min = result.get("duration_min", "04:00")
        
        # تفريغ القائمة الحالية (لأن الأذان أهم)
        if not forceplay:
            db[chat_id] = []
            
        # محاولة تجهيز الرابط (سواء يوتيوب أو مباشر)
        try:
            if "youtube" in link or "youtu.be" in link:
                file_path, direct = await YouTube.download(
                    vidid, mystic, video=False, videoid=vidid
                )
            else:
                file_path = link
        except:
            file_path = link
            
        # الانضمام وتشغيل الصوت
        await StreamController.join_call(
            chat_id,
            original_chat_id,
            file_path,
            video=False,
            image=None,
        )
        
        # إضافة لقائمة الانتظار (عشان السيستم يفضل شغال)
        await put_queue(
            chat_id,
            original_chat_id,
            f"adhan_{vidid}",
            title,
            duration_min,
            "System",
            vidid,
            user_id,
            "audio",
            forceplay=True,
        )
        
        # استخدام أزرار الأذان (إغلاق فقط)
        button = get_adhan_buttons()
        
        await safe_delete(mystic)
        
        # رسالة الأذان
        caption_text = f"<b>🕋 {title}</b>\n\nاللهم رب هذه الدعوة التامة والصلاة القائمة."
        
        try:
            img = result.get("thumb") or config.STREAM_IMG_URL
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=caption_text,
                reply_markup=button,
            )
            # تحديث قاعدة البيانات عشان الـ Play.py يفهم إن ده أذان
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream" 
        except Exception:
            pass
        return

    # ==========================
    # 2. PLAYLIST MODE
    # ==========================
    elif streamtype == "playlist":
        p19 = get_safe_text(_, "play_19", TXT_PLAY_19)
        msg = f"{p19}\n\n"
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
                p20 = get_safe_text(_, "play_20", TXT_PLAY_20)
                msg += f"{count}. {title[:70]}\n"
                msg += f"{p20} {position}\n\n"
            else:
                if not forceplay:
                    db[chat_id] = []
                try:
                    file_path, direct = await YouTube.download(
                        vidid, mystic, video=is_video, videoid=vidid
                    )
                except Exception:
                    raise AssistantErr(get_safe_text(_, "play_14", "فشل التشغيل"))

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
                # أزرار كاملة للبلاي ليست
                button = select_buttons("youtube", chat_id, vidid)
                
                await safe_delete(mystic)
                
                base_txt = get_safe_text(_, "stream_1", TXT_STREAM_1)
                caption_text = "🧚 " + base_txt.format(
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
                        reply_markup=button,
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
            
        upl = InlineKeyboardMarkup([[InlineKeyboardButton(text="إغلاق", callback_data="close")]])
        final_position = len(db.get(chat_id) or []) - 1
        
        p21 = get_safe_text(_, "play_21", TXT_PLAY_21)
        return await app.send_photo(
            original_chat_id,
            photo=playlist_photo,
            caption="🧚 " + p21.format(final_position, link),
            reply_markup=upl,
        )

    # ==========================
    # 3. YOUTUBE MODE
    # ==========================
    elif streamtype == "youtube":
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
            raise AssistantErr(get_safe_text(_, "play_14", "فشل التشغيل"))

        if not file_path:
             raise AssistantErr(get_safe_text(_, "play_14", "فشل التشغيل"))

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
            # زر إغلاق للقائمة
            button = InlineKeyboardMarkup([[InlineKeyboardButton(text="إغلاق", callback_data="close")]])
            await safe_delete(mystic)
            
            q4 = get_safe_text(_, "queue_4", TXT_QUEUE_4)
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + q4.format(position, title[:27], duration_min, user_name),
                reply_markup=button,
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
            # 🛑 استخدام المصنع لتحديد الأزرار (كاملة أو مخصصة حسب الطلب)
            # لو جاي من Song.py هنبعتله custom عشان يطلع الـ 4 زرارير
            # لو يوتيوب عادي، هيطلع الزراير الكاملة
            button = select_buttons(streamtype, chat_id, vidid)
            
            await safe_delete(mystic)
            
            base_txt = get_safe_text(_, "stream_1", TXT_STREAM_1)
            caption_text = "🧚 " + base_txt.format(
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
                    reply_markup=button,
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
            except Exception:
                pass

    # ==========================
    # 4. SOUNDCLOUD MODE
    # ==========================
    elif streamtype == "soundcloud":
        file_path = result.get("filepath")
        title = result.get("title")
        duration_min = result.get("duration_min")
        vidid = result.get("vidid", "soundcloud")
        
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
            button = InlineKeyboardMarkup([[InlineKeyboardButton(text="إغلاق", callback_data="close")]])
            q4 = get_safe_text(_, "queue_4", TXT_QUEUE_4)
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + q4.format(position, title[:27], duration_min, user_name),
                reply_markup=button,
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
            
            button = select_buttons(streamtype, chat_id, vidid)
            await safe_delete(mystic)
            
            base_txt = get_safe_text(_, "stream_1", TXT_STREAM_1)
            run = await app.send_photo(
                original_chat_id,
                photo=config.SOUNCLOUD_IMG_URL,
                caption="🧚 " + base_txt.format(
                    config.SUPPORT_CHAT, title[:23], duration_min, user_name
                ),
                reply_markup=button,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

    # ==========================
    # 5. TELEGRAM FILES
    # ==========================
    elif streamtype == "telegram":
        file_path = result.get("path")
        link = result.get("link")
        title = (result.get("title")).title()
        duration_min = result.get("dur", result.get("duration_min", "00:00"))
        vidid = link 

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
            button = InlineKeyboardMarkup([[InlineKeyboardButton(text="إغلاق", callback_data="close")]])
            q4 = get_safe_text(_, "queue_4", TXT_QUEUE_4)
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + q4.format(position, title[:27], duration_min, user_name),
                reply_markup=button,
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
            
            button = select_buttons("youtube", chat_id, vidid) # تيليجرام يأخذ أزرار كاملة
            await safe_delete(mystic)
            
            base_txt = get_safe_text(_, "stream_1", TXT_STREAM_1)
            run = await app.send_photo(
                original_chat_id,
                photo=config.TELEGRAM_VIDEO_URL if is_video else config.TELEGRAM_AUDIO_URL,
                caption="🧚 " + base_txt.format(link, title[:23], duration_min, user_name),
                reply_markup=button,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

    # ==========================
    # 6. LIVE / INDEX MODE
    # ==========================
    elif streamtype == "live":
        link = result.get("link")
        vidid = result.get("vidid")
        title = (result.get("title")).title()
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
            button = InlineKeyboardMarkup([[InlineKeyboardButton(text="إغلاق", callback_data="close")]])
            q4 = get_safe_text(_, "queue_4", TXT_QUEUE_4)
            await app.send_message(
                chat_id=original_chat_id,
                text="🧚 " + q4.format(position, title[:27], duration_min, user_name),
                reply_markup=button,
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            n, file_path = await YouTube.video(link)
            if n == 0:
                raise AssistantErr(get_safe_text(_, "str_3", "فشل البث"))

            await StreamController.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
                image=thumbnail or None,
            )
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
            button = select_buttons("youtube", chat_id, vidid)
            await safe_delete(mystic)
            
            base_txt = get_safe_text(_, "stream_1", TXT_STREAM_1)
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption="🧚 " + base_txt.format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                ),
                reply_markup=button,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

    elif streamtype == "index":
        link = result
        title = "رابط خارجي"
        duration_min = "00:00"
        vidid = link # Use link as ID

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
            button = InlineKeyboardMarkup([[InlineKeyboardButton(text="إغلاق", callback_data="close")]])
            q4 = get_safe_text(_, "queue_4", TXT_QUEUE_4)
            await mystic.edit_text(
                text="🧚 " + q4.format(position, title[:27], duration_min, user_name),
                reply_markup=button,
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await StreamController.join_call(
                chat_id,
                original_chat_id,
                link,
                video=is_video,
            )
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
            
            button = select_buttons("youtube", chat_id, vidid)
            await safe_delete(mystic)
            
            base_txt = get_safe_text(_, "stream_2", TXT_STREAM_2)
            run = await app.send_photo(
                original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption="🧚 " + base_txt.format(user_name),
                reply_markup=button,
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
