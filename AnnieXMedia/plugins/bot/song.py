# Authored By Certified Coders © 2026
# System: Song Plugin (Final Version - Custom Playback)
# Features: Exclusive List Play Button + Inline Stream Control

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
    ForceReply,
)

# استيرادات AnnieXMedia
from config import (
    BANNED_USERS,
    SONG_DOWNLOAD_DURATION,
    SONG_DOWNLOAD_DURATION_LIMIT,
    OWNER_ID,
    LOGGER_ID,
)
from AnnieXMedia import app
from AnnieXMedia.platforms import YouTube, SongDownloader
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import (
    get_config, set_config, get_cached_file, cache_file, get_lang
)
from strings import get_string

# استيراد دالة التشغيل
from AnnieXMedia.utils.stream.stream import stream

# تحديد المطورين
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

DEFAULT_LIST_LIMIT = 10
OWNER_USERNAME_LINK = "https://t.me/S_G0C7"

# ==========================================================
#  دالة تنظيف العناوين
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
#  أوامر التحكم (للمالك)
# ==========================================================
@app.on_message(filters.command(["رفع الجودة", "ارفع الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def enable_hq_cmd(client, message):
    SongDownloader.enable_quality()
    await message.reply_text("تم تفعيل الجودة العالية (HQ).")

@app.on_message(filters.command(["قفل الجودة", "اقفل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def disable_hq_cmd(client, message):
    SongDownloader.disable_quality()
    await message.reply_text("تم تعطيل الجودة العالية.")

@app.on_message(filters.command(["قفل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_download(client, message):
    await set_config("download_locked", True)
    await message.reply_text("تم تعطيل التنزيل.")

@app.on_message(filters.command(["فتح التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_download(client, message):
    await set_config("download_locked", False)
    await message.reply_text("تم تفعيل التنزيل.")

@app.on_message(filters.command(["قفل كيب البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_buttons(client, message):
    await set_config("buttons_locked", True)
    await message.reply_text("تم تعطيل أزرار البحث.")

@app.on_message(filters.command(["تفعيل كيب البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_buttons(client, message):
    await set_config("buttons_locked", False)
    await message.reply_text("تم تفعيل أزرار البحث.")

# ==========================================================
#  بناء كيبورد الليست
# ==========================================================
def _build_list_keyboard(results: list, user_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for i, r in enumerate(results[:DEFAULT_LIST_LIMIT], start=1):
        title = r.get("title", "Unknown")
        vidid = r.get("vidid", "")
        clean_t = clean_title(title)[:40]
        text = f"{i}. {clean_t}"
        callback = f"list_select {vidid}|{user_id}"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback)])
    
    keyboard.append([
        InlineKeyboardButton(text="المالك", url=OWNER_USERNAME_LINK),
        InlineKeyboardButton(text="إغلاق", callback_data="list_close"),
    ])
    return InlineKeyboardMarkup(keyboard)

# ==========================================================
#  المعالج الذكي (song / هات) -> (زر التشغيل مخفي ❌)
# ==========================================================
@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("عذراً، التنزيل متوقف حالياً.")

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text)
    if not match: return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("يرجى كتابة الاسم.")

    query = query.strip()
    is_video_request = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video_request = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()

    url = await YouTube.url(message)
    if not url and ("http" in query): url = query

    if url:
        # Play Button = False here
        return await direct_download_handler(client, message, url, is_video_request, show_play_btn=False)

    mystic = await message.reply_text("جاري البحث...")
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except: return await mystic.edit_text("لم يتم العثور على نتائج.")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"مدة المقطع أكبر من {SONG_DOWNLOAD_DURATION} دقيقة.")

    if await get_config("buttons_locked"):
        yt_link = f"https://www.youtube.com/watch?v={vidid}"
        await mystic.delete()
        # Play Button = False here
        return await direct_download_handler(client, message, yt_link, is_video_request, show_play_btn=False)
    else:
        buttons = song_markup(None, vidid)
        await mystic.delete()
        return await message.reply_photo(
            thumbnail,
            caption=f"العنوان: {title}\nالمدة: {duration_min}\n\nاختر طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

# ==========================================================
#  أمر (يوت / yut) -> (زر التشغيل مخفي ❌)
# ==========================================================
@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")
    if len(message.command) < 2: return await message.reply_text("اكتب الاسم.")
    
    query = message.text.split(None, 1)[1]
    is_video = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()
    
    if "http" in query:
        # Play Button = False here
        return await direct_download_handler(client, message, query.split()[0], is_video, show_play_btn=False)

    mystic = await message.reply_text("جاري البحث...")
    try:
        details = await YouTube.details(query)
        if details:
            vidid = details[4]
            link = f"https://www.youtube.com/watch?v={vidid}"
            await mystic.delete()
            # Play Button = False here
            await direct_download_handler(client, message, link, is_video, show_play_btn=False)
        else: await mystic.edit_text("لم يتم العثور على نتائج.")
    except: await mystic.edit_text("حدث خطأ.")

# ==========================================================
#  أمر (ليست / لست) - القائمة
# ==========================================================
@app.on_message(filters.command(["ليست", "لست"], prefixes=["", "/"]) & ~BANNED_USERS)
async def list_command(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    if len(message.text.split()) == 1:
        try:
            response = await client.ask(
                message.chat.id, 
                "ارسل اسـم الفنان الان .", 
                user_id=message.from_user.id, 
                timeout=30,
                reply_markup=ForceReply(selective=True)
            )
            query = response.text
        except: return 
    else:
        query = message.text.split(None, 1)[1].strip()

    if not query: return await message.reply_text("اكتب الاسم.")

    # بلاي ليست (روابط)
    if "http" in query and ("list=" in query or "playlist" in query):
        await message.reply_text("تم الكشف عن بلاي ليست.. جاري المعالجة.")
        async def _process_playlist():
            try:
                limit = getattr(SongDownloader, "playlist_limit", DEFAULT_LIST_LIMIT) or DEFAULT_LIST_LIMIT
                ids = await YouTube.playlist(query, limit, message.from_user.id)
                if not ids: return
                for vid in ids[:limit]:
                    try:
                        # في البلاي ليست الجماعية نغلق زر التشغيل
                        await direct_download_handler(client, message, f"https://www.youtube.com/watch?v={vid}", False, show_play_btn=False)
                        await asyncio.sleep(1)
                    except: continue
            except: return
        asyncio.create_task(_process_playlist())
        return

    # بحث القائمة
    mystic = await message.reply_text("جاري البحث...")
    try:
        limit = getattr(SongDownloader, "playlist_limit", DEFAULT_LIST_LIMIT) or DEFAULT_LIST_LIMIT
        results = await YouTube.search(query, limit=int(limit))
    except: results = []

    if not results: return await mystic.edit_text("لم يتم العثور على نتائج.")

    keyboard = _build_list_keyboard(results, message.from_user.id)
    
    text = (
        "اخـتار من الـقـائمة التالية.\n"
        "\n"
        "                                       ـ"
    )

    await mystic.delete()
    return await message.reply_text(text, reply_markup=keyboard)

# ==========================================================
#  دالة التحميل والرفع (مع منطق زر التشغيل)
# ==========================================================
async def direct_download_handler(client, message, url, is_video_force=False, show_play_btn=False):
    """
    show_play_btn: المتحكم الوحيد في ظهور زر التشغيل.
    """
    mystic = await message.reply_text("جاري المعالجة...")
    try:
        try:
            details = await YouTube.details(url)
            if details: title, _, duration_sec, thumbnail_url, vidid = details
            else: title, duration_sec, thumbnail_url, vidid = "Unknown", 0, None, None
        except: title, duration_sec, thumbnail_url, vidid = "Unknown", 0, None, None

        clean_full_title = clean_title(title)
        if "-" in clean_full_title:
            parts = clean_full_title.split("-", 1)
            artist = parts[0].strip(); song = parts[1].strip()
        else: artist = clean_full_title; song = clean_full_title
        if not artist or "annie" in artist.lower(): artist = "Unknown"

        caption = f"الطلب: {message.from_user.mention}\nالعنوان: {song}"

        # 🛑 منطق زر التشغيل الحصري
        reply_markup = None
        if show_play_btn and vidid:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="- تـشغيل الان.", callback_data=f"force_play {vidid}")]
            ])

        cache_key = f"{vidid}|{'video' if is_video_force else 'audio'}"
        cached = await get_cached_file(cache_key)

        if cached:
            await mystic.edit_text("جاري الرفع.")
            try:
                if is_video_force:
                    await client.send_video(message.chat.id, video=cached, caption=caption, reply_markup=reply_markup, reply_to_message_id=message.id)
                else:
                    await client.send_audio(message.chat.id, audio=cached, caption=caption, reply_markup=reply_markup, reply_to_message_id=message.id)
                await mystic.delete()
                return
            except: pass

        await mystic.edit_text("جاري التنزيل.")
        thumb_path = await YouTube.download_thumb(thumbnail_url) if thumbnail_url else None
        path, is_direct = await SongDownloader.download(url, is_video=is_video_force)
        
        if not path: return await mystic.edit_text("فشل التحميل.")

        await mystic.edit_text("جاري الرفع.")
        try:
            if is_video_force:
                log = await client.send_video(LOGGER_ID, video=path, caption=f"ID: `{vidid}`\n{clean_full_title}", duration=duration_sec, thumb=thumb_path)
                fid = log.video.file_id
            else:
                log = await client.send_audio(LOGGER_ID, audio=path, caption=f"ID: `{vidid}`\n{clean_full_title}", duration=duration_sec, title=song, performer=artist, thumb=thumb_path)
                fid = log.audio.file_id
            await cache_file(cache_key, fid)
        except: pass

        await mystic.edit_text("جاري الإرسال...")
        try:
            if is_video_force:
                await client.send_video(message.chat.id, video=path, caption=caption, duration=duration_sec, thumb=thumb_path, reply_markup=reply_markup)
            else:
                await client.send_audio(message.chat.id, audio=path, caption=caption, duration=duration_sec, title=song, performer=artist, thumb=thumb_path, reply_markup=reply_markup)
        except: pass

        await mystic.delete()
        if not is_direct and os.path.exists(path): os.remove(path)
        if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)

    except Exception as e:
        traceback.print_exc()
        await mystic.edit_text(f"خطأ: {e}")

# ==========================================================
#  Callbacks (Select & Force Play)
# ==========================================================

# 🛑 هذا الكولاك الوحيد الذي يرسل True لزر التشغيل
@app.on_callback_query(filters.regex(pattern=r"list_select") & ~BANNED_USERS)
async def list_select_cb(client, query):
    try:
        data = query.data.split(None, 1)[1]
        vidid, uid = data.split("|", 1)
        if query.from_user.id != int(uid): return await query.answer("مش ليك.", show_alert=True)
    except: return

    try: await query.answer("جاري التحضير...", show_alert=False)
    except: pass

    yturl = f"https://www.youtube.com/watch?v={vidid}"
    try:
        # ✅ show_play_btn=True هنا بس (لأنه جاي من الليست)
        await direct_download_handler(client, query.message, yturl, is_video_force=False, show_play_btn=True)
    except: await query.message.reply_text("فشل.")

# 🛑 كولاك زر التشغيل: معدل لاستخدام وضع 'custom'
@app.on_callback_query(filters.regex(pattern=r"force_play") & ~BANNED_USERS)
async def force_play_cb(client, query):
    try: vidid = query.data.split()[1]
    except: return

    chat_id = query.message.chat.id
    user_id = query.from_user.id
    user_name = query.from_user.first_name

    await query.answer("جاري التشغيل...", show_alert=False)
    
    try:
        # جلب اللغة (ضروري عشان stream.py يشتغل صح)
        language = await get_lang(chat_id)
        _ = get_string(language)

        details, _ = await YouTube.track(vidid, videoid=vidid)
        
        # 🔥 هنا التريك:
        # 1. بنبعت query.message (رسالة الملف) مكان mystic
        # 2. بنستخدم streamtype="custom" عشان يفعل اللوجيك الجديد في stream.py
        await stream(
            _, 
            query.message, # <--- دي الرسالة اللي هتتعدل أزرارها
            user_id,
            details,
            chat_id,
            user_name,
            chat_id,
            video=False,
            streamtype="custom", # ✅ مفتاح السر
            forceplay=True, 
        )
    except Exception as e:
        await query.message.reply_text(f"فشل التشغيل: {e}")

@app.on_callback_query(filters.regex(pattern=r"list_close") & ~BANNED_USERS)
async def list_close_cb(client, query):
    try: await query.message.edit_reply_markup(None)
    except: pass
    
# Callbacks للأغاني العادية (الزر مخفي)
@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS: return
    vidid = query.data.split("|")[1]
    return await query.edit_message_reply_markup(InlineKeyboardMarkup(song_markup(None, vidid)))

@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS: return
    try: await query.answer("جاري...", show_alert=True)
    except: pass
    data = query.data.split("|")
    vidid = data[2]
    is_video = True if data[0].strip().endswith("video") else False
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    # ❌ show_play_btn=False
    await direct_download_handler(client, query.message, yturl, is_video_force=is_video, show_play_btn=False)

@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS: return
    try: await query.answer("جاري جلب الصيغ...", show_alert=True)
    except: pass
    vidid = query.data.split("|")[1]
    is_audio = "audio" in query.data
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    # ❌ show_play_btn=False
    await direct_download_handler(client, query.message, yturl, is_video_force=not is_audio, show_play_btn=False)
