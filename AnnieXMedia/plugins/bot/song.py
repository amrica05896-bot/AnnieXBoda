# Authored By Certified Coders © 2026
# System: Song Plugin (Smart Yut Command + Quality Control)

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
from config import BANNED_USERS, SONG_DOWNLOAD_DURATION, SONG_DOWNLOAD_DURATION_LIMIT, OWNER_ID
from AnnieXMedia import app
from AnnieXMedia.platforms import YouTube, SongDownloader
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import get_config, set_config

# تحديد المطورين (Sudo) للتحكم في الجودة
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# ==========================================================
#  1. أوامر التحكم بالجودة (للمالك فقط)
# ==========================================================

@app.on_message(filters.command(["رفع الجودة", "ارفع الجودة", "رفع الكواليتي"], prefixes="") & filters.user(SUDO_USERS))
async def enable_hq_cmd(client, message):
    SongDownloader.enable_quality()
    await message.reply_text("تم تفعيل الجودة العالية للجميع (HQ Enabled)")

@app.on_message(filters.command(["قفل الجودة", "قفل الكواليتي", "اقفل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def disable_hq_cmd(client, message):
    SongDownloader.disable_quality()
    await message.reply_text("تم قفل الجودة والعودة للوضع السريع (Standard Mode)")

# ==========================================================
#  2. أوامر القفل والفتح العامة (للمالك)
# ==========================================================

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

# ==========================================================
#  3. المعالج الذكي (هات / ابعتلي / song)
# ==========================================================

@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("عذرا التنزيل مغلق حاليا للصيانة")

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text)
    if not match: return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("اكتب اسم الاغنية او الرابط بعد الأمر")

    query = query.strip()

    # --- كشف الفيديو ---
    is_video_request = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video_request = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()

    # هل النص رابط؟
    url = await YouTube.url(message)
    if not url and ("http" in query):
        url = query

    if url:
        if "youtu" not in url and "googleusercontent" not in url:
            return await message.reply_text("الرابط غير مدعوم")
        return await direct_download_handler(client, message, url, is_video_request)

    # البحث
    mystic = await message.reply_text("جـاري البحث .")
    
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("عذرا لم يتم العثور على نتائج")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"عذرا الاغنية اطول من {SONG_DOWNLOAD_DURATION} دقيقة")

    # فحص قفل الأزرار (التحميل التلقائي)
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
#  4. أمر (يوت / yut) - المطور والمحسن
# ==========================================================

@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حاليا")

    if len(message.command) < 2:
        return await message.reply_text("اكتب اسم الاغنية او الرابط بجانب الأمر")
    
    # استخراج النص
    query = message.text.split(None, 1)[1]
    
    # --- كشف الفيديو ---
    is_video = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video = True
        # تنظيف النص
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()
    
    # --- الحالة 1: المستخدم أرسل رابطاً ---
    if "http" in query:
        url = query.split()[0]
        if "youtu" in url or "googleusercontent" in url:
            return await direct_download_handler(client, message, url, is_video)
        else:
            return await message.reply_text("رابط غير مدعوم، تأكد من رابط يوتيوب")

    # --- الحالة 2: المستخدم أرسل اسم بحث (يوت كايروكي / يوت فيديو كايروكي) ---
    mystic = await message.reply_text("جـاري البحث .")
    try:
        # نبحث عن أول نتيجة
        details = await YouTube.details(query)
        if details:
            # details ترجع: title, duration_min, duration_sec, thumb, vidid
            vidid = details[4] 
            link = f"https://www.youtube.com/watch?v={vidid}"
            
            await mystic.delete()
            # إرسال للتحميل مباشرة
            await direct_download_handler(client, message, link, is_video)
        else:
            await mystic.edit_text("لم يتم العثور على نتائج.")
    except Exception:
        await mystic.edit_text("حدث خطأ أثناء البحث.")


# ==========================================================
#  5. دالة التحميل والرفع (الرئيسية)
# ==========================================================

async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("جـاري التنزيل .")
    
    try:
        # جلب التفاصيل
        try:
            details = await YouTube.details(url)
            if details:
                title, _, duration_sec, thumbnail_url, vidid = details
            else:
                title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None
        except:
            title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None

        # تحميل الصورة المصغرة
        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except: thumb_path = None

        # استخدام SongDownloader للتحميل
        path, is_direct_link = await SongDownloader.download(url, is_video=is_video_force)

        if not path:
             return await mystic.edit_text("فشل التحميل من المصدر")

        if is_direct_link:
             await mystic.edit_text("جاري التشغيل (بث مباشر)")
        else:
             await mystic.edit_text("جاري الرفع")
        
        # الكابشن المطلوب
        caption_text = f"NAME ↠ {message.from_user.mention}\naddress ↠ {title}"

        # الرفع
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
                    title=title,
                    performer="Annie Bot",
                    thumb=thumb_path
                )
        except Exception as upload_error:
             # محاولة إعادة التحميل لو الرابط المباشر فشل
             if "WEBPAGE_CURL_FAILED" in str(upload_error) and is_direct_link:
                 await mystic.edit_text("فشل الرابط المباشر، جاري التنزيل والمحاولة مرة أخرى")
                 path, _ = await SongDownloader.download(url, is_video=is_video_force)
                 
                 if is_video_force:
                    await client.send_video(message.chat.id, video=path, caption=caption_text)
                 else:
                    await client.send_audio(message.chat.id, audio=path, caption=caption_text)

        await mystic.delete()
        
        # تنظيف الملفات
        if not is_direct_link and os.path.exists(path):
            os.remove(path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        traceback.print_exc()
        await mystic.edit_text(f"حدث خطأ: {e}")


# ==========================================================
#  6. معالجة الأزرار (Callbacks)
# ==========================================================

@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق", show_alert=True)

    stype, vidid = query.data.strip().split(None, 1)[1].split("|")
    buttons = song_markup(None, vidid)
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق", show_alert=True)

    callback_data = query.data.strip()
    stype, vidid = callback_data.split(None, 1)[1].split("|")

    try: await query.answer("جاري جلب الصيغ", show_alert=True)
    except: pass

    try:
        formats_available, link = await YouTube.formats(vidid, True)
    except Exception:
        return await query.edit_message_text("فشل في جلب الجودات المتاحة")

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
        InlineKeyboardButton(text="اغلاق", callback_data="close"),
    ])

    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق", show_alert=True)

    try: await query.answer("جـاري التنزيل .")
    except: pass

    stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
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
            try: thumb_path = await YouTube.download_thumb(thumbnail_url)
            except: thumb_path = None
    except:
        title, duration_sec, thumb_path = "Unknown", 0, None

    is_video = True if stype == "video" else False
    
    # استخدام SongDownloader للتحميل
    path, is_direct_link = await SongDownloader.download(yturl, is_video=is_video)

    if not path:
         return await mystic.edit_text("فشل التحميل من المصدر")

    if is_direct_link:
         await mystic.edit_text("جاري التشغيل (بث مباشر)")
    else:
         await mystic.edit_text("جاري الرفع")
    
    caption_text = f"NAME ↠ {query.from_user.mention}\naddress ↠ {title}"

    try:
        if is_video:
            await client.send_video(
                query.message.chat.id,
                video=path,
                caption=caption_text,
                duration=duration_sec,
                thumb=thumb_path,
                supports_streaming=True
            )
        else:
            await client.send_audio(
                query.message.chat.id,
                audio=path,
                caption=caption_text,
                duration=duration_sec,
                title=title,
                performer="Annie Bot",
                thumb=thumb_path
            )
        await mystic.delete()
        if not is_direct_link and os.path.exists(path): os.remove(path)
        
    except Exception as e:
        await mystic.edit_text(f"فشل الرفع: {e}")
    
    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
