# Authored By Certified Coders © 2026
# System: Song Plugin (Clean Text & Custom Triggers)
# Features: No Emojis, Removed standalone /video command, Direct Stream

import os
import re
import traceback
import yt_dlp
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
from AnnieXMedia.platforms.Youtube import YouTube
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import get_config, set_config

# تحديد المطورين (Sudo)
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# دالة مساعدة لجلب مسار الكوكيز
def get_cookie_path():
    possible = ["AnnieXMedia/assets/cookies.txt", "cookies.txt", "/app/cookies.txt"]
    for p in possible:
        if os.path.exists(p): return p
    return None

# ==========================================================
#  أوامر التحكم (للمالك فقط)
# ==========================================================

@app.on_message(filters.command(["قفل التنزيل", "تعطيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_download(client, message):
    await set_config("download_locked", True)
    await message.reply_text("**تم قفل امر التنزيل والبحث عن الاعضاء.**")

@app.on_message(filters.command(["فتح التنزيل", "تفعيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_download(client, message):
    await set_config("download_locked", False)
    await message.reply_text("**تم فتح التنزيل والبحث للجميع.**")

@app.on_message(filters.command(["قفل كيب البحث", "قفل الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_buttons(client, message):
    await set_config("buttons_locked", True)
    await message.reply_text("**تم قفل ازرار البحث (سيتم التحميل تلقائيا).**")

@app.on_message(filters.command(["تفعيل كيب البحث", "فتح الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_buttons(client, message):
    await set_config("buttons_locked", False)
    await message.reply_text("**تم تفعيل ازرار البحث والخيارات.**")

# ==========================================================
# 1. المعالج الذكي (Regex) - ابعتلي / هات / تنزيل
# ==========================================================

# ⚠️ تم التعديل: إزالة (video|فيديو|فيد) من القائمة ليعمل فقط مع الجمل الكاملة
@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    # فحص القفل
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("**عذرا التنزيل مغلق حاليا للصيانة.**")

    # استخراج النص
    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text)
    if not match: return

    command = match.group(1).lower()
    query = match.group(2)

    # التحقق من وجود نص للبحث
    if not query or query.strip() == "":
        return await message.reply_text("**يا حب اكتب اسم الاغنية او الرابط بعد الأمر.**")

    query = query.strip()

    # تحديد نوع الطلب (هل يريد فيديو؟)
    is_video_request = False
    
    # التحقق مما إذا كان المستخدم كتب "فيديو" داخل الجملة (مثال: ابعتلي فيديو كذا)
    if "فيديو" in query or "video" in query or "فيد" in query:
        is_video_request = True
        # تنظيف كلمة فيديو من البحث عشان النتائج تكون دقيقة
        query = query.replace("فيديو", "").replace("video", "").replace("فيد", "").strip()

    # هل النص رابط؟
    url = await YouTube.url(message) 
    
    if url:
        if "youtu" not in url:
            return await message.reply_text("**الرابط ده مش شغال.**")
        return await direct_download_handler(client, message, url, is_video_request)

    # البحث
    mystic = await message.reply_text("**جاري البحث...**")
    
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("**عذرا لم يتم العثور على نتائج.**")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"**عذرا الاغنية اطول من {SONG_DOWNLOAD_DURATION} دقيقة.**")

    # فحص قفل الأزرار
    if await get_config("buttons_locked"):
        yt_link = f"https://www.youtube.com/watch?v={vidid}"
        await mystic.delete()
        return await direct_download_handler(client, message, yt_link, is_video_request)
    else:
        buttons = song_markup(None, vidid)
        await mystic.delete()
        return await message.reply_photo(
            thumbnail,
            caption=f"**العنوان:** {title}\n**المدة:** {duration_min}\n\n**اختار طريقة التحميل:**",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ==========================================================
# 2. أمر التحميل المباشر (يوت)
# ==========================================================

@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("**التنزيل مغلق حاليا.**")

    if len(message.command) < 2:
        return await message.reply_text("**حط الرابط جنب الأمر يا حب.**")
    
    # استخراج الرابط أو النص
    url = message.text.split(None, 1)[1]
    
    is_video = False
    # التحقق من طلب الفيديو (يوت فيديو / يوت فيد)
    if "فيد" in message.text or "video" in message.text or "فيديو" in message.text:
        is_video = True
        # تنظيف الكلمات الزائدة من الرابط أو اسم الأغنية
        url = url.replace("فيديو", "").replace("فيد", "").replace("video", "").strip()
    
    # هل هو رابط يوتيوب؟
    if "youtu" in url:
        await direct_download_handler(client, message, url, is_video)
    else:
        # لو مش رابط (اسم أغنية)، نحوله للبحث الذكي
        message.text = f"تنزيل {url}"
        if is_video:
             message.text = f"ابعتلي فيديو {url}"
        await smart_song_handler(client, message)


# ==========================================================
# 3. دالة التحميل والرفع
# ==========================================================

async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("**جاري التحميل...**")
    
    # رسالة الجودة
    quality_msg = "جودة قياسية (720p)"
    if message.from_user.id in SUDO_USERS:
        quality_msg = "جودة عالية (Sudo)"

    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(url)
        title = title.title()
        
        # استدعاء دالة التحميل من Youtube.py
        file_path, is_direct_link = await YouTube.download(
            url,
            mystic,
            video=is_video_force,
            videoid=vidid,
            title=title
        )

        if is_direct_link:
             await mystic.edit_text("**جاري التشغيل (بث مباشر سريع)...**")
        else:
             await mystic.edit_text(f"**جاري الرفع...**\n{quality_msg}")
        
        if is_video_force:
            await client.send_video(
                message.chat.id,
                video=file_path,
                caption=f"**{title}**\n\n{quality_msg}\n**طلب:** {message.from_user.mention}",
                duration=duration_sec,
                thumb=thumbnail,
                supports_streaming=True
            )
        else:
            await client.send_audio(
                message.chat.id,
                audio=file_path,
                caption=f"**{title}**\n\n{quality_msg}\n**طلب:** {message.from_user.mention}",
                duration=duration_sec,
                title=title,
                performer="Annie Bot",
                thumb=thumbnail
            )
        
        await mystic.delete()
        
        if not is_direct_link and os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        await mystic.edit_text(f"**خطأ:** {e}")


# ==========================================================
# 4. أمر رفع الجودة (للمطورين)
# ==========================================================

@app.on_message(filters.command(["رفع جودة"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def quality_upgrade(client, message):
    if not message.reply_to_message:
        return await message.reply_text("**رد على رابط عشان ارفع جودته.**")
    
    reply = message.reply_to_message
    url = None
    
    if reply.text:
        match = re.search(r'(https?://(?:www\.)?youtu(?:\.be|be\.com)/\S+)', reply.text)
        if match: url = match.group(0)
    elif reply.caption:
        match = re.search(r'(https?://(?:www\.)?youtu(?:\.be|be\.com)/\S+)', reply.caption)
        if match: url = match.group(0)
        
    if not url:
        return await message.reply_text("**مش لاقي رابط يوتيوب في الرسالة دي.**")
    
    await direct_download_handler(client, message, url, is_video_force=True)


# ==========================================================
# 5. معالجة الأزرار (Callbacks)
# ==========================================================

@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق.", show_alert=True)

    stype, vidid = query.data.strip().split(None, 1)[1].split("|")
    buttons = song_markup(None, vidid)
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق.", show_alert=True)

    callback_data = query.data.strip()
    stype, vidid = callback_data.split(None, 1)[1].split("|")

    try: await query.answer("جاري جلب الصيغ...", show_alert=True)
    except: pass

    try:
        formats_available, link = await YouTube.formats(vidid, True)
    except Exception:
        return await query.edit_message_text("**فشل في جلب الجودات المتاحة.**")

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
        return await query.answer("التنزيل مغلق.", show_alert=True)

    try: await query.answer("جاري التحميل...")
    except: pass

    stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
    mystic = await query.edit_message_text("**جاري التحميل...**")

    yturl = f"https://www.youtube.com/watch?v={vidid}"
    cookie_path = get_cookie_path()

    try:
        title, duration_min, duration_sec, thumbnail, _ = await YouTube.details(vidid)
        title = title.title()
    except:
        title = "Unknown Track"
        duration_sec = 0
        thumbnail = None

    try: thumb_image_path = await query.message.download()
    except: thumb_image_path = None

    if stype == "video":
        try:
            file_path, is_direct = await YouTube.download(
                yturl,
                mystic,
                songvideo=True,
                format_id=format_id,
                title=title
            )
        except Exception as e:
            return await mystic.edit_text(f"**فشل التحميل:** {e}")

        await mystic.edit_text("**جاري الرفع...**")
        
        try:
            await client.send_video(
                query.message.chat.id,
                video=file_path,
                caption=f"**{title}**\n\n**طلب:** {query.from_user.mention}",
                duration=duration_sec,
                thumb=thumb_image_path or thumbnail,
                supports_streaming=True
            )
            await mystic.delete()
        except Exception as e:
            traceback.print_exc()
            return await mystic.edit_text(f"**فشل الرفع:** {e}")

        if not is_direct and os.path.exists(file_path): os.remove(file_path)

    elif stype == "audio":
        try:
            file_path, is_direct = await YouTube.download(
                yturl,
                mystic,
                songaudio=True,
                format_id=format_id,
                title=title
            )
        except Exception as e:
            return await mystic.edit_text(f"**فشل التحميل:** {e}")

        await mystic.edit_text("**جاري الرفع...**")
        
        try:
            await client.send_audio(
                query.message.chat.id,
                audio=file_path,
                caption=f"**{title}**\n\n**طلب:** {query.from_user.mention}",
                duration=duration_sec,
                title=title,
                performer="Annie Bot",
                thumb=thumb_image_path or thumbnail
            )
            await mystic.delete()
        except Exception:
            traceback.print_exc()
            return await mystic.edit_text("**فشل الرفع.**")

        if not is_direct and os.path.exists(file_path): os.remove(file_path)
    
    if thumb_image_path and os.path.exists(thumb_image_path): os.remove(thumb_image_path)
