# Authored By Certified Coders © 2026
# System: Song Plugin (Smart Warehouse + Limit Control) - No Emoji Edition

import os
import re
import asyncio
import traceback
from pyrogram import enums, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaVideo,
    Message,
)

# استيرادات AnnieXMedia
from config import BANNED_USERS, SONG_DOWNLOAD_DURATION, SONG_DOWNLOAD_DURATION_LIMIT, OWNER_ID, LOGGER_ID
from AnnieXMedia import app
from AnnieXMedia.platforms import YouTube, SongDownloader
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import get_config, set_config, get_cached_file, cache_file

# تحديد المطورين
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# ==========================================================
#  🧹 دالة تنظيف العناوين
# ==========================================================
def clean_title(title: str) -> str:
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    bad_words = [
        "Official Video", "Official Audio", "Lyrics", "Video", 
        "Music Video", "HD", "HQ", "4K", "ft.", "feat.", 
        "Live", "Performance", "with Lyrics"
    ]
    for word in bad_words:
        title = title.replace(word, "")
        title = title.replace(word.lower(), "")
        title = title.replace(word.upper(), "")
    return title.strip()

# ==========================================================
#  1. أوامر التحكم في حد البلاي ليست (Limit Control)
# ==========================================================

@app.on_message(filters.command(["فتح الحد", "فتح الليميت"], prefixes="") & filters.user(SUDO_USERS))
async def open_limit_cmd(client, message):
    SongDownloader.open_limit()
    await message.reply_text("تم فتح الحد للبلاي ليست.")

@app.on_message(filters.command(["قفل ليميت", "قفل الحد"], prefixes="") & filters.user(SUDO_USERS))
async def lock_limit_cmd(client, message):
    SongDownloader.reset_limit()
    await message.reply_text("تم تعيين الحد الافتراضي (10 ملفات).")

@app.on_message(filters.command(["تعيين ليميت", "تعيين حد"], prefixes="") & filters.user(SUDO_USERS))
async def set_limit_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("يرجى كتابة الرقم بجانب الأمر.")
    try:
        limit = int(message.command[2])
        SongDownloader.set_limit(limit)
        await message.reply_text(f"تم تعيين حد البلاي ليست لـ {limit} ملف.")
    except:
        await message.reply_text("يرجى كتابة رقم صحيح.")

# ==========================================================
#  2. أوامر التحكم بالجودة
# ==========================================================

@app.on_message(filters.command(["رفع الجودة", "ارفع الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def enable_hq_cmd(client, message):
    SongDownloader.enable_quality()
    await message.reply_text("تم تفعيل الجودة العالية.")

@app.on_message(filters.command(["قفل الجودة", "اقفل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def disable_hq_cmd(client, message):
    SongDownloader.disable_quality()
    await message.reply_text("تم تعطيل الجودة العالية.")

# ==========================================================
#  3. أوامر القفل والفتح العامة
# ==========================================================

@app.on_message(filters.command(["قفل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_download(client, message):
    await set_config("download_locked", True)
    await message.reply_text("تم تعطيل التنزيل والبحث.")

@app.on_message(filters.command(["فتح التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_download(client, message):
    await set_config("download_locked", False)
    await message.reply_text("تم تفعيل التنزيل والبحث.")

@app.on_message(filters.command(["قفل كيب البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_buttons(client, message):
    await set_config("buttons_locked", True)
    await message.reply_text("تم تعطيل أزرار البحث.")

@app.on_message(filters.command(["تفعيل كيب البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_buttons(client, message):
    await set_config("buttons_locked", False)
    await message.reply_text("تم تفعيل أزرار البحث.")

# ==========================================================
#  4. المعالج الذكي (هات / ابعتلي / song)
# ==========================================================

@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("عذراً، التنزيل متوقف حالياً.")

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text)
    if not match: return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("يرجى كتابة اسم الأغنية أو الرابط.")

    query = query.strip()
    is_video_request = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video_request = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()

    url = await YouTube.url(message)
    if not url and ("http" in query):
        url = query

    if url:
        if "youtu" not in url and "googleusercontent" not in url:
            return await message.reply_text("الرابط غير مدعوم.")
        return await direct_download_handler(client, message, url, is_video_request)

    mystic = await message.reply_text("جـاري البحث...")
    
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("لم يتم العثور على نتائج.")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"عذراً، مدة المقطع تتجاوز {SONG_DOWNLOAD_DURATION} دقيقة.")

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

# ==========================================================
#  5. أمر (يوت / yut)
# ==========================================================

@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    if len(message.command) < 2:
        return await message.reply_text("اكتب اسم الأغنية أو الرابط.")
    
    query = message.text.split(None, 1)[1]
    is_video = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()
    
    if "http" in query:
        url = query.split()[0]
        if "youtu" in url or "googleusercontent" in url:
            return await direct_download_handler(client, message, url, is_video)
        else:
            return await message.reply_text("رابط غير مدعوم.")

    mystic = await message.reply_text("جـاري البحث...")
    try:
        details = await YouTube.details(query)
        if details:
            vidid = details[4] 
            link = f"https://www.youtube.com/watch?v={vidid}"
            await mystic.delete()
            await direct_download_handler(client, message, link, is_video)
        else:
            await mystic.edit_text("لم يتم العثور على نتائج.")
    except Exception:
        await mystic.edit_text("حدث خطأ أثناء البحث.")

# ==========================================================
#  6. دالة التحميل والرفع (المستودع الذكي)
# ==========================================================

async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("جـاري المعالجة...")
    
    try:
        try:
            details = await YouTube.details(url)
            if details:
                title, _, duration_sec, thumbnail_url, vidid = details
            else:
                title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None
        except:
            title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None

        clean_full_title = clean_title(title)
        if "-" in clean_full_title:
            parts = clean_full_title.split("-", 1)
            artist_name = parts[0].strip()
            song_title = parts[1].strip()
        else:
            artist_name = clean_full_title 
            song_title = clean_full_title

        if not artist_name or artist_name.lower() == "annie bot":
             artist_name = "Unknown Artist"

        caption_text = (
            f"الطـلب بواسطـة: {message.from_user.mention}\n"
            f"عنـوان المقطـع: {song_title}"
        )

        cache_key = f"{vidid}|{'video' if is_video_force else 'audio'}"
        cached_file_id = await get_cached_file(cache_key)

        if cached_file_id:
            await mystic.edit_text("جـاري الرفع.")
            try:
                if is_video_force:
                    await client.send_video(
                        message.chat.id,
                        video=cached_file_id,
                        caption=caption_text,
                        reply_to_message_id=message.id
                    )
                else:
                    await client.send_audio(
                        message.chat.id,
                        audio=cached_file_id,
                        caption=caption_text,
                        reply_to_message_id=message.id
                    )
                await mystic.delete()
                return 
            except Exception: pass

        # 🛑 الكشف عن البلاي ليست وتعديل الرسالة 🛑
        if "list=" in url:
            await mystic.edit_text("تـم الـكـشـف عـن بلاي ليست.")
            await asyncio.sleep(0.5) 
            await mystic.edit_text("جـاري التنزيل.")
        else:
            await mystic.edit_text("جـاري التنزيل.")

        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except: thumb_path = None

        path, is_direct_link = await SongDownloader.download(url, is_video=is_video_force)

        if not path:
             return await mystic.edit_text("فشل التحميل من المصدر.")

        await mystic.edit_text("جـاري الرفع.")
        
        try:
            if is_video_force:
                log_msg = await client.send_video(
                    LOGGER_ID,
                    video=path,
                    caption=f"Video Warehouse\nID: `{vidid}`\nTitle: {clean_full_title}",
                    duration=duration_sec,
                    thumb=thumb_path,
                    supports_streaming=True
                )
                file_id_to_cache = log_msg.video.file_id
            else:
                log_msg = await client.send_audio(
                    LOGGER_ID,
                    audio=path,
                    caption=f"Audio Warehouse\nID: `{vidid}`\nTitle: {clean_full_title}",
                    duration=duration_sec,
                    title=song_title,
                    performer=artist_name,
                    thumb=thumb_path
                )
                file_id_to_cache = log_msg.audio.file_id
            
            await cache_file(cache_key, file_id_to_cache)
        except Exception: pass

        await mystic.edit_text("جـاري الإرسال...")
        try:
            if is_video_force:
                await client.send_video(
                    message.chat.id,
                    video=path, 
                    caption=caption_text,
                    duration=duration_sec,
                    thumb=thumb_path,
                    supports_streaming=True
                )
            else:
                await client.send_audio(
                    message.chat.id,
                    audio=path,
                    caption=caption_text,
                    duration=duration_sec,
                    title=song_title,
                    performer=artist_name,
                    thumb=thumb_path
                )
        except Exception: pass

        await mystic.delete()
        if not is_direct_link and os.path.exists(path):
            os.remove(path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        traceback.print_exc()
        await mystic.edit_text(f"حدث خطأ: {e}")

# ==========================================================
#  7. معالجة الأزرار (Callbacks)
# ==========================================================

@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)

    stype, vidid = query.data.strip().split(None, 1)[1].split("|")
    buttons = song_markup(None, vidid)
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)

    callback_data = query.data.strip()
    stype, vidid = callback_data.split(None, 1)[1].split("|")

    try: await query.answer("جاري جلب الصيغ...", show_alert=True)
    except: pass

    try:
        formats_available, link = await YouTube.formats(vidid, True)
    except Exception:
        return await query.edit_message_text("فشل في جلب الجودات المتاحة.")

    keyboard = []
    done = []

    if stype == "audio":
        for x in formats_available:
            check = x["format"]
            if "audio" in check:
                if x.get("filesize") is None: continue
                form = x.get("format_note", "Audio").title()
                if form not in done: done.append(form)
                else: continue
                sz = convert_bytes(x["filesize"])
                fom = x["format_id"]
                keyboard.append([InlineKeyboardButton(text=f"{form} ({sz})", callback_data=f"song_download {stype}|{fom}|{vidid}")])
    else:
        supported_ids = [160, 133, 134, 135, 136, 137, 298, 299, 264, 304, 266]
        for x in formats_available:
            if x.get("filesize") is None: continue
            fid = int(x["format_id"]) if x["format_id"].isdigit() else 0
            if fid not in supported_ids: continue
            sz = convert_bytes(x["filesize"])
            ap = x["format"].split("-")[1] if "-" in x["format"] else x["format"]
            keyboard.append([InlineKeyboardButton(text=f"{ap} ({sz})", callback_data=f"song_download {stype}|{x['format_id']}|{vidid}")])

    keyboard.append([
        InlineKeyboardButton(text="رجوع", callback_data=f"song_back {stype}|{vidid}"),
        InlineKeyboardButton(text="إغلاق", callback_data="close"),
    ])

    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)

    try: await query.answer("جـاري التنزيل...", show_alert=True)
    except: pass

    stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
    
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    is_video = True if stype == "video" else False
    
    # نستخدم نفس المعالج لتوحيد الرسائل
    await direct_download_handler(client, query.message, yturl, is_video_force=is_video)
