# Authored By Certified Coders © 2026
# System: Play Command Handler (Fixed Live Stream & Playlist Thumbnails Logic)
# Compatibility: PyTgCalls v3.0 Native Chain

import asyncio
import random
import string

from pyrogram import filters
from pyrogram.errors import FloodWait, RandomIdDuplicate
from pyrogram.types import InlineKeyboardMarkup, InputMediaPhoto, Message
from motor.motor_asyncio import AsyncIOMotorClient

import config
from config import AYU, BANNED_USERS, lyrical, MONGO_DB_URI, OWNER_ID
from AnnieXMedia import Apple, Resso, SoundCloud, Spotify, Telegram, YouTube, app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.utils import seconds_to_min, time_to_seconds
from AnnieXMedia.utils.channelplay import get_channeplayCB
from AnnieXMedia.utils.decorators.language import languageCB
from AnnieXMedia.utils.decorators.play import PlayWrapper
from AnnieXMedia.utils.errors import capture_err, capture_callback_err
from AnnieXMedia.utils.formatters import formats
from AnnieXMedia.utils.exceptions import AssistantErr
from AnnieXMedia.utils.inline import (
    botplaylist_markup,
    livestream_markup,
    playlist_markup,
    slider_markup,
    track_markup,
)
from AnnieXMedia.utils.logger import play_logs
from AnnieXMedia.utils.stream.stream import stream

# ==========================================================
# 🗄️ إعدادات قاعدة البيانات (نظام قفل البحث)
# ==========================================================

SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
_mongo_client_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_client_.Annie
songdb = mongodb.song_settings

async def get_search_state():
    try:
        data = await songdb.find_one({"_id": "song_config"})
        if not data: return False
        return data.get("search_locked", False)
    except: return False

async def set_search_state(locked: bool):
    try:
        await songdb.update_one({"_id": "song_config"}, {"$set": { "search_locked": locked }}, upsert=True)
    except: pass

async def _safe_delete_msg(msg):
    try:
        if msg: await msg.delete()
    except: pass

# ==========================================================
# 🔒 أوامر التحكم (أدمن المطور)
# ==========================================================

@app.on_message(filters.command(["قفل البحث", "تعطيل البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_search_cmd(client, message):
    await set_search_state(True)
    await message.reply_text("**تم قفل البحث بنجاح .**")

@app.on_message(filters.command(["فتح البحث", "تفعيل البحث"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_search_cmd(client, message):
    await set_search_state(False)
    await message.reply_text("**تم فتح البحث بنجاح .**")

# ==========================================================
# 🎵 كود التشغيل الرئيسي (The Main Engine)
# ==========================================================

@app.on_message(
    filters.command(
        [
            "play", "vplay", "cplay", "cvplay", "playforce", "vplayforce", "cplayforce", "cvplayforce",
            "تشغيل", "شغل", "فيد", "فيديو"
        ],
        prefixes=["", "/", "!", "#"]
    )
    & filters.group
    & ~BANNED_USERS
)
@PlayWrapper
@capture_err
async def play_command(
    client,
    message: Message,
    _,
    chat_id,
    video,
    channel,
    playmode,
    url,
    fplay,
):
    # 1. التحقق من القفل
    is_locked = await get_search_state()
    if is_locked and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("- البحـث مغلـق .")

    # 2. تحديد نوع الميديا (فيديو ولا صوت)
    command = message.command[0] if message.command else ""
    if command in ["فيد", "فيديو", "vplay", "cvplay"]:
        video = True
    
    # 3. رسالة الانتظار
    wait_text = _["play_2"].format(channel) if channel else random.choice(AYU)
    try:
        mystic = await message.reply_text(wait_text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        mystic = await message.reply_text(wait_text)
    except RandomIdDuplicate:
        mystic = await app.send_message(message.chat.id, wait_text)

    # تهيئة المتغيرات
    plist_id = None
    plist_type = None
    spotify = None
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    internal_type = None

    # ==========================
    # A. الرد على ملف صوتي (Audio Reply)
    # ==========================
    audio_telegram = (message.reply_to_message.audio or message.reply_to_message.voice) if message.reply_to_message else None
    if audio_telegram:
        if audio_telegram.file_size > config.TG_AUDIO_FILESIZE_LIMIT:
            return await mystic.edit_text(_["play_5"])
        if audio_telegram.duration > config.DURATION_LIMIT:
            return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, app.mention))

        file_path = await Telegram.get_filepath(audio=audio_telegram)
        if await Telegram.download(_, message, mystic, file_path):
            message_link = await Telegram.get_link(message)
            file_name = await Telegram.get_filename(audio_telegram, audio=True)
            dur = await Telegram.get_duration(audio_telegram, file_path)
            details = {"title": file_name, "link": message_link, "path": file_path, "dur": dur}

            try:
                await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, video=False, streamtype="telegram", forceplay=bool(fplay))
            except Exception as e:
                await _safe_delete_msg(mystic)
                return await app.send_message(chat_id, _["general_2"].format(type(e).__name__))

            await play_logs(message, streamtype="Telegram [Audio]", query=message.reply_to_message.caption or "—")
            return await _safe_delete_msg(mystic)
        return

    # ==========================
    # B. الرد على فيديو (Video Reply)
    # ==========================
    video_telegram = (message.reply_to_message.video or message.reply_to_message.document) if message.reply_to_message else None
    if video_telegram:
        if message.reply_to_message.document:
            try:
                ext = (video_telegram.file_name or "").split(".")[-1]
                if ext.lower() not in formats:
                    return await mystic.edit_text(_["play_7"].format(" | ".join(formats)))
            except:
                return await mystic.edit_text(_["play_7"].format(" | ".join(formats)))

        if video_telegram.file_size > config.TG_VIDEO_FILESIZE_LIMIT:
            return await mystic.edit_text(_["play_8"])

        file_path = await Telegram.get_filepath(video=video_telegram)
        if await Telegram.download(_, message, mystic, file_path):
            message_link = await Telegram.get_link(message)
            file_name = await Telegram.get_filename(video_telegram)
            dur = await Telegram.get_duration(video_telegram, file_path)
            details = {"title": file_name, "link": message_link, "path": file_path, "dur": dur}

            try:
                await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, video=True, streamtype="telegram", forceplay=bool(fplay))
            except Exception as e:
                await _safe_delete_msg(mystic)
                return await app.send_message(chat_id, _["general_2"].format(type(e).__name__))

            await play_logs(message, streamtype="Telegram [Video]", query=message.reply_to_message.caption or "—")
            return await _safe_delete_msg(mystic)
        return

    # ==========================
    # C. الروابط (URLs: YT, Spotify, Apple, etc.)
    # ==========================
    if url:
        if await YouTube.exists(url):
            if "playlist" in url:
                try:
                    details = await YouTube.playlist(url, config.PLAYLIST_FETCH_LIMIT, user_id)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                
                plist_type = "yt"
                plist_id = (url.split("="))[1].split("&")[0] if "&" in url else (url.split("="))[1]
                img = config.PLAYLIST_IMG_URL
                cap = _["play_9"]
                internal_type = "playlist"
                log_label = "Youtube playlist"
            else:
                try:
                    details, track_id = await YouTube.track(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                
                img = details.get("thumb", config.YOUTUBE_IMG_URL)
                cap = _["play_10"].format(details["title"], details["duration_min"])
                internal_type = "youtube"
                log_label = "Youtube Track"

        elif await Spotify.valid(url):
            spotify = True
            if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
                return await mystic.edit_text("» Spotify not supported yet.")
            
            if "track" in url:
                try:
                    details, track_id = await Spotify.track(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                img = details.get("thumb", config.SPOTIFY_ARTIST_IMG_URL)
                cap = _["play_10"].format(details["title"], details["duration_min"])
                internal_type = "youtube"
                log_label = "Spotify Track"
            elif "playlist" in url:
                try:
                    details, plist_id = await Spotify.playlist(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                plist_type = "spplay"
                img = config.SPOTIFY_PLAYLIST_IMG_URL
                cap = _["play_11"].format(app.mention, message.from_user.mention)
                internal_type = "playlist"
                log_label = "Spotify playlist"
            elif "album" in url:
                try:
                    details, plist_id = await Spotify.album(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                plist_type = "spalbum"
                img = config.SPOTIFY_ALBUM_IMG_URL
                cap = _["play_11"].format(app.mention, message.from_user.mention)
                internal_type = "playlist"
                log_label = "Spotify album"
            elif "artist" in url:
                try:
                    details, plist_id = await Spotify.artist(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                plist_type = "spartist"
                img = config.SPOTIFY_ARTIST_IMG_URL
                cap = _["play_11"].format(message.from_user.first_name)
                internal_type = "playlist"
                log_label = "Spotify artist"
            else:
                return await mystic.edit_text(_["play_15"])

        elif await Apple.valid(url):
            if "album" in url or "/song/" in url:
                try:
                    details, track_id = await Apple.track(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                img = details.get("thumb", config.PLAYLIST_IMG_URL)
                cap = _["play_10"].format(details["title"], details["duration_min"])
                internal_type = "youtube"
                log_label = "Apple Music"
            elif "playlist" in url:
                spotify = True
                try:
                    details, plist_id = await Apple.playlist(url)
                except Exception as e:
                    return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
                plist_type = "apple"
                img = config.PLAYLIST_IMG_URL  # Bug fixed here! (was url)
                cap = _["play_12"].format(app.mention, message.from_user.mention)
                internal_type = "playlist"
                log_label = "Apple Music playlist"
            else:
                return await mystic.edit_text(_["play_3"])

        elif await Resso.valid(url):
            try:
                details, track_id = await Resso.track(url)
            except Exception as e:
                return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
            img = details.get("thumb", config.PLAYLIST_IMG_URL)
            cap = _["play_10"].format(details["title"], details["duration_min"])
            internal_type = "youtube"
            log_label = "Resso"

        elif await SoundCloud.valid(url):
            try:
                details, track_path = await SoundCloud.download(url)
            except Exception as e:
                return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")
            if details["duration_sec"] > config.DURATION_LIMIT:
                return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, app.mention))
            
            try:
                await stream(_, mystic, user_id, details, chat_id, user_name, message.chat.id, streamtype="soundcloud", forceplay=bool(fplay))
            except Exception as e:
                await _safe_delete_msg(mystic)
                return await app.send_message(chat_id, _["general_2"].format(type(e).__name__))
            
            await play_logs(message, streamtype="Soundcloud")
            return await _safe_delete_msg(mystic)

        else:
            # Index / M3U8 Link
            try:
                await stream(_, mystic, user_id, url, chat_id, user_name, message.chat.id, video=bool(video), streamtype="index", forceplay=bool(fplay))
                return await play_logs(message, streamtype="M3U8 or Index Link")
            except Exception as e:
                await _safe_delete_msg(mystic)
                return await app.send_message(chat_id, _["general_2"].format(type(e).__name__))

    # ==========================
    # D. البحث (Search Query)
    # ==========================
    else:
        if len(message.command) < 2:
            buttons = botplaylist_markup(_)
            return await mystic.edit_text(_["play_18"], reply_markup=InlineKeyboardMarkup(buttons))

        slider = True
        query = message.text.split(None, 1)[1]
        if "-v" in query: query = query.replace("-v", "")
        
        try:
            details, track_id = await YouTube.track(query)
        except Exception as e:
            return await mystic.edit_text(f"{_['play_3']}\nʀᴇᴀsᴏɴ: {e}")

        internal_type = "youtube"
        log_label = "Youtube Track"

    # ==========================
    # التنفيذ النهائي (Final Execution)
    # ==========================
    if str(playmode) == "Direct":
        if not plist_type:
            # 🔥 Fix: Live Stream Condition
            # If duration is valid AND not "Live", check limit.
            if details.get("duration_min") and str(details.get("duration_min")).lower() != "live":
                duration_sec = time_to_seconds(details["duration_min"])
                if duration_sec and duration_sec > config.DURATION_LIMIT:
                    return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, app.mention))
                
                try:
                    await stream(
                        _, mystic, user_id, details, chat_id, user_name, message.chat.id,
                        video=bool(video), streamtype=internal_type, spotify=spotify, forceplay=bool(fplay)
                    )
                except AssistantErr as e:
                    await _safe_delete_msg(mystic)
                    return await app.send_message(chat_id, str(e))
                except Exception as e:
                    await _safe_delete_msg(mystic)
                    return await app.send_message(chat_id, _["general_2"].format(type(e).__name__))

                await _safe_delete_msg(mystic)
                return await play_logs(message, streamtype=log_label)
            
            else:
                # This is a Live Stream -> Show Buttons
                buttons = livestream_markup(_, track_id, user_id, "v" if video else "a", "c" if channel else "g", "f" if fplay else "d")
                stream_img = details.get("thumb")
                if not stream_img or not str(stream_img).startswith("http"):
                    stream_img = config.YOUTUBE_IMG_URL
                    
                await _safe_delete_msg(mystic)
                return await message.reply_photo(
                    photo=stream_img,
                    caption=_["play_13"],
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

        else:
            # Playlist UI
            ran_hash = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
            lyrical[ran_hash] = plist_id
            buttons = playlist_markup(_, ran_hash, user_id, plist_type, "c" if channel else "g", "f" if fplay else "d")
            await _safe_delete_msg(mystic)

            # 🔥 Smart Thumbnail Extractor (نظام استخراج الصور الذكي لقوائم التشغيل)
            final_thumb = config.PLAYLIST_IMG_URL
            try:
                # إذا كانت التفاصيل عبارة عن قاموس ويحتوي على صورة
                if isinstance(details, dict) and details.get("thumb"):
                    final_thumb = details["thumb"]
                # إذا كانت التفاصيل عبارة عن قائمة (أبل ميوزك مثلاً)، اجلب صورة أول أغنية
                elif isinstance(details, list) and len(details) > 0 and isinstance(details[0], dict) and details[0].get("thumb"):
                    final_thumb = details[0]["thumb"]
                # كخطة بديلة نستخدم متغير img إذا كان صالحاً
                elif img and isinstance(img, str) and img.startswith("http") and "apple.com" not in img:
                    final_thumb = img
            except Exception:
                pass
            
            # حماية أخيرة قبل الإرسال (تمنع الكراش 100%)
            if not final_thumb or not str(final_thumb).startswith("http"):
                final_thumb = config.PLAYLIST_IMG_URL

            await message.reply_photo(
                photo=final_thumb,
                caption=cap,
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            plist_label_map = {
                "yt": "Youtube playlist", "spplay": "Spotify playlist", "spalbum": "Spotify album",
                "spartist": "Spotify artist", "apple": "Apple Music playlist"
            }
            return await play_logs(message, streamtype=plist_label_map.get(plist_type, "Playlist"))
            
    else:
        # Inline Search Slider
        buttons = slider_markup(_, track_id, user_id, query, 0, "c" if channel else "g", "f" if fplay else "d")
        await _safe_delete_msg(mystic)
        
        # حماية صورة البحث
        slide_thumb = details.get("thumb")
        if not slide_thumb or not str(slide_thumb).startswith("http"):
            slide_thumb = config.YOUTUBE_IMG_URL
            
        await message.reply_photo(
            photo=slide_thumb,
            caption=_["play_10"].format(details["title"].title(), details["duration_min"]),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return await play_logs(message, streamtype="Searched on YouTube")

# ==========================
# معالجات الأزرار (Callbacks)
# ==========================

@app.on_callback_query(filters.regex("MusicStream") & ~BANNED_USERS)
@languageCB
@capture_callback_err
async def play_music_cb(client, CallbackQuery, _):
    try:
        callback_data = CallbackQuery.data.split(None, 1)[1]
        vidid, user_id, mode, cplay, fplay = callback_data.split("|")

        if CallbackQuery.from_user.id != int(user_id):
            return await CallbackQuery.answer(_["playcb_1"], show_alert=True)

        chat_id, channel = await get_channeplayCB(_, cplay, CallbackQuery)
        user_name = CallbackQuery.from_user.first_name
        await CallbackQuery.message.delete()
        await CallbackQuery.answer()

        try:
            mystic = await CallbackQuery.message.reply_text(_["play_2"].format(channel) if channel else random.choice(AYU))
        except FloodWait as e:
            await asyncio.sleep(e.value)
            mystic = await CallbackQuery.message.reply_text(_["play_2"].format(channel) if channel else random.choice(AYU))
        except RandomIdDuplicate:
            mystic = await app.send_message(CallbackQuery.message.chat.id, _["play_2"].format(channel) if channel else random.choice(AYU))

        details, track_id = await YouTube.track(vidid, videoid=vidid)

        # 🔥 Fix: Live Stream Condition (Buttons)
        if details.get("duration_min") and str(details.get("duration_min")).lower() != "live":
            duration_sec = time_to_seconds(details["duration_min"])
            if duration_sec and duration_sec > config.DURATION_LIMIT:
                return await mystic.edit_text(_["play_6"].format(config.DURATION_LIMIT_MIN, app.mention))
            
            video = mode == "v"
            forceplay = fplay == "f"

            await stream(
                _, mystic, CallbackQuery.from_user.id, details, chat_id, user_name,
                CallbackQuery.message.chat.id, bool(video), streamtype="youtube", forceplay=bool(forceplay)
            )
            await _safe_delete_msg(mystic)
        else:
            # If Live, Show Confirmation Buttons
            buttons = livestream_markup(_, track_id, CallbackQuery.from_user.id, mode, "c" if cplay == "c" else "g", "f" if fplay else "d")
            return await mystic.edit_text(_["play_13"], reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        await _safe_delete_msg(mystic)
        err = _["general_2"].format(type(e).__name__)
        return await CallbackQuery.message.reply_text(err)

@app.on_callback_query(filters.regex("AnonymousAdmin") & ~BANNED_USERS)
@capture_callback_err
async def anonymous_check(client, CallbackQuery):
    try:
        await CallbackQuery.answer(
            "» ʀᴇᴠᴇʀᴛ ʙᴀᴄᴋ ᴛᴏ ᴜsᴇʀ ᴀᴄᴄᴏᴜɴᴛ :\n\n"
            "ᴏᴘᴇɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ sᴇᴛᴛɪɴɢs.\n"
            "-> ᴀᴅᴍɪɴɪsᴛʀᴀᴛᴏʀs\n-> ᴄʟɪᴄᴋ ᴏɴ ʏᴏᴜʀ ɴᴀᴍᴇ\n"
            "-> ᴜɴᴄʜᴇᴄᴋ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.",
            show_alert=True,
        )
    except Exception:
        pass

@app.on_callback_query(filters.regex("AnniePlaylists") & ~BANNED_USERS)
@languageCB
@capture_callback_err
async def play_playlists_command(client, CallbackQuery, _):
    try:
        callback_data = CallbackQuery.data.split(None, 1)[1]
        videoid, user_id, ptype, mode, cplay, fplay = callback_data.split("|")

        if CallbackQuery.from_user.id != int(user_id):
            return await CallbackQuery.answer(_["playcb_1"], show_alert=True)

        chat_id, channel = await get_channeplayCB(_, cplay, CallbackQuery)
        user_name = CallbackQuery.from_user.first_name
        await CallbackQuery.message.delete()
        await CallbackQuery.answer()

        try:
            mystic = await CallbackQuery.message.reply_text(_["play_2"].format(channel) if channel else random.choice(AYU))
        except FloodWait as e:
            await asyncio.sleep(e.value)
            mystic = await CallbackQuery.message.reply_text(_["play_2"].format(channel) if channel else random.choice(AYU))
        except RandomIdDuplicate:
            mystic = await app.send_message(CallbackQuery.message.chat.id, _["play_2"].format(channel) if channel else random.choice(AYU))

        videoid = lyrical.get(videoid)
        video = mode == "v"
        forceplay = fplay == "f"
        spotify = True

        if ptype == "yt":
            spotify = False
            result = await YouTube.playlist("", config.PLAYLIST_FETCH_LIMIT, CallbackQuery.from_user.id, videoid=videoid)
            internal_type = "playlist"
            log_label = "Youtube playlist"
        elif ptype == "spplay":
            result, _ = await Spotify.playlist(videoid)
            internal_type = "playlist"
            log_label = "Spotify playlist"
        elif ptype == "spalbum":
            result, _ = await Spotify.album(videoid)
            internal_type = "playlist"
            log_label = "Spotify album"
        elif ptype == "spartist":
            result, _ = await Spotify.artist(videoid)
            internal_type = "playlist"
            log_label = "Spotify artist"
        elif ptype == "apple":
            result, _ = await Apple.playlist(videoid, True)
            internal_type = "playlist"
            log_label = "Apple Music playlist"
        else:
            return

        await stream(
            _, mystic, CallbackQuery.from_user.id, result, chat_id, user_name,
            CallbackQuery.message.chat.id, bool(video), streamtype=internal_type, spotify=spotify, forceplay=bool(forceplay)
        )
        await play_logs(CallbackQuery.message, streamtype=log_label)
        await _safe_delete_msg(mystic)

    except Exception as e:
        await _safe_delete_msg(mystic)
        err = _["general_2"].format(type(e).__name__)
        return await CallbackQuery.message.reply_text(err)

@app.on_callback_query(filters.regex("slider") & ~BANNED_USERS)
@languageCB
@capture_callback_err
async def slider_queries(client, CallbackQuery, _):
    try:
        callback_data = CallbackQuery.data.split(None, 1)[1]
        what, rtype, query, user_id, cplay, fplay = callback_data.split("|")

        if CallbackQuery.from_user.id != int(user_id):
            return await CallbackQuery.answer(_["playcb_1"], show_alert=True)

        rtype = int(rtype)
        query_type = (rtype + 1) if what == "F" else (rtype - 1)

        if query_type > 9: query_type = 0
        if query_type < 0: query_type = 9

        title, duration_min, thumbnail, vidid = await YouTube.slider(query, query_type)
        buttons = slider_markup(_, vidid, user_id, query, query_type, cplay, fplay)
        
        # حماية لصورة البحث عند التحريك
        if not thumbnail or not str(thumbnail).startswith("http"):
            thumbnail = config.YOUTUBE_IMG_URL
            
        med = InputMediaPhoto(media=thumbnail, caption=_["play_10"].format(title.title(), duration_min))

        await CallbackQuery.edit_message_media(media=med, reply_markup=InlineKeyboardMarkup(buttons))
        await CallbackQuery.answer(_["playcb_2"])

    except Exception:
        pass
