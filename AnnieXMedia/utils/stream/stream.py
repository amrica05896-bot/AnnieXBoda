# Authored By Certified Coders © 2026
# System: Stream Controller (Logic & Queue Bridge)
# Updated: Added 'custom' streamtype for Inline Song Playback

import asyncio
import os
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
# 🔥 استدعاء ملف الأزرار الخاص بيك
from AnnieXMedia.utils.inline.custom import custom_markup 
from AnnieXMedia.utils.pastebin import ANNIEBIN
from AnnieXMedia.utils.stream.queue import put_queue, put_queue_index
from AnnieXMedia.utils.thumbnails import get_thumb
from AnnieXMedia.utils.errors import capture_internal_err

# --- Helper: Safe Message Deletion ---
async def safe_delete(message):
    try:
        if message: await message.delete()
    except:
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

    # Force Stop logic for 'forceplay'
    if forceplay:
        await StreamController.force_stop_stream(chat_id)

    def get_download_id(vid):
        return f"{vid}_v" if is_video else vid

    # ==========================
    # 🔥 حالة CUSTOM (لتشغيل الملف وتغيير أزراره)
    # ==========================
    if streamtype == "custom":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        
        # 1. التنزيل (أو جلب الرابط المباشر)
        try:
            # نمرر None مكان mystic عشان الـ Downloader مغيرش الكابشن بتاع أغنية الملف
            file_path, direct = await YouTube.download(
                vidid, 
                None, 
                video=is_video, 
                videoid=get_download_id(vidid)
            )
        except Exception:
            # لو فشل، بنرجع الأزرار الأصلية أو نبعت تنبيه بسيط
            return await app.send_message(original_chat_id, text=_["play_14"])
        
        if not file_path:
            return await app.send_message(original_chat_id, text=_["play_14"])

        # 2. تشغيل في الكول
        try:
            await StreamController.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
            )
        except AssistantErr as e:
            return await app.send_message(original_chat_id, text=str(e))
        except Exception as e:
            return await app.send_message(original_chat_id, text=f"Error: {e}")

        # 3. وضع البيانات في الطابور
        # بنمسح الطابور القديم عشان ده Force Play
        db[chat_id] = [] 
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
            forceplay=True,
        )

        # 4. 🔥 السحر هنا: تعديل رسالة الملف للأزرار الجديدة
        # mystic هنا هي رسالة الملف نفسها اللي اتبعتت من song.py
        button = custom_markup(_, chat_id, vidid)
        
        try:
            await mystic.edit_reply_markup(reply_markup=button)
        except:
            # لو معرفش يعدل، يبعت رسالة جديدة احتياطي
            await app.send_message(
                original_chat_id,
                text="✅ تم التشغيل",
                reply_markup=button
            )

        # تسجيل الرسالة دي كـ "التحكم" في الداتا بيز
        db[chat_id][0]["mystic"] = mystic
        db[chat_id][0]["markup"] = "custom"
        return

    # ==========================
    # 1. PLAYLIST MODE
    # ==========================
    if streamtype == "playlist":
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

            if str(duration_min) == "None": continue
            if duration_sec and duration_sec > config.DURATION_LIMIT: continue

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
                        vidid, mystic, video=is_video, videoid=get_download_id(vidid)
                    )
                except Exception:
                    continue
                
                if not file_path: continue

                try:
                    # v3.0 Update: Removed 'image' param from join_call
                    await StreamController.join_call(
                        chat_id,
                        original_chat_id,
                        file_path,
                        video=is_video,
                    )
                except AssistantErr as e:
                    await safe_delete(mystic)
                    await app.send_message(original_chat_id, text=str(e))
                    return
                except Exception as e:
                    await safe_delete(mystic)
                    await app.send_message(original_chat_id, text=f"Error: {e}")
                    return

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

                run = await app.send_photo(
                    original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{vidid}",
                        title[:23],
                        duration_min,
                        user_name,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"

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
            caption=_["play_21"].format(final_position, link),
            reply_markup=upl,
        )

    # ==========================
    # 2. YOUTUBE MODE (Single Track)
    # ==========================
    elif streamtype == "youtube":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        thumbnail = result["thumb"]

        try:
            file_path, direct = await YouTube.download(
                vidid, mystic, video=is_video, videoid=get_download_id(vidid)
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
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            try:
                # v3.0 Update: Removed 'image' param
                await StreamController.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=is_video,
                )
            except AssistantErr as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return
            except Exception as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=f"Error: {e}")
                return

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
            
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"

    # ==========================
    # 3. SOUNDCLOUD MODE
    # ==========================
    elif streamtype == "soundcloud":
        file_path = result["filepath"]
        title = result["title"]
        duration_min = result["duration_min"]
        
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
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            try:
                # v3.0 Update: Removed 'image' param
                await StreamController.join_call(chat_id, original_chat_id, file_path, video=False)
            except AssistantErr as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return
            except Exception as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return

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
                caption=_["stream_1"].format(
                    config.SUPPORT_CHAT, title[:23], duration_min, user_name
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

    # ==========================
    # 4. TELEGRAM FILES
    # ==========================
    elif streamtype == "telegram":
        file_path = result["path"]
        link = result["link"]
        title = (result["title"]).title()
        duration_min = result["dur"]
        
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
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            try:
                # v3.0 Update: Removed 'image' param
                await StreamController.join_call(chat_id, original_chat_id, file_path, video=is_video)
            except AssistantErr as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return
            except Exception as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return

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
                caption=_["stream_1"].format(link, title[:23], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

    # ==========================
    # 5. LIVE / INDEX MODE
    # ==========================
    elif streamtype == "live":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        thumbnail = result["thumb"]
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
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            n, file_path = await YouTube.video(link)
            if n == 0:
                raise AssistantErr(_["str_3"])
            if not file_path:
                raise AssistantErr(_["play_14"])

            try:
                # v3.0 Update: Removed 'image' param
                await StreamController.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=is_video,
                )
            except AssistantErr as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return
            except Exception as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return

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
            
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"

    elif streamtype == "index":
        link = result
        title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"
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
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            
            try:
                # v3.0 Update: Removed 'image' param
                await StreamController.join_call(
                    chat_id,
                    original_chat_id,
                    link,
                    video=is_video,
                )
            except AssistantErr as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return
            except Exception as e:
                await safe_delete(mystic)
                await app.send_message(original_chat_id, text=str(e))
                return

            await put_queue(
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

            run = await app.send_photo(
                original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption=_["stream_2"].format(user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
