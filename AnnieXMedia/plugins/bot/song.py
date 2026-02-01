# Authored By Certified Coders © 2026
# System: Song Plugin | Playlist Support | MongoDB Fixed | Pyromod
# Optimized for AnnieXMedia Bot Folder Structure

import asyncio
import os
import re
import time
from pyrogram import filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, 
    Message, 
    InputMediaAudio, 
    InputMediaVideo
)
from motor.motor_asyncio import AsyncIOMotorClient

# استيراد الإعدادات وكائن البوت الرئيسي
from config import (
    BANNED_USERS, 
    SONG_DOWNLOAD_DURATION, 
    SONG_DOWNLOAD_DURATION_LIMIT, 
    OWNER_ID, 
    MONGO_DB_URI
)
from AnnieXMedia import app
from AnnieXMedia.platforms.Youtube import YouTube 
from AnnieXMedia.platforms.YTProcessor import Processor 
from AnnieXMedia.utils.inline.song import song_markup

# ==========================================================
# الإعـدادات الـتـقـنـيـة والاتـصـال بـالـقـاعـدة
# ==========================================================

# معالجة OWNER_ID لضمان عمله سواء كان رقماً أو قائمة
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

_mongo_client_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_client_.Annie
songdb = mongodb.song_settings

async def get_config(key):
    """جلب الإعدادات من قاعدة البيانات"""
    try:
        data = await songdb.find_one({"_id": "song_config"})
        if not data: return False
        return data.get(key, False)
    except: return False

async def set_config(key, value):
    """تحديث الإعدادات في قاعدة البيانات"""
    try:
        await songdb.update_one({"_id": "song_config"}, {"$set": {key: value}}, upsert=True)
    except: pass

# ==========================================================
# أوامـر الـتـحـكـم والـقـفـل (لـلـمـطـور فـقـط)
# ==========================================================

@app.on_message(filters.command(["قفل البحث", "تعطيل البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_whole_section(client, message):
    await set_config("search_locked", True)
    await message.reply_text("**تـم قـفـل قـسـم الـبـحـث والـتـحـمـيـل نـهـائـيـاً عـن الـأعـضـاء.**")

@app.on_message(filters.command(["فتح البحث", "تفعيل البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_whole_section(client, message):
    await set_config("search_locked", False)
    await message.reply_text("**تـم فـتـح قـسـم الـبـحـث والـتـحـمـيـل لـلـجـمـيـع.**")

@app.on_message(filters.command(["قفل انلاين البحث", "قفل انلاين بحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_inline_search(client, message):
    await set_config("inline_locked", True)
    await message.reply_text("**تـم قـفـل بـحـث الانـلايـن (الأزرار).**")

@app.on_message(filters.command(["فتح انلاين البحث", "فتح انلاين بحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_inline_search(client, message):
    await set_config("inline_locked", False)
    await message.reply_text("**تـم فـتـح بـحـث الانـلايـن.**")

# ==========================================================
# الـمـعـالـج الـذكـي الـمـوحـد (Regex Engine)
# ==========================================================

@app.on_message(filters.regex(r"^/?(اغنية|اغنيه|هات|هاتلي|ابعتلي|song|video|تحميل|يوتيوب)(?:\s+(فيد|فيديو|video))?(?:\s+(.+))?$") & ~BANNED_USERS, group=5)
async def unified_song_processor(client, message: Message):
    
    # 1. فحص القفل العام
    is_search_locked = await get_config("search_locked")
    if is_search_locked and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("**عـذراً، الـقـسـم مـغـلـق حـالـيـاً مـن قـبـل الـمـطـور.**")

    match = re.match(r"^/?(اغنية|اغنيه|هات|هاتلي|ابعتلي|song|video|تحميل|يوتيوب)(?:\s+(فيد|فيديو|video))?(?:\s+(.+))?$", message.text)
    if not match: return
    
    command_trigger = match.group(1).lower()
    video_trigger = match.group(2)
    query = match.group(3)

    is_video_request = command_trigger in ["video", "/video", "فيديو"] or video_trigger

    # 2. نظام التفاعل الذكي (Pyromod Listen)
    if not query:
        prompt = await message.reply_text("**ارسـل الان اسـم الـمـقـطـع أو رابـط الـقـائـمـة.**")
        try:
            response = await client.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=20)
            if response and response.text:
                query = response.text
                await prompt.delete()
            else:
                return await prompt.edit_text("**تـم انـهـاء الانـتـظـار لـعـدم الـرد.**")
        except Exception:
            return await prompt.edit_text("**حـدث خـطـأ فـي نـظـام الـاسـتـمـاع.**")

    mystic = await message.reply_text("**جـارٍ الـمـعـالـجـة والـبـحـث...**")

    # 3. اكتشاف قوائم التشغيل (Playlists)
    if "list=" in query and ("youtube.com" in query or "youtu.be" in query):
        try:
            await Processor.download_playlist(
                client=client, 
                mystic_msg=mystic, 
                playlist_url=query, 
                is_video=is_video_request, 
                user_name=message.from_user.first_name
            )
        except Exception as e:
            await mystic.edit_text(f"**حـدث خـطـأ فـي الـقـائـمـة:** {e}")
        return

    # 4. معالجة الطلبات الفردية
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
        if duration_sec is None: duration_sec = 0
        
        if int(duration_sec) > 14400:
            return await mystic.edit_text("**عـذراً، الـمـقـطـع طـويـل جـداً (الـحـد الـأقـصـى 4 سـاعـات).**")
        
        is_inline_locked = await get_config("inline_locked")

        # التحميل المباشر (في حال قفل الأزرار)
        if is_inline_locked:
             await mystic.edit_text("**جـارٍ الـتـحـمـيـل الـفـوري...**")
             yturl = f"https://www.youtube.com/watch?v={vidid}"
             quality_arg = "high" if message.from_user.id in SUDO_USERS else "mid"

             file_path = await Processor.download_file(yturl, quality_arg, is_video_request, title, vidid=vidid, is_owner=(message.from_user.id in SUDO_USERS))
             await mystic.edit_text("**جـارٍ الـرفـع لـتـلـيـجـرام...**")
             await Processor.upload_alexa_style(client, mystic, file_path, is_video_request, title, duration_sec, message.from_user.first_name, vidid=vidid)

        # عرض أزرار اختيار الجودة
        else:
            buttons = song_markup(None, vidid)
            await mystic.delete()
            await message.reply_photo(
                photo=thumbnail, 
                caption=f"**الـعـنـوان:** {title}\n**الـمـدة:** {duration_min}\n\n**اخـتـر الـجـودة والـنـوع:**",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    except Exception:
        # نظام البحث الاحتياطي (Fallback Search)
        is_inline_locked = await get_config("inline_locked")
        if is_inline_locked or is_video_request:
            await mystic.edit_text("**جـارٍ الـبـحـث والـتـحـمـيـل...**")
            file_path = await Processor.download_file(query, "mid", is_video_request, query, is_owner=(message.from_user.id in SUDO_USERS))
            if file_path:
                 await mystic.edit_text("**جـارٍ الـرفـع...**")
                 await Processor.upload_alexa_style(client, mystic, file_path, is_video_request, query, 0, message.from_user.first_name)
            else:
                await mystic.edit_text("**عـذراً، لـم يـتـم الـعـثـور عـلـى نـتـائـج.**")
        else:
             await mystic.edit_text("**عـذراً، لـم يـتـم الـعـثـور عـلـى نـتـائـج.**")

# ==========================================================
# أوامـر الـتـحـمـيـل الـمـبـاشـر (يـوت)
# ==========================================================

@app.on_message(filters.command(["يوت"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_direct_audio(client, message: Message):
    if await get_config("search_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("**عـذراً، الـقـسـم مـغـلـق.**")

    if len(message.command) > 1 and message.command[1] in ["فيد", "فيديو", "video", "vid"]:
        return 

    if len(message.command) < 2:
        return await message.reply_text("**يـرجـى كـتـابـة الـرابـط بـجـانـب الـأمـر.**")
    
    query = message.text.split(None, 1)[1]
    mystic = await message.reply_text("**جـارٍ الـتـحـمـيـل...**")
    
    if "list=" in query:
         return await Processor.download_playlist(client, mystic, query, False, message.from_user.first_name)

    try:
        title, _, duration_sec, _, vidid = await YouTube.details(query)
        yturl = f"https://www.youtube.com/watch?v={vidid}"
        quality_arg = "high" if message.from_user.id in SUDO_USERS else "mid"
        file_path = await Processor.download_file(yturl, quality_arg, False, title, vidid=vidid, is_owner=(message.from_user.id in SUDO_USERS))
        await mystic.edit_text("**جـارٍ الـرفـع...**")
        await Processor.upload_alexa_style(client, mystic, file_path, False, title, duration_sec, message.from_user.first_name, vidid=vidid)
    except Exception as e:
        await mystic.edit_text(f"**حـدث خـطـأ:** {e}")

@app.on_message(filters.command(["يوت فيد", "يوت فيديو"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_direct_video(client, message: Message):
    if await get_config("search_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("**عـذراً، الـقـسـم مـغـلـق.**")

    if len(message.command) < 3: 
        return await message.reply_text("**يـرجـى كـتـابـة الـرابـط بـجـانـب الـأمـر.**")
    
    query = message.text.split(None, 2)[2]
    mystic = await message.reply_text("**جـارٍ الـتـحـمـيـل...**")
    
    if "list=" in query:
         return await Processor.download_playlist(client, mystic, query, True, message.from_user.first_name)
    
    try:
        title, _, duration_sec, _, vidid = await YouTube.details(query)
        yturl = f"https://www.youtube.com/watch?v={vidid}"
        quality_arg = "high" if message.from_user.id in SUDO_USERS else "mid"
        file_path = await Processor.download_file(yturl, quality_arg, True, title, vidid=vidid, is_owner=(message.from_user.id in SUDO_USERS))
        await mystic.edit_text("**جـارٍ الـرفـع...**")
        await Processor.upload_alexa_style(client, mystic, file_path, True, title, duration_sec, message.from_user.first_name, vidid=vidid)
    except Exception as e:
        await mystic.edit_text(f"**حـدث خـطـأ:** {e}")

# ==========================================================
# مـعـالـجـات الـتـفـاعـل (Callback Queries)
# ==========================================================

@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_callback(client, CallbackQuery):
    if await get_config("search_locked") and CallbackQuery.from_user.id not in SUDO_USERS:
        return await CallbackQuery.answer("قـسـم الـتـح_مـيـل مـغـلـق حـالـيـاً.", show_alert=True)

    if await get_config("inline_locked") and CallbackQuery.from_user.id not in SUDO_USERS:
         return await CallbackQuery.answer("هـذه الـمـيـزة مـعـطـلـة مـؤقـتـاً.", show_alert=True)

    stype, quality_arg, vidid = CallbackQuery.data.split(None, 1)[1].split("|")
    await CallbackQuery.answer("جـارٍ بـدء الـتـحـمـيـل...")
    
    try: mystic = await CallbackQuery.message.edit_text("**جـارٍ الـتـحـمـيـل مـن يـوتـيـوب...**")
    except: mystic = await client.send_message(CallbackQuery.message.chat.id, "**جـارٍ الـتـحـمـيـل...**")
    
    is_video = (stype == "video")
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    
    try:
        title, _, duration_sec, _, _ = await YouTube.details(vidid)
        file_path = await Processor.download_file(yturl, quality_arg, is_video, title, vidid=vidid, is_owner=(CallbackQuery.from_user.id in SUDO_USERS))
        await mystic.edit_text("**جـارٍ الـرفـع...**")
        await Processor.upload_alexa_style(client, mystic, file_path, is_video, title, duration_sec, CallbackQuery.from_user.first_name, vidid=vidid)
    except Exception:
        await mystic.edit_text("**فـشـل الـتـحـمـيـل، حـاول مـرة أخـرى لاحـقـاً.**")

@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_callback(client, CallbackQuery):
    if await get_config("search_locked") and CallbackQuery.from_user.id not in SUDO_USERS:
        return await CallbackQuery.answer("الـقـسـم مـغـلـق.", show_alert=True)

    stype, vidid = CallbackQuery.data.split(None, 1)[1].split("|")
    await CallbackQuery.answer("جـارٍ جـلـب خـيـارات الـجـودة...")
    buttons = await Processor.get_quality_buttons(vidid, stype)
    await CallbackQuery.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def song_back_callback(client, CallbackQuery):
    stype, vidid = CallbackQuery.data.split(None, 1)[1].split("|")
    buttons = song_markup(None, vidid)
    await CallbackQuery.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
