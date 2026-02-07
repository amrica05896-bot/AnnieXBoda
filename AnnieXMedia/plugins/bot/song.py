# Authored By Certified Coders © 2026
# System: Song Plugin (Smart Warehouse + Artist Name Logic) - No Emoji Edition
# Added commands: "ليست" and "لست"
# Behavior:
# - "ليست <query>" : shows top N search results (default 10) from YouTube with buttons for each result.
# - "ليست <playlist_url>" : if playlist URL provided, will process the playlist (respecting SongDownloader.playlist_limit).
# - Buttons include "المالك" (link) and "إغلاق".
# NOTE: This file is designed to integrate with the existing direct_download_handler and SongDownloader instance.

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
# استيراد دوال المستودع والكاش
from AnnieXMedia.utils.database import get_config, set_config, get_cached_file, cache_file

# تحديد المطورين (Sudo)
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# Default search limit for "ليست"
DEFAULT_LIST_LIMIT = 10

# Owner username for the "المالك" button (if you prefer to keep in config, replace here)
OWNER_USERNAME_LINK = "https://t.me/S_G0C7"

# ==========================================================
#  دالة تنظيف العناوين (The Cleaner)
# ==========================================================
def clean_title(title: str) -> str:
    # 1. إزالة ما بين الأقواس المربعة والدائرية [Official] (Video)
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    
    # 2. إزالة كلمات محددة تتكرر في يوتيوب
    bad_words = [
        "Official Video", "Official Audio", "Lyrics", "Video", 
        "Music Video", "HD", "HQ", "4K", "ft.", "feat.", 
        "Live", "Performance", "with Lyrics"
    ]
    for word in bad_words:
        title = title.replace(word, "")
        title = title.replace(word.lower(), "")
        title = title.replace(word.upper(), "")

    # 3. إزالة المسافات الزائدة
    title = title.strip()
    return title

# ==========================================================
#  1. أوامر التحكم بالجودة (للمالك فقط)
# ==========================================================
@app.on_message(filters.command(["رفع الجودة", "ارفع الجودة", "تفعيل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def enable_hq_cmd(client, message):
    SongDownloader.enable_quality()
    await message.reply_text("تم تفعيل الجودة العالية (HQ) للجميع.")

@app.on_message(filters.command(["قفل الجودة", "اقفل الجودة", "تعطيل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def disable_hq_cmd(client, message):
    SongDownloader.disable_quality()
    await message.reply_text("تم تعطيل الجودة العالية والعودة للوضع السريع.")

# ==========================================================
#  2. أوامر القفل والفتح العامة (للمالك)
# ==========================================================
@app.on_message(filters.command(["قفل التنزيل", "تعطيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_download(client, message):
    await set_config("download_locked", True)
    await message.reply_text("تم تعطيل التنزيل والبحث في البوت.")

@app.on_message(filters.command(["فتح التنزيل", "تفعيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_download(client, message):
    await set_config("download_locked", False)
    await message.reply_text("تم تفعيل التنزيل والبحث للجميع.")

@app.on_message(filters.command(["قفل كيب البحث", "قفل الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_buttons(client, message):
    await set_config("buttons_locked", True)
    await message.reply_text("تم تعطيل أزرار البحث (التحميل التلقائي).")

@app.on_message(filters.command(["تفعيل كيب البحث", "فتح الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_buttons(client, message):
    await set_config("buttons_locked", False)
    await message.reply_text("تم تفعيل أزرار البحث والاختيارات.")

# ==========================================================
#  Helper: build list keyboard from search results
# ==========================================================
def _build_list_keyboard(results: list, user_id: int) -> InlineKeyboardMarkup:
    """
    results: list of dicts with keys: title, vidid
    Each row: [ "index. title" -> callback list_select <vidid>|<user_id> ]
    Last row: [ "المالك" (url), "إغلاق" (callback list_close) ]
    """
    keyboard = []
    for i, r in enumerate(results[:DEFAULT_LIST_LIMIT], start=1):
        title = r.get("title", "Unknown")
        vidid = r.get("vidid", "")
        text = f"{i}. {title[:40]}"
        callback = f"list_select {vidid}|{user_id}"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback)])
    # final row
    keyboard.append([
        InlineKeyboardButton(text="المالك", url=OWNER_USERNAME_LINK),
        InlineKeyboardButton(text="إغلاق", callback_data="list_close"),
    ])
    return InlineKeyboardMarkup(keyboard)

# ==========================================================
#  3. أمر (هات / ابعتلي / song) - موجود بدون تعديل كبير
#     (لم يتم تغيير سلوك هذا الأمر)
# ==========================================================
@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("عذراً، التنزيل متوقف حالياً للصيانة.")

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text)
    if not match:
        return

    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("يرجى كتابة اسم الأغنية أو الرابط بعد الأمر.")

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
            return await message.reply_text("الرابط غير مدعوم، يرجى استخدام روابط يوتيوب.")
        return await direct_download_handler(client, message, url, is_video_request)

    # البحث
    mystic = await message.reply_text("جاري البحث...")
    
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("لم يتم العثور على نتائج.")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"عذراً، مدة المقطع تتجاوز {SONG_DOWNLOAD_DURATION} دقيقة.")

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
            caption=f"العنوان: {title}\nالمدة: {duration_min}\n\nاختر طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

# ==========================================================
#  4. أمر (يوت / yut) - موجود بدون تعديل
# ==========================================================
@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    if len(message.command) < 2:
        return await message.reply_text("اكتب اسم الأغنية أو الرابط بجانب الأمر.")
    
    # استخراج النص
    query = message.text.split(None, 1)[1]
    
    # --- كشف الفيديو ---
    is_video = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()
    
    # --- الحالة 1: المستخدم أرسل رابطاً ---
    if "http" in query:
        url = query.split()[0]
        if "youtu" in url or "googleusercontent" in url:
            return await direct_download_handler(client, message, url, is_video)
        else:
            return await message.reply_text("رابط غير مدعوم، تأكد من رابط يوتيوب.")

    # --- الحالة 2: المستخدم أرسل اسم بحث ---
    mystic = await message.reply_text("جاري البحث...")
    try:
        # نبحث عن أول نتيجة
        details = await YouTube.details(query)
        if details:
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
#  5. أمر (ليست / لست) - الجديد
#    - يعرض أول N نتائج بحث (زر لكل أغنية)
#    - إذا كان الرابط بلاي ليست: يعالج القائمة ويرسل الملفات واحداً واحداً
# ==========================================================
@app.on_message(filters.command(["ليست", "لست"], prefixes=["", "/"]) & ~BANNED_USERS)
async def list_command(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    if len(message.command) < 2:
        return await message.reply_text("اكتب اسم الفنان أو الرابط بعد الأمر.")

    query = message.text.split(None, 1)[1].strip()
    if not query:
        return await message.reply_text("يرجى كتابة اسم الفنان أو الرابط بعد الأمر.")

    # إذا المستخدم أرسل رابط بلاي ليست -> نفعل وضع البايلست
    if "http" in query and ("list=" in query or "playlist" in query):
        # كشف والرد الفوري
        await message.reply_text("تم الكشف عن بلاي ليست.\nجاري التنزيل.\nجاري الرفع.")
        # معالجة البلاي ليست في الخلفية (احترام الحد)
        async def _process_playlist():
            try:
                limit = getattr(SongDownloader, "playlist_limit", DEFAULT_LIST_LIMIT) or DEFAULT_LIST_LIMIT
                # YouTube.playlist expects (link, limit, user_id) in our platform
                try:
                    ids = await YouTube.playlist(query, limit, message.from_user.id)
                except Exception:
                    ids = []
                if not ids:
                    return
                # لكل id: استدعي direct_download_handler (سيقوم بالرفع والإرسال)
                for vid in ids[:limit]:
                    ylink = f"https://www.youtube.com/watch?v={vid}"
                    # استدعاء الممر الرئيسي للتحميل والرفع
                    try:
                        await direct_download_handler(client, message, ylink, is_video_force=False)
                        # صغير تأخير لتفادي FloodWait
                        await asyncio.sleep(1.2)
                    except Exception:
                        await asyncio.sleep(0.7)
                        continue
            except Exception:
                return

        # لا نغلق الاستجابة — نطلق المعالجة (ستقوم بالرفع كما في SongDownloader)
        asyncio.create_task(_process_playlist())
        return

    # خلاف ذلك: بحث عادي -> نظهر أول N نتائج كأزرار
    mystic = await message.reply_text("جاري البحث...")
    try:
        limit = getattr(SongDownloader, "playlist_limit", DEFAULT_LIST_LIMIT) or DEFAULT_LIST_LIMIT
        results = await YouTube.search(query, limit=int(limit))
    except Exception:
        results = []

    if not results:
        return await mystic.edit_text("لم يتم العثور على نتائج.")

    keyboard = _build_list_keyboard(results, message.from_user.id)
    # حذف الرسالة المؤقتة ثم عرض القائمة
    await mystic.delete()
    return await message.reply_photo(
        photo=(results[0].get("thumbnail") if results and results[0].get("thumbnail") else "https://telegra.ph/file/placeholder.jpg"),
        caption=f"نتائج البحث لـ: {query}\nاختر الأغنية من القائمة (الحد {limit})",
        reply_markup=keyboard,
    )

# ==========================================================
#  6. دالة التحميل والرفع (المستودع الذكي) - موجودة كما هي
# ==========================================================
async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("جاري المعالجة...")
    
    try:
        # 1. جلب التفاصيل
        try:
            details = await YouTube.details(url)
            if details:
                title, _, duration_sec, thumbnail_url, vidid = details
            else:
                title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None
        except:
            title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None

        # استخراج وتجميل اسم الفنان
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

        # تنسيق الرسالة النهائية بدون إيموجي
        caption_text = (
            f"الطلب بواسطة: {message.from_user.mention}\n"
            f"عنوان المقطع: {song_title}"
        )

        # فحص المستودع (Warehouse Check)
        cache_key = f"{vidid}|{'video' if is_video_force else 'audio'}"
        cached_file_id = await get_cached_file(cache_key)

        if cached_file_id:
            await mystic.edit_text("جاري الرفع.")
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
            except Exception as e:
                print(f"Cache failed: {e}")

        # لو مش في الكاش: حمل وارفع للمستودع
        await mystic.edit_text("جاري التنزيل.")

        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except:
                thumb_path = None

        path, is_direct_link = await SongDownloader.download(url, is_video=is_video_force)

        if not path:
             return await mystic.edit_text("فشل التحميل من المصدر.")

        await mystic.edit_text("جاري الرفع.")
        
        # الرفع لجروب السجل (المخزن)
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
            
            # حفظ في الداتا بيس
            await cache_file(cache_key, file_id_to_cache)

        except Exception as e:
            print(f"Warehouse Upload Error: {e}")

        # الإرسال للمستخدم
        await mystic.edit_text("جاري الإرسال...")
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
        except Exception:
             pass

        await mystic.delete()
        
        # تنظيف الملفات المؤقتة
        if not is_direct_link and os.path.exists(path):
            os.remove(path)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        traceback.print_exc()
        await mystic.edit_text(f"حدث خطأ: {e}")

# ==========================================================
#  7. Callbacks: list selection and close
# ==========================================================
@app.on_callback_query(filters.regex(pattern=r"list_select") & ~BANNED_USERS)
async def list_select_cb(client, query):
    """
    Callback data format: "list_select <vidid>|<user_id>"
    Only the original user can press the button.
    """
    try:
        payload = query.data.split(None, 1)[1]
        vidid, uid = payload.split("|", 1)
        uid = int(uid)
    except Exception:
        return await query.answer("خطأ في بيانات الزر.", show_alert=True)

    if query.from_user.id != uid:
        return await query.answer("مش ليك يقلب اخوك.", show_alert=True)

    # acknowledge
    try:
        await query.answer("جاري التحضير...", show_alert=False)
    except:
        pass

    # call direct download handler for the selected vid
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    try:
        # use the message that held the buttons as reference
        await direct_download_handler(client, query.message, yturl, is_video_force=False)
    except Exception as e:
        try:
            await query.message.reply_text("فشل في جلب الملف.")
        except:
            pass

@app.on_callback_query(filters.regex(pattern=r"list_close") & ~BANNED_USERS)
async def list_close_cb(client, query):
    try:
        await query.message.edit_reply_markup(reply_markup=None)
        await query.answer("تم الإغلاق.", show_alert=False)
    except Exception:
        try:
            await query.answer("تم الإغلاق.", show_alert=False)
        except:
            pass
