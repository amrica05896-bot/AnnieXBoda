# Authored By Certified Coders © 2026
# System: Song Plugin (Flora Style)
# Speed: Nuclear (Direct YouTube Class Usage)
# Fix: Removed 'pykeyboard' dependency (Pure Pyrogram)

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
from config import BANNED_USERS, SONG_DOWNLOAD_DURATION, SONG_DOWNLOAD_DURATION_LIMIT
from AnnieXMedia import app
from AnnieXMedia.platforms.Youtube import YouTube
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup

# دالة مساعدة لجلب مسار الكوكيز
def get_cookie_path():
    possible = ["AnnieXMedia/assets/cookies.txt", "cookies.txt", "/app/cookies.txt"]
    for p in possible:
        if os.path.exists(p): return p
    return None

# ==========================================================
# أوامـر الـبـحـث (song / video)
# ==========================================================

@app.on_message(filters.command(["song", "بحث", "اغنية", "تحميل", "video", "فيديو", "فيد"], prefixes=["/", "!", "", "."]) & filters.group & ~BANNED_USERS)
async def song_commad_group(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("**يا حب اكتب اسم الاغنية او الرابط للبحث.**")

    url = await YouTube.url(message)

    if url:
        if not await YouTube.exists(url):
            return await message.reply_text("**رابط اليوتيوب ده مش شغال او محظور.**")

        mystic = await message.reply_text("**جـارٍ الـمـعـالـجـة...**")
        
        try:
            title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(url)
        except:
            return await mystic.edit_text("**حدث خطأ اثناء جلب المعلومات.**")

        if str(duration_min) == "None":
            return await mystic.edit_text("**فشل في تحديد المدة.**")

        if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
            return await mystic.edit_text(f"**عذراً الاغنية اطول من {SONG_DOWNLOAD_DURATION} دقيقة.**")

        buttons = song_markup(None, vidid)
        await mystic.delete()

        return await message.reply_photo(
            thumbnail,
            caption=f"**الـعـنـوان:** {title}\n**الـمـدة:** {duration_min}",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    else:
        query = message.text.split(None, 1)[1]
        mystic = await message.reply_text("**جـارٍ الـبـحـث...**")

        try:
            title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
        except Exception:
            return await mystic.edit_text("**لم يتم العثور على نتائج.**")

        if str(duration_min) == "None":
            return await mystic.edit_text("**فشل في تحديد المدة.**")

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
# مـعـالـجـة الأزرار (Callbacks)
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

    try: await query.answer("جاري جلب الصيغ المتاحة...", show_alert=True)
    except: pass

    try:
        formats_available, link = await YouTube.formats(vidid, True)
    except Exception:
        return await query.edit_message_text("**فشل في جلب الجودات المتاحة.**")

    # ✅ استبدال pykeyboard بـ List عادية
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

                # إضافة زر لكل جودة في صف جديد
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"{form} ({sz})",
                        callback_data=f"song_download {stype}|{fom}|{vidid}",
                    )
                ])
    
    else:
        supported_ids = [160, 133, 134, 135, 136, 137, 298, 299, 264, 304, 266]
        
        for x in formats_available:
            check = x["format"]
            if x.get("filesize") is None: continue
            
            fid = int(x["format_id"]) if x["format_id"].isdigit() else 0
            if fid not in supported_ids: continue

            sz = convert_bytes(x["filesize"])
            ap = check.split("-")[1] if "-" in check else check
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{ap} ({sz})",
                    callback_data=f"song_download {stype}|{x['format_id']}|{vidid}",
                )
            ])

    # إضافة أزرار الرجوع والإغلاق في صف واحد
    keyboard.append([
        InlineKeyboardButton(text="رجوع", callback_data=f"song_back {stype}|{vidid}"),
        InlineKeyboardButton(text="اغلاق", callback_data="close"),
    ])

    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


# ==========================================================
# الـتـحـمـيـل الـفـعـلـي (Downloading)
# ==========================================================

@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    try: await query.answer("جاري التحميل...")
    except: pass

    stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
    mystic = await query.edit_message_text("**جـارٍ الـتـحـمـيـل مـن الـسـيـرفـر...**")

    yturl = f"https://www.youtube.com/watch?v={vidid}"
    cookie_path = get_cookie_path()

    try:
        # استخدام yt-dlp لاستخراج البيانات الأساسية
        with yt_dlp.YoutubeDL({"quiet": True, "cookiefile": cookie_path}) as ytdl:
            x = ytdl.extract_info(yturl, download=False)
    except:
        x = {"title": "Unknown Track", "duration": 0, "uploader": "Unknown"}

    title = (x.get("title", "Unknown")).title()
    title = re.sub(r"\W+", " ", title)
    duration = x.get("duration", 0)
    
    try:
        thumb_image_path = await query.message.download()
    except:
        thumb_image_path = None

    if stype == "video":
        try:
            file_path = await YouTube.download(
                yturl,
                mystic,
                songvideo=True,
                format_id=format_id,
                title=title,
            )
        except Exception as e:
            return await mystic.edit_text(f"**فشل التحميل:** {e}")

        width = 1280
        height = 720
        try:
            if query.message.photo:
                width = query.message.photo.width
                height = query.message.photo.height
        except: pass

        med = InputMediaVideo(
            media=file_path,
            duration=duration,
            width=width,
            height=height,
            thumb=thumb_image_path,
            caption=f"**{title}**\n\n**Requested By:** {query.from_user.mention}",
            supports_streaming=True,
        )

        await mystic.edit_text("**جـارٍ الـرفـع لـتـلـيـجـرام...**")
        await app.send_chat_action(chat_id=query.message.chat.id, action=enums.ChatAction.UPLOAD_VIDEO)

        try:
            await query.edit_message_media(media=med)
        except Exception as e:
            traceback.print_exc()
            return await mystic.edit_text("**فشل الرفع لتليجرام.**")

        if os.path.exists(file_path): os.remove(file_path)

    elif stype == "audio":
        try:
            filename = await YouTube.download(
                yturl,
                mystic,
                songaudio=True,
                format_id=format_id,
                title=title,
            )
        except Exception as e:
            return await mystic.edit_text(f"**فشل التحميل:** {e}")

        med = InputMediaAudio(
            media=filename,
            caption=f"**{title}**\n\n**Requested By:** {query.from_user.mention}",
            thumb=thumb_image_path,
            title=title,
            performer=x.get("uploader", "Annie Bot"),
        )

        await mystic.edit_text("**جـارٍ الـرفـع لـتـلـيـجـرام...**")
        await app.send_chat_action(chat_id=query.message.chat.id, action=enums.ChatAction.UPLOAD_AUDIO)

        try:
            await query.edit_message_media(media=med)
        except Exception:
            traceback.print_exc()
            return await mystic.edit_text("**فشل الرفع لتليجرام.**")

        if os.path.exists(filename): os.remove(filename)

    if thumb_image_path and os.path.exists(thumb_image_path):
        os.remove(thumb_image_path)
