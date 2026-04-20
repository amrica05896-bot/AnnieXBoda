# Authored By Certified Coders © 2026
# System: Song Plugin (Final Version - Custom Playback)
# Fixes: Strict Audio/Video Recognition & Extension Forcing 🎵

import os
import re
import asyncio
import traceback
from pyrogram import enums, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
from AnnieXMedia.utils.inline.song import song_markup
from AnnieXMedia.utils.database import get_config, set_config, get_cached_file, cache_file, get_lang
from strings import get_string
from AnnieXMedia.utils.stream.stream import stream

SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
DEFAULT_LIST_LIMIT = 10
OWNER_USERNAME_LINK = "https://t.me/S_G0C7"

def clean_title(title: str) -> str:
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    bad_words = [
        "Official Video", "Official Audio", "Lyrics", "Video",
        "Music Video", "HD", "HQ", "4K", "ft.", "feat.",
        "Live", "Performance", "with Lyrics"
    ]
    for word in bad_words:
        title = title.replace(word, "").replace(word.lower(), "").replace(word.upper(), "")
    return title.strip()

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

def _build_list_keyboard(results: list, user_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for i, r in enumerate(results[:DEFAULT_LIST_LIMIT], start=1):
        clean_t = clean_title(r.get("title", "Unknown"))[:40]
        keyboard.append([InlineKeyboardButton(text=f"{i}. {clean_t}", callback_data=f"list_select {r.get('vidid', '')}|{user_id}")])
    keyboard.append([
        InlineKeyboardButton(text="المالك", url=OWNER_USERNAME_LINK),
        InlineKeyboardButton(text="إغلاق", callback_data="list_close"),
    ])
    return InlineKeyboardMarkup(keyboard)

# ==========================================================
# معالج ابعتلي / هات (تم إصلاح استخراج كلمة فيديو)
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
    
    # 🔴 التصليح: البحث الدقيق عن كلمة فيديو لإرسال الفيديو
    words = query.split()
    for kw in ["فيديو", "video", "فيد"]:
        if kw in words:
            is_video_request = True
            words.remove(kw)
            
    query = " ".join(words).strip()
    if not query:
        return await message.reply_text("يرجى كتابة اسم الأغنية.")

    url = await YouTube.url(message)
    if not url and ("http" in query): url = query

    if url:
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
        return await direct_download_handler(client, message, yt_link, is_video_request, show_play_btn=False)
    else:
        await mystic.delete()
        return await message.reply_photo(
            thumbnail,
            caption=f"العنوان: {title}\nالمدة: {duration_min}\n\nاختر طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(song_markup(None, vidid)),
        )

# ==========================================================
# أمر يوت (تم إصلاح استخراج كلمة فيديو)
# ==========================================================
@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")
    if len(message.command) < 2: return await message.reply_text("اكتب الاسم.")
    
    query = message.text.split(None, 1)[1]
    is_video = False
    
    # 🔴 التصليح: البحث الدقيق عن كلمة فيديو لإرسال الفيديو
    words = query.split()
    for kw in ["فيديو", "video", "فيد"]:
        if kw in words:
            is_video = True
            words.remove(kw)
            
    query = " ".join(words).strip()
    if not query:
        return await message.reply_text("اكتب الاسم.")
    
    if "http" in query:
        return await direct_download_handler(client, message, query.split()[0], is_video, show_play_btn=False)

    mystic = await message.reply_text("جاري البحث...")
    try:
        details = await YouTube.details(query)
        if details:
            link = f"https://www.youtube.com/watch?v={details[4]}"
            await mystic.delete()
            await direct_download_handler(client, message, link, is_video, show_play_btn=False)
        else: await mystic.edit_text("لم يتم العثور على نتائج.")
    except: await mystic.edit_text("حدث خطأ.")

# ==========================================================
# أمر ليست
# ==========================================================
@app.on_message(filters.command(["ليست", "لست"], prefixes=["", "/"]) & ~BANNED_USERS)
async def list_command(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    query = message.text.split(None, 1)[1].strip() if len(message.command) > 1 else None
    if not query:
        try:
            response = await client.ask(message.chat.id, "ارسل اسـم الفنان الان .", user_id=message.from_user.id, timeout=30, reply_markup=ForceReply(selective=True))
            query = response.text
        except: return 

    if "http" in query and ("list=" in query or "playlist" in query):
        await message.reply_text("تم الكشف عن بلاي ليست.. جاري المعالجة.")
        async def _process_playlist():
            try:
                limit = getattr(SongDownloader, "playlist_limit", DEFAULT_LIST_LIMIT) or DEFAULT_LIST_LIMIT
                ids = await YouTube.playlist(query, limit, message.from_user.id)
                if not ids: return
                for vid in ids[:limit]:
                    try:
                        await direct_download_handler(client, message, f"https://www.youtube.com/watch?v={vid}", False, show_play_btn=False)
                        await asyncio.sleep(1)
                    except: continue
            except: return
        asyncio.create_task(_process_playlist())
        return

    mystic = await message.reply_text("جاري البحث...")
    try:
        limit = getattr(SongDownloader, "playlist_limit", DEFAULT_LIST_LIMIT) or DEFAULT_LIST_LIMIT
        results = await YouTube.search(query, limit=int(limit))
    except: results = []

    if not results: return await mystic.edit_text("لم يتم العثور على نتائج.")
    await mystic.delete()
    return await message.reply_text("اخـتار من الـقـائمة التالية.\n\n                                       ـ", reply_markup=_build_list_keyboard(results, message.from_user.id))

# ==========================================================
# معالج التحميل الفعلي للرفع
# ==========================================================
async def direct_download_handler(client, message, url, is_video_force=False, show_play_btn=False):
    mystic = await message.reply_text("جاري المعالجة...")
    try:
        try:
            details = await YouTube.details(url)
            title, duration_sec, thumbnail_url, vidid = details[0], details[2], details[3], details[4] if details else ("Unknown", 0, None, None)
        except: title, duration_sec, thumbnail_url, vidid = "Unknown", 0, None, None

        clean_full_title = clean_title(title)
        artist = clean_full_title.split("-", 1)[0].strip() if "-" in clean_full_title else clean_full_title
        song = clean_full_title.split("-", 1)[1].strip() if "-" in clean_full_title else clean_full_title
        caption = f"الطلب: {message.from_user.mention}\nالعنوان: {song}"

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="- تـشغيل الان.", callback_data=f"force_play {vidid}")]]) if show_play_btn and vidid else None
        cache_key = f"{vidid}|{'video' if is_video_force else 'audio'}"
        cached = await get_cached_file(cache_key)

        if cached:
            await mystic.edit_text("جاري الرفع.")
            try:
                if is_video_force: await client.send_video(message.chat.id, video=cached, caption=caption, reply_markup=reply_markup, reply_to_message_id=message.id)
                else: await client.send_audio(message.chat.id, audio=cached, caption=caption, reply_markup=reply_markup, reply_to_message_id=message.id)
                return await mystic.delete()
            except: pass

        await mystic.edit_text("جاري التنزيل.")
        thumb_path = await YouTube.download_thumb(thumbnail_url) if thumbnail_url else None
        path, is_direct = await SongDownloader.download(url, is_video=is_video_force)
        
        if not path: return await mystic.edit_text("فشل التحميل.")

        # 🔴 الخدعة السحرية: إجبار الملف إنه يتعرف كصوت في تليجرام مهما كان امتداده الأصلي
        if not is_video_force:
            if not path.endswith((".m4a", ".mp3")):
                try:
                    new_path = path.rsplit(".", 1)[0] + ".m4a"
                    os.rename(path, new_path)
                    path = new_path
                except: pass

        await mystic.edit_text("جاري الرفع...")
        try:
            if is_video_force:
                log = await client.send_video(LOGGER_ID, video=path, caption=f"ID: `{vidid}`\n{clean_full_title}", duration=duration_sec, thumb=thumb_path)
                await cache_file(cache_key, log.video.file_id)
                await client.send_video(message.chat.id, video=path, caption=caption, duration=duration_sec, thumb=thumb_path, reply_markup=reply_markup)
            else:
                log = await client.send_audio(LOGGER_ID, audio=path, caption=f"ID: `{vidid}`\n{clean_full_title}", duration=duration_sec, title=song, performer=artist, thumb=thumb_path)
                await cache_file(cache_key, log.audio.file_id)
                await client.send_audio(message.chat.id, audio=path, caption=caption, duration=duration_sec, title=song, performer=artist, thumb=thumb_path, reply_markup=reply_markup)
        except: pass

        await mystic.delete()
        if not is_direct and os.path.exists(path): os.remove(path)
        if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)

    except Exception as e: await mystic.edit_text(f"خطأ: {e}")

# ==========================================================
# Callbacks
# ==========================================================
@app.on_callback_query(filters.regex(pattern=r"list_select") & ~BANNED_USERS)
async def list_select_cb(client, query):
    try:
        vidid, uid = query.data.split(None, 1)[1].split("|", 1)
        if query.from_user.id != int(uid): return await query.answer("مش ليك.", show_alert=True)
        await query.answer("جاري التحضير...", show_alert=False)
        await direct_download_handler(client, query.message, f"https://www.youtube.com/watch?v={vidid}", False, show_play_btn=True)
    except: await query.message.reply_text("فشل.")

@app.on_callback_query(filters.regex(pattern=r"force_play") & ~BANNED_USERS)
async def force_play_cb(client, query):
    try: vidid = query.data.split()[1]
    except: return
    chat_id, user_id, user_name = query.message.chat.id, query.from_user.id, query.from_user.first_name
    await query.answer("جاري التشغيل...", show_alert=False)
    try:
        language = await get_lang(chat_id)
        details, _ = await YouTube.track(vidid, videoid=vidid)
        await stream(get_string(language), query.message, user_id, details, chat_id, user_name, chat_id, video=False, streamtype="custom", forceplay=True)
    except Exception as e: await query.message.reply_text(f"فشل التشغيل: {e}")

@app.on_callback_query(filters.regex(pattern=r"list_close") & ~BANNED_USERS)
async def list_close_cb(client, query):
    try: await query.message.edit_reply_markup(None)
    except: pass
    
@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS: return
    return await query.edit_message_reply_markup(InlineKeyboardMarkup(song_markup(None, query.data.split("|")[1])))

@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS: return
    try: await query.answer("جاري...", show_alert=True)
    except: pass
    data = query.data.split("|")
    # 🔴 التصليح: تحديد إن الزر المنداس عليه هو فيديو ولا صوت بشكل سليم
    is_video = True if data[1].strip() == "video" else False
    await direct_download_handler(client, query.message, f"https://www.youtube.com/watch?v={data[2]}", is_video_force=is_video, show_play_btn=False)

@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS: return
    try: await query.answer("جاري...", show_alert=True)
    except: pass
    await direct_download_handler(client, query.message, f"https://www.youtube.com/watch?v={query.data.split('|')[1]}", not ("audio" in query.data), False)
