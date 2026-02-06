# Authored By Certified Coders © 2026
# System: Song Plugin (List + Interactive Play Button) - No Emoji Edition

import os
import re
import asyncio
import traceback
from pyrogram import enums, filters, types
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# استيرادات AnnieXMedia
from config import BANNED_USERS, SONG_DOWNLOAD_DURATION, SONG_DOWNLOAD_DURATION_LIMIT, OWNER_ID, LOGGER_ID
from AnnieXMedia import app
from AnnieXMedia.platforms import YouTube, SongDownloader
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import get_config, set_config, get_cached_file, cache_file

# استيراد دالة التشغيل
from AnnieXMedia.utils.stream.stream import stream

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
#  4. أمر (ليست / List)
# ==========================================================
@app.on_message(filters.command(["ليست", "list"], prefixes=["", "/"]) & filters.group & ~BANNED_USERS)
async def list_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    # الحالة 1: كتب "ليست" فقط
    if len(message.text.split()) == 1:
        return await message.reply_text(
            "ارسل اسـم الفنان الان .",
            reply_markup=types.ForceReply(selective=True)
        )

    # الحالة 2: كتب "ليست عمرو دياب"
    query = message.text.split(None, 1)[1]
    await process_list_search(client, message, query)

# معالج الرد على رسالة "ارسل اسم الفنان"
@app.on_message(filters.reply & filters.group & ~BANNED_USERS)
async def list_reply_handler(client, message):
    reply = message.reply_to_message
    if reply and reply.from_user.is_self and reply.text == "ارسل اسـم الفنان الان .":
        await process_list_search(client, message, message.text)

async def process_list_search(client, message, query):
    mystic = await message.reply_text("جـاري البحث...")
    try:
        results = await YouTube.search(query, limit=10)
        if not results:
            return await mystic.edit_text("لم يتم العثور على نتائج.")

        buttons = []
        for vid in results:
            title = vid["title"][:40] 
            vidid = vid["vidid"]
            # عند الضغط هيحمل صوت
            buttons.append([InlineKeyboardButton(text=title, callback_data=f"song_download audio|{vidid}")])

        buttons.append([InlineKeyboardButton(text="الـمـالك", url="https://t.me/S_G0C7")])
        buttons.append([InlineKeyboardButton(text="إغلاق", callback_data="close")])

        await mystic.delete()
        await message.reply_text(
            f"نتائج البحث عن: {query}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        await mystic.edit_text("حدث خطأ أثناء البحث.")

# ==========================================================
#  5. معالج الفيديو (Video Handler)
# ==========================================================
@app.on_message(filters.regex(r"^/?(فيديو|video|vid|فيد|/video|يوت فيديو|هات فيديو|ابعتلي فيديو)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def video_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    match = re.match(r"^/?(فيديو|video|vid|فيد|/video|يوت فيديو|هات فيديو|ابعتلي فيديو)(\s+.+)?$", message.text)
    if not match: return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("يرجى كتابة اسم الفيديو أو الرابط.")

    await process_song_request(client, message, query.strip(), is_video_force=True)

# ==========================================================
#  6. معالج الصوت (Audio Handler)
# ==========================================================
@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song|/song|يوت|yut)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def audio_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    if re.match(r"^/?(فيديو|video|/video)", message.text): return

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song|/song|يوت|yut)(\s+.+)?$", message.text)
    if not match: return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("يرجى كتابة اسم الأغنية أو الرابط.")

    await process_song_request(client, message, query.strip(), is_video_force=False)

# ==========================================================
#  7. الدالة الموحدة للمعالجة
# ==========================================================
async def process_song_request(client, message, query, is_video_force):
    url = await YouTube.url(message)
    if not url and ("http" in query): url = query

    if url:
        return await direct_download_handler(client, message, url, is_video_force)

    mystic = await message.reply_text("جـاري البحث...")
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("لم يتم العثور على نتائج.")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"عذراً، مدة المقطع تتجاوز {SONG_DOWNLOAD_DURATION} دقيقة.")

    if await get_config("buttons_locked") or is_video_force:
        yt_link = f"https://www.youtube.com/watch?v={vidid}"
        await mystic.delete()
        return await direct_download_handler(client, message, yt_link, is_video_force)
    else:
        buttons = song_markup(None, vidid)
        await mystic.delete()
        return await message.reply_photo(
            thumbnail,
            caption=f"العنوان: {title}\nالمدة: {duration_min}\n\nاختار طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

# ==========================================================
#  8. دالة التحميل المباشر (الزرار الذكي)
# ==========================================================
async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("جـاري المعالجة...")
    try:
        try:
            details = await YouTube.track(url)
            vidid = details.get("vidid", "")
            title = details.get("title", "Unknown")
        except:
            title, vidid = "Media", ""

        clean_full_title = clean_title(title)
        
        # 🛑 هنا التغيير: زرار التشغيل فقط في البداية 🛑
        buttons = [
            [InlineKeyboardButton(text="- تشغيل الان.", callback_data=f"force_play {vidid}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        cache_key = f"{vidid}|{'video' if is_video_force else 'audio'}"
        cached_file_id = await get_cached_file(cache_key)

        if cached_file_id:
            await mystic.edit_text("جـاري الرفع.")
            if is_video_force:
                await client.send_video(
                    message.chat.id, video=cached_file_id, caption=clean_full_title,
                    reply_markup=reply_markup, reply_to_message_id=message.id
                )
            else:
                await client.send_audio(
                    message.chat.id, audio=cached_file_id, caption=clean_full_title,
                    reply_markup=reply_markup, reply_to_message_id=message.id
                )
            await mystic.delete()
            return

        if "list=" in url:
            await mystic.edit_text("تـم الـكـشـف عـن بلاي ليست.")
            await asyncio.sleep(0.5)
        
        await mystic.edit_text("جـاري التنزيل.")
        path, _ = await SongDownloader.download(url, is_video=is_video_force)

        if not path:
             return await mystic.edit_text("فشل التحميل.")

        await mystic.edit_text("جـاري الرفع.")
        
        fid = None
        try:
            if is_video_force:
                log_msg = await client.send_video(LOGGER_ID, video=path, caption=f"ID: {vidid}\n{clean_full_title}")
                fid = log_msg.video.file_id
            else:
                log_msg = await client.send_audio(LOGGER_ID, audio=path, caption=f"ID: {vidid}\n{clean_full_title}")
                fid = log_msg.audio.file_id
            await cache_file(cache_key, fid)
        except: pass

        if is_video_force:
            await client.send_video(
                message.chat.id, video=path, caption=clean_full_title,
                reply_markup=reply_markup, reply_to_message_id=message.id
            )
        else:
            await client.send_audio(
                message.chat.id, audio=path, caption=clean_full_title,
                reply_markup=reply_markup, reply_to_message_id=message.id
            )

        await mystic.delete()
        if os.path.exists(path): os.remove(path)

    except Exception as e:
        traceback.print_exc()
        await mystic.edit_text(f"خطأ: {e}")

# ==========================================================
#  9. معالج زر (تشغيل الان) التفاعلي
# ==========================================================
@app.on_callback_query(filters.regex("force_play") & ~BANNED_USERS)
async def force_play_cb(client, query):
    try:
        vidid = query.data.split()[1]
    except: return

    chat_id = query.message.chat.id
    user_id = query.from_user.id
    user_name = query.from_user.first_name

    await query.answer("جاري التشغيل في الكول...")
    
    # 1. تغيير الأزرار لأزرار التحكم
    new_buttons = [
        [
            InlineKeyboardButton(text="▢", callback_data=f"stream_admin Stop|{chat_id}"),
            InlineKeyboardButton(text="↻", callback_data=f"stream_admin Replay|{chat_id}"),
            InlineKeyboardButton(text="II", callback_data=f"stream_admin Pause|{chat_id}"),
        ]
    ]
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_buttons))
    except: pass

    # 2. بدء التشغيل
    try:
        details, _ = await YouTube.track(vidid, videoid=vidid)
        mystic = await query.message.reply_text(f"جاري تشغيل: {details['title']}")
        
        await stream(
            _,
            mystic,
            user_id,
            details,
            chat_id,
            user_name,
            chat_id,
            video=False,
            streamtype="youtube",
            forceplay=True, 
        )
        await mystic.delete()
    except Exception as e:
        await query.message.reply_text("فشل التشغيل، تأكد من وجود مكالمة.")

# ==========================================================
#  10. Callbacks
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
    except: return await query.edit_message_text("فشل.")
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
    keyboard.append([InlineKeyboardButton(text="رجوع", callback_data=f"song_back {stype}|{vidid}"), InlineKeyboardButton(text="إغلاق", callback_data="close")])
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)
    try: await query.answer("جـاري التنزيل...", show_alert=True)
    except: pass
    
    data = query.data.strip().split(None, 1)[1].split("|")
    if len(data) == 3:
        stype, format_id, vidid = data
        is_video = True if stype == "video" else False
    else:
        stype, vidid = data
        is_video = False

    yturl = f"https://www.youtube.com/watch?v={vidid}"
    await direct_download_handler(client, query.message, yturl, is_video_force=is_video)
