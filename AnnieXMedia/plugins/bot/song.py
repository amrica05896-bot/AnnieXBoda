# Authored By Certified Coders © 2026
# System: Song Plugin (Ultimate Edition)
# Features: Regex Commands, Auto-Quality (Sudo vs User), Direct Link (Yut)
# Speed: Nuclear (Direct YouTube Class Usage)

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

# تحديد المطورين (Sudo)
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# دالة مساعدة لجلب مسار الكوكيز
def get_cookie_path():
    possible = ["AnnieXMedia/assets/cookies.txt", "cookies.txt", "/app/cookies.txt"]
    for p in possible:
        if os.path.exists(p): return p
    return None

# ==========================================================
# 1. الـمـعـالـج الـذكـي (Regex) - ابعتلي / هات / تنزيل
# ==========================================================

@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song|video|فيديو|فيد)(?:\s+(.+))?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    # استخراج النص
    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song|video|فيديو|فيد)(?:\s+(.+))?$", message.text)
    if not match: return

    command = match.group(1).lower()
    query = match.group(2)

    # التحقق من وجود نص للبحث
    if not query:
        return await message.reply_text("**يا حب اكتب اسم الاغنية او الرابط بعد الأمر.**")

    # هل الطلب فيديو؟
    is_video = False
    if command in ["video", "فيديو", "فيد"]:
        is_video = True
    # لو المستخدم كتب "ابعتلي فيديو كذا"
    if query.startswith("فيديو ") or query.startswith("فيد "):
        is_video = True
        query = query.replace("فيديو ", "").replace("فيد ", "")

    url = await YouTube.url(message) # هل الرسالة تحتوي على رابط؟

    # --- الحالة 1: رابط مباشر (يتم التعامل معه بذكاء) ---
    if url:
        if not await YouTube.exists(url):
            return await message.reply_text("**الرابط ده مش شغال.**")

        # تحويل لـ "يوت" تلقائياً للروابط المباشرة لتطبيق الجودة
        return await yut_direct_handler(client, message, url, is_video)

    # --- الحالة 2: بحث عن اسم (إظهار أزرار) ---
    mystic = await message.reply_text("**جـارٍ الـبـحـث...**")
    
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("**لم يتم العثور على نتائج.**")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"**عذراً الاغنية اطول من {SONG_DOWNLOAD_DURATION} دقيقة.**")

    buttons = song_markup(None, vidid)
    await mystic.delete()

    return await message.reply_photo(
        thumbnail,
        caption=f"**الـعـنـوان:** {title}\n**الـمـدة:** {duration_min}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ==========================================================
# 2. أمـر الـتـحـمـيـل الـمـبـاشـر (يوت) + رفـع الـجـودة
# ==========================================================

async def yut_direct_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("**جـارٍ الـتـحـمـيـل بـأفـضـل جـودة مـنـاسـبـة...**")
    
    # تحديد الجودة بناءً على المستخدم
    if message.from_user.id in SUDO_USERS:
        # للمالك: أعلى جودة ممكنة
        video_fmt = "bestvideo+bestaudio/best"
        audio_fmt = "bestaudio/best"
        quality_msg = "🌟 **جودة عالية (Sudo)**"
    else:
        # للمستخدم: جودة متوسطة (توفير)
        video_fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        audio_fmt = "bestaudio[abr<=128]/bestaudio"
        quality_msg = "✅ **جودة قياسية (720p)**"

    try:
        # استخراج المعلومات
        with yt_dlp.YoutubeDL({"quiet": True, "cookiefile": get_cookie_path()}) as ytdl:
            x = ytdl.extract_info(url, download=False)
        
        title = x.get("title", "Unknown").title()
        title = re.sub(r"\W+", " ", title)
        duration = x.get("duration", 0)
        
        # تحديد المسار
        path = f"downloads/{x['id']}"

        # التحميل الفعلي
        if is_video_force:
            opts = {
                "format": video_fmt,
                "outtmpl": f"{path}.%(ext)s",
                "cookiefile": get_cookie_path(),
                "geo_bypass": True,
                "quiet": True,
            }
            ext = "mp4"
        else:
            opts = {
                "format": audio_fmt,
                "outtmpl": f"{path}.%(ext)s",
                "cookiefile": get_cookie_path(),
                "geo_bypass": True,
                "quiet": True,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}] if not is_video_force else []
            }
            ext = "mp3"

        # تنفيذ التحميل
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        
        # البحث عن الملف الناتج
        final_path = ""
        for f in os.listdir("downloads"):
            if f.startswith(x['id']):
                final_path = os.path.join("downloads", f)
                break
        
        if not final_path or not os.path.exists(final_path):
            return await mystic.edit_text("**فشل التحميل من المصدر.**")

        # الرفع
        await mystic.edit_text(f"**جـارٍ الـرفـع...**\n{quality_msg}")
        
        if is_video_force:
            await client.send_video(
                message.chat.id,
                video=final_path,
                caption=f"**{title}**\n\n{quality_msg}",
                duration=duration,
                supports_streaming=True
            )
        else:
            await client.send_audio(
                message.chat.id,
                audio=final_path,
                caption=f"**{title}**\n\n{quality_msg}",
                duration=duration,
                title=title,
                performer=x.get("uploader", "Bot")
            )
        
        await mystic.delete()
        if os.path.exists(final_path): os.remove(final_path)

    except Exception as e:
        await mystic.edit_text(f"**خطأ:** {e}")


@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("**حط الرابط جنب الأمر يا حب.**")
    
    url = message.text.split(None, 1)[1]
    # فحص لو مطلوب فيديو
    is_video = "video" in message.text or "فيد" in message.text
    
    if "youtu" in url:
        await yut_direct_handler(client, message, url, is_video)
    else:
        await message.reply_text("**ده مش رابط يوتيوب!**")


@app.on_message(filters.command(["رفع جودة"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def quality_upgrade(client, message):
    if not message.reply_to_message:
        return await message.reply_text("**رد على رابط عشان ارفع جودته.**")
    
    reply = message.reply_to_message
    url = None
    
    # محاولة استخراج الرابط من الرد
    if reply.text:
        match = re.search(r'(https?://(?:www\.)?youtu(?:\.be|be\.com)/\S+)', reply.text)
        if match: url = match.group(0)
    elif reply.caption:
        match = re.search(r'(https?://(?:www\.)?youtu(?:\.be|be\.com)/\S+)', reply.caption)
        if match: url = match.group(0)
        
    if not url:
        return await message.reply_text("**مش لاقي رابط يوتيوب في الرسالة دي.**")
        
    # إعادة التحميل بجودة المطور (العالية)
    await yut_direct_handler(client, message, url, is_video_force=True)


# ==========================================================
# 3. مـعـالـجـة الأزرار (Callbacks)
# ==========================================================

@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    stype, vidid = query.data.strip().split(None, 1)[1].split("|")
    buttons = song_markup(None, vidid)
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
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
    try: await query.answer("جاري التحميل...")
    except: pass

    stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
    mystic = await query.edit_message_text("**جـارٍ الـتـحـمـيـل مـن الـسـيـرفـر...**")

    yturl = f"https://www.youtube.com/watch?v={vidid}"
    cookie_path = get_cookie_path()

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "cookiefile": cookie_path}) as ytdl:
            x = ytdl.extract_info(yturl, download=False)
    except:
        x = {"title": "Unknown Track", "duration": 0}

    title = x.get("title", "Unknown").title()
    title = re.sub(r"\W+", " ", title)
    
    try: thumb_image_path = await query.message.download()
    except: thumb_image_path = None

    if stype == "video":
        try:
            file_path = await YouTube.download(
                yturl, mystic, songvideo=True, format_id=format_id, title=title
            )
        except Exception as e:
            return await mystic.edit_text(f"**فشل التحميل:** {e}")

        med = InputMediaVideo(
            media=file_path, duration=x.get("duration", 0),
            thumb=thumb_image_path, caption=f"**{title}**\n\n**Requested By:** {query.from_user.mention}",
            supports_streaming=True
        )
        await mystic.edit_text("**جـارٍ الـرفـع...**")
        
        try: await query.edit_message_media(media=med)
        except Exception: 
            await mystic.delete()
            await client.send_video(query.message.chat.id, video=file_path, caption=f"**{title}**")
        
        if os.path.exists(file_path): os.remove(file_path)

    elif stype == "audio":
        try:
            filename = await YouTube.download(
                yturl, mystic, songaudio=True, format_id=format_id, title=title
            )
        except Exception as e:
            return await mystic.edit_text(f"**فشل التحميل:** {e}")

        med = InputMediaAudio(
            media=filename, caption=f"**{title}**\n\n**Requested By:** {query.from_user.mention}",
            thumb=thumb_image_path, title=title, performer=x.get("uploader", "Bot")
        )
        await mystic.edit_text("**جـارٍ الـرفـع...**")
        
        try: await query.edit_message_media(media=med)
        except Exception:
            await mystic.delete()
            await client.send_audio(query.message.chat.id, audio=filename, caption=f"**{title}**")

        if os.path.exists(filename): os.remove(filename)
    
    if thumb_image_path and os.path.exists(thumb_image_path): os.remove(thumb_image_path)
