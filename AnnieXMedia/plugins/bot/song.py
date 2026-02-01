# Authored By Certified Coders © 2026
# System: Song Plugin (Clean Text & Error Free)
# Features: Fixes Thumbnails, Empty Media, and Throttling compatibility.

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
# 1. المعالج الذكي (Regex)
# ==========================================================

# تم إزالة (video|فيديو|فيد) من بداية الأمر، ليعمل فقط مع الجمل
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
    
    # فحص الكلمات الدلالية داخل الجملة
    if "فيديو" in query or "video" in query or "فيد" in query:
        is_video_request = True
        # تنظيف كلمة فيديو من البحث
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
    # التحقق من طلب الفيديو
    if "فيد" in message.text or "video" in message.text or "فيديو" in message.text:
        is_video = True
        url = url.replace("فيديو", "").replace("فيد", "").replace("video", "").strip()
    
    # هل هو رابط يوتيوب؟
    if "youtu" in url:
        await direct_download_handler(client, message, url, is_video)
    else:
        # لو مش رابط، نحوله لأمر ذكي
        message.text = f"تنزيل {url}"
        if is_video:
             message.text = f"ابعتلي فيديو {url}"
        await smart_song_handler(client, message)


# ==========================================================
# 3. دالة التحميل والرفع (مع الإصلاحات الجذرية)
# ==========================================================

async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("**جاري التحميل...**")
    
    # رسالة الجودة
    quality_msg = "جودة قياسية (720p)"
    if message.from_user.id in SUDO_USERS:
        quality_msg = "جودة عالية (Sudo)"

    try:
        # جلب التفاصيل
        details = await YouTube.details(url)
        if details:
            title, _, duration_sec, thumbnail_url, vidid = details
        else:
            title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None

        # 🔥 إصلاح [Errno 2]: تحميل الصورة وحفظ مسارها محلياً
        # نعتمد على دالة download_thumb الموجودة في ملف Youtube.py الجديد
        thumb_path = None
        if thumbnail_url:
            try:
                # محاولة تحميل الصورة وحفظها كملف
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except:
                thumb_path = None

        # تحميل الوسائط (فيديو/صوت)
        file_path, is_direct_link = await YouTube.download(
            url,
            mystic,
            video=is_video_force,
            videoid=vidid,
            title=title
        )

        # 🔥 إصلاح [WEBPAGE_MEDIA_EMPTY]: التأكد من وجود الملف
        if not file_path or (not is_direct_link and not os.path.exists(file_path)):
            return await mystic.edit_text("**فشل التحميل من المصدر أو الملف فارغ.**")

        if is_direct_link:
             await mystic.edit_text("**جاري التشغيل (بث مباشر سريع)...**")
        else:
             await mystic.edit_text(f"**جاري الرفع...**\n{quality_msg}")
        
        # الرفع
        if is_video_force:
            await client.send_video(
                message.chat.id,
                video=file_path,
                caption=f"**{title}**\n\n{quality_msg}\n**طلب:** {message.from_user.mention}",
                duration=duration_sec,
                thumb=thumb_path, # نرسل مسار الملف وليس الرابط
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
                thumb=thumb_path # نرسل مسار الملف وليس الرابط
            )
        
        await mystic.delete()
        
        # تنظيف الملفات
        if not is_direct_link and os.path.exists(file_path):
            os.remove(file_path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        traceback.print_exc()
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
    
    try:
        # جلب المعلومات والصورة
        details = await YouTube.details(yturl)
        if details:
            title, _, duration_sec, thumbnail_url, _ = details
        else:
            title, duration_sec, thumbnail_url = "Unknown Track", 0, None
        
        # تحميل الصورة المصغرة محلياً
        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except: thumb_path = None

    except:
        title, duration_sec, thumb_path = "Unknown", 0, None

    try: user_thumb = await query.message.download()
    except: user_thumb = None
    
    # استخدام صورة المستخدم إذا وجدت، وإلا الصورة المحملة
    final_thumb = user_thumb if user_thumb else thumb_path

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
                 raise Exception("Download Failed")

            await mystic.edit_text("**جاري الرفع...**")
            
            await client.send_video(
                query.message.chat.id,
                video=file_path,
                caption=f"**{title}**\n\n**طلب:** {query.from_user.mention}",
                duration=duration_sec,
                thumb=final_thumb,
                supports_streaming=True
            )
            await mystic.delete()
        except Exception as e:
            traceback.print_exc()
            await mystic.edit_text(f"**فشل الرفع:** {e}")

        if os.path.exists(file_path): os.remove(file_path)

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
                 raise Exception("Download Failed")

            await mystic.edit_text("**جاري الرفع...**")
            
            await client.send_audio(
                query.message.chat.id,
                audio=file_path,
                caption=f"**{title}**\n\n**طلب:** {query.from_user.mention}",
                duration=duration_sec,
                title=title,
                performer="Annie Bot",
                thumb=final_thumb
            )
            await mystic.delete()
        except Exception as e:
            traceback.print_exc()
            await mystic.edit_text(f"**فشل الرفع:** {e}")

        if os.path.exists(file_path): os.remove(file_path)
    
    # تنظيف الصور
    if user_thumb and os.path.exists(user_thumb): os.remove(user_thumb)
    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
