# song.py
# Song plugin for AnnieXMedia — uses YouTube platform and SongDownloader
# Clean ASCII header

import os
import re
import asyncio
import traceback
from typing import Optional

from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# imports from your project
from config import BANNED_USERS, SONG_DOWNLOAD_DURATION, SONG_DOWNLOAD_DURATION_LIMIT, OWNER_ID
from AnnieXMedia import app
from AnnieXMedia.platforms import YouTube, SongDownloader
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import get_config, set_config

SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# helper: fallback URL extractor if YouTube.url missing
def extract_url_from_message(message: Message) -> Optional[str]:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    if not text:
        return None
    # simple regex for youtube url or youtu.be
    m = re.search(r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-_%&=]+)", text)
    if m:
        return m.group(1)
    # try generic URL
    m2 = re.search(r"(https?://[^\s]+)", text)
    return m2.group(1) if m2 else None

# ======== Quality control commands ========
@app.on_message(filters.command("رفع الجودة", prefixes="") & filters.user(SUDO_USERS))
async def enable_hq_cmd(client, message):
    SongDownloader.enable_quality()
    await message.reply_text("تم تفعيل الجودة العالية للجميع")

@app.on_message(filters.command("قفل الجودة", prefixes="") & filters.user(SUDO_USERS))
async def disable_hq_cmd(client, message):
    SongDownloader.disable_quality()
    await message.reply_text("تم قفل الجودة")

# general locks
@app.on_message(filters.command(["قفل التنزيل", "تعطيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_download(client, message):
    await set_config("download_locked", True)
    await message.reply_text("تم قفل امر التنزيل والبحث عن الاعضاء")

@app.on_message(filters.command(["فتح التنزيل", "تفعيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_download(client, message):
    await set_config("download_locked", False)
    await message.reply_text("تم فتح التنزيل والبحث للجميع")

@app.on_message(filters.command(["قفل كيب البحث", "قفل الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_buttons(client, message):
    await set_config("buttons_locked", True)
    await message.reply_text("تم قفل ازرار البحث وسيتم التحميل تلقائيا")

@app.on_message(filters.command(["تفعيل كيب البحث", "فتح الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_buttons(client, message):
    await set_config("buttons_locked", False)
    await message.reply_text("تم تفعيل ازرار البحث والخيارات")

# smart handler
@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("عذرا التنزيل مغلق حاليا للصيانة")

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text or "")
    if not match:
        return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("اكتب اسم الاغنية او الرابط بعد الأمر")
    query = query.strip()

    is_video_request = False
    if any(k in query for k in ("فيديو", "video", "فيد")):
        is_video_request = True
        query = query.replace("فيديو", "").replace("video", "").replace("فيد", "").strip()

    # try to get url using platform helper; fallback if missing
    url = None
    try:
        # might raise AttributeError if YouTube.url not implemented
        url = await YouTube.url(message)
    except Exception:
        url = None

    if not url:
        url = extract_url_from_message(message)

    if url:
        if "youtu" not in url and "googleusercontent" not in url:
            return await message.reply_text("الرابط غير مدعوم")
        return await direct_download_handler(client, message, url, is_video_request)

    mystic = await message.reply_text("جـاري البحث .")
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        await mystic.edit_text("عذرا لم يتم العثور على نتائج")
        return

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"عذرا الاغنية اطول من {SONG_DOWNLOAD_DURATION} دقيقة")

    if await get_config("buttons_locked"):
        yt_link = f"https://www.youtube.com/watch?v={vidid}"
        await mystic.delete()
        return await direct_download_handler(client, message, yt_link, is_video_request)
    else:
        buttons = song_markup(None, vidid)
        await mystic.delete()
        return await message.reply_photo(
            thumbnail,
            caption=f"العنوان: {title}\nالمدة: {duration_min}\n\nاختار طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

# yut command
@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حاليا")

    if len(message.command) < 2:
        return await message.reply_text("ضع الرابط بجانب الأمر")

    url = message.text.split(None, 1)[1]
    is_video = False
    if any(k in message.text for k in ("فيد", "video", "فيديو")):
        is_video = True
        url = url.replace("فيديو", "").replace("فيد", "").replace("video", "").strip()

    if "youtu" in url:
        await direct_download_handler(client, message, url, is_video)
    else:
        message.text = f"تنزيل {url}"
        if is_video:
            message.text = f"ابعتلي فيديو {url}"
        await smart_song_handler(client, message)

# main download handler
async def direct_download_handler(client, message: Message, url: str, is_video_force: bool = False):
    mystic = await message.reply_text("جـاري التنزيل .")
    local_file_used = False
    local_path = None
    try:
        # details
        try:
            details = await YouTube.details(url)
            if details:
                title, _, duration_sec, thumbnail_url, vidid = details
            else:
                title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None
        except Exception:
            title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None

        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except Exception:
                thumb_path = None

        # use SongDownloader: returns (path_or_url, is_direct_flag)
        path_or_url, is_direct = await SongDownloader.download(url, is_video=is_video_force)

        if not path_or_url:
            return await mystic.edit_text("فشل التحميل من المصدر")

        if is_direct:
            await mystic.edit_text("جاري التشغيل (بث مباشر)")
        else:
            await mystic.edit_text("جاري الرفع")

        caption_text = f"NAME ↠ {message.from_user.mention}\naddress ↠ {title}"

        # Try to send directly: if is_direct -> send by URL; else send local file
        try:
            if is_video_force:
                if is_direct:
                    # sending by URL may fail with WEBPAGE_CURL_FAILED -> fallback below
                    await client.send_video(
                        message.chat.id,
                        video=path_or_url,
                        caption=caption_text,
                        duration=duration_sec,
                        thumb=thumb_path,
                        supports_streaming=True
                    )
                else:
                    await client.send_video(
                        message.chat.id,
                        video=path_or_url,
                        caption=caption_text,
                        duration=duration_sec,
                        thumb=thumb_path,
                        supports_streaming=True
                    )
            else:
                if is_direct:
                    # attempt to send audio by URL (Telegram will fetch it)
                    await client.send_audio(
                        message.chat.id,
                        audio=path_or_url,
                        caption=caption_text,
                        duration=duration_sec,
                        title=title,
                        performer="Annie Bot",
                        thumb=thumb_path
                    )
                else:
                    await client.send_audio(
                        message.chat.id,
                        audio=path_or_url,
                        caption=caption_text,
                        duration=duration_sec,
                        title=title,
                        performer="Annie Bot",
                        thumb=thumb_path
                    )

        except Exception as upload_error:
            # If sending a direct URL failed (common WEBPAGE_CURL_FAILED), fallback to download then upload local file
            errstr = str(upload_error)
            if is_direct and ("WEBPAGE_CURL_FAILED" in errstr or "WEBPAGE_MEDIA_EMPTY" in errstr or "Bad Request" in errstr):
                await mystic.edit_text("فشل الرابط المباشر، جاري التنزيل والمحاولة مرة أخرى")
                # force local download (HQ flag not needed here)
                file_path, _ = await SongDownloader.download(url, is_video=is_video_force)
                if not file_path:
                    return await mystic.edit_text("فشل في تنزيل الملف محليًا لإعادة المحاولة")

                # upload local file
                local_file_used = True
                local_path = file_path
                if is_video_force:
                    await client.send_video(message.chat.id, video=file_path, caption=caption_text, duration=duration_sec, thumb=thumb_path, supports_streaming=True)
                else:
                    await client.send_audio(message.chat.id, audio=file_path, caption=caption_text, duration=duration_sec, title=title, performer="Annie Bot", thumb=thumb_path)
            else:
                # other upload error — re-raise to be caught below
                raise

        await mystic.delete()

    except Exception as e:
        traceback.print_exc()
        try:
            await mystic.edit_text(f"حدث خطأ: {e}")
        except Exception:
            pass
    finally:
        # cleanup local file if we downloaded one
        try:
            if local_file_used and local_path and os.path.exists(local_path):
                os.remove(local_path)
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
        except Exception:
            pass

# Callbacks and other handlers remain mostly unchanged but kept robust
@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق", show_alert=True)
    try:
        stype, vidid = query.data.strip().split(None, 1)[1].split("|")
    except Exception:
        return await query.answer("بيانات خاطئة", show_alert=True)
    buttons = song_markup(None, vidid)
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق", show_alert=True)
    callback_data = query.data.strip()
    stype, vidid = callback_data.split(None, 1)[1].split("|")
    try:
        await query.answer("جاري جلب الصيغ", show_alert=True)
    except:
        pass
    try:
        formats_available, link = await YouTube.formats(vidid, True)
    except Exception:
        return await query.edit_message_text("فشل في جلب الجودات المتاحة")
    keyboard = []
    done = []
    if stype == "audio":
        for x in formats_available:
            check = x.get("format", "")
            if "audio" in check or ("audio" in x.get("format_note", "").lower()):
                if x.get("filesize") is None: continue
                form = x.get("format_note", "Audio").title()
                if form in done: continue
                done.append(form)
                sz = convert_bytes(x["filesize"])
                fom = x["format_id"]
                keyboard.append([InlineKeyboardButton(text=f"{form} ({sz})", callback_data=f"song_download {stype}|{fom}|{vidid}")])
    else:
        supported_ids = [160, 133, 134, 135, 136, 137, 298, 299, 264, 304, 266]
        for x in formats_available:
            if x.get("filesize") is None: continue
            fid_str = str(x.get("format_id", "0"))
            fid = int(fid_str) if fid_str.isdigit() else 0
            if fid not in supported_ids: continue
            sz = convert_bytes(x["filesize"])
            ap = x.get("format", "")
            ap_label = ap.split("-")[1] if "-" in ap else ap
            keyboard.append([InlineKeyboardButton(text=f"{ap_label} ({sz})", callback_data=f"song_download {stype}|{x['format_id']}|{vidid}")])

    keyboard.append([
        InlineKeyboardButton(text="رجوع", callback_data=f"song_back {stype}|{vidid}"),
        InlineKeyboardButton(text="اغلاق", callback_data="close"),
    ])
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق", show_alert=True)
    try:
        await query.answer("جـاري التنزيل .")
    except:
        pass
    try:
        stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
    except Exception:
        return await query.answer("بيانات خاطئة", show_alert=True)
    mystic = await query.edit_message_text("جـاري التنزيل .")
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    try:
        details = await YouTube.details(yturl)
        if details:
            title, _, duration_sec, thumbnail_url, _ = details
        else:
            title, duration_sec, thumbnail_url = "Unknown Track", 0, None
        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except:
                thumb_path = None
    except:
        title, duration_sec, thumb_path = "Unknown", 0, None

    # If user picked manual format we use YouTube.download to fetch that specific format
    if stype == "video":
        try:
            file_path, _ = await YouTube.download(
                yturl,
                mystic,
                songvideo=True,
                format_id=format_id,
                title=title
            )
            if not file_path or not os.path.exists(file_path):
                raise Exception("Failed to get file")
            await mystic.edit_text("جاري الرفع")
            caption_text = f"NAME ↠ {query.from_user.mention}\naddress ↠ {title}"
            await client.send_video(
                query.message.chat.id,
                video=file_path,
                caption=caption_text,
                duration=duration_sec,
                thumb=thumb_path,
                supports_streaming=True
            )
            await mystic.delete()
            try:
                os.remove(file_path)
            except Exception:
                pass
        except Exception as e:
            await mystic.edit_text(f"فشل الرفع: {e}")

    elif stype == "audio":
        try:
            file_path, _ = await YouTube.download(
                yturl,
                mystic,
                songaudio=True,
                format_id=format_id,
                title=title
            )
            if not file_path or not os.path.exists(file_path):
                raise Exception("Failed to get file")
            await mystic.edit_text("جاري الرفع")
            caption_text = f"NAME ↠ {query.from_user.mention}\naddress ↠ {title}"
            await client.send_audio(
                query.message.chat.id,
                audio=file_path,
                caption=caption_text,
                duration=duration_sec,
                title=title,
                performer="Annie Bot",
                thumb=thumb_path
            )
            await mystic.delete()
            try:
                os.remove(file_path)
            except Exception:
                pass
        except Exception as e:
            await mystic.edit_text(f"فشل الرفع: {e}")

    if thumb_path and os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
        except Exception:
            pass
