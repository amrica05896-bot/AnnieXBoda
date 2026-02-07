# file: plugins/song.py
# Authored By Certified Coders © 2026
# System: Song Plugin (Smart Warehouse + Playlist / "ليست" + Artist Name Logic)
# - Adds: "ليست / لست" playlist inspector + pick & play flow
# - Keeps behavior of existing song handlers; does NOT modify play.py or stream.py
# - Relies on existing AnnieXMedia interfaces: YouTube, SongDownloader, StreamController, DB helpers

import os
import re
import time
import asyncio
import traceback
from typing import Optional, List, Tuple, Dict, Any

from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)

from AnnieXMedia import app
from config import (
    BANNED_USERS,
    SONG_DOWNLOAD_DURATION,
    SONG_DOWNLOAD_DURATION_LIMIT,
    OWNER_ID,
    LOGGER_ID,
)
from AnnieXMedia.platforms import YouTube, SongDownloader
from AnnieXMedia.utils.formatters import convert_bytes
from AnnieXMedia.utils.inline.song import song_markup  # reuse existing markup
from AnnieXMedia.utils.database import get_config, set_config, get_cached_file, cache_file

# Sudo / Owner
SUDO_USERS = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]

# In-memory caches (lightweight, ephemeral)
_PL_FILE_CACHE: Dict[str, Tuple[str, float, bool]] = {}  # vidid -> (path_or_file_id, ts, is_direct_flag)
_PLAYLIST_MSG_TO_VIDS: Dict[int, List[str]] = {}  # message_id -> vidid list

# Cleanup settings
_CLEANUP_TTL = 60 * 15  # 15 minutes
_cleanup_task_started = False


# -------------------------
# Helper: Cleanup background
# -------------------------
async def _cleanup_loop():
    global _cleanup_task_started
    if _cleanup_task_started:
        return
    _cleanup_task_started = True
    while True:
        try:
            now = time.time()
            to_del = []
            for vid, (pth, ts, is_direct) in list(_PL_FILE_CACHE.items()):
                if now - ts > _CLEANUP_TTL:
                    try:
                        if pth and os.path.exists(pth) and not is_direct:
                            os.remove(pth)
                    except Exception:
                        pass
                    to_del.append(vid)
            for v in to_del:
                _PL_FILE_CACHE.pop(v, None)
        except Exception:
            pass
        await asyncio.sleep(60)


# start cleanup task
asyncio.get_event_loop().create_task(_cleanup_loop())


# -------------------------
# Title cleaner / artist extractor
# -------------------------
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


# -------------------------
# Owner commands: quality + locks + playlist limit control
# -------------------------
@app.on_message(filters.command(["رفع الجودة", "ارفع الجودة", "تفعيل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def enable_hq_cmd(client, message: Message):
    SongDownloader.enable_quality()
    await message.reply_text("تم تفعيل الجودة العالية (HQ).")


@app.on_message(filters.command(["قفل الجودة", "اقفل الجودة", "تعطيل الجودة"], prefixes="") & filters.user(SUDO_USERS))
async def disable_hq_cmd(client, message: Message):
    SongDownloader.disable_quality()
    await message.reply_text("تم تعطيل الجودة العالية.")


@app.on_message(filters.command(["قفل التنزيل", "تعطيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_download(client, message: Message):
    await set_config("download_locked", True)
    await message.reply_text("تم تعطيل التنزيل.")


@app.on_message(filters.command(["فتح التنزيل", "تفعيل التنزيل"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_download(client, message: Message):
    await set_config("download_locked", False)
    await message.reply_text("تم تفعيل التنزيل.")


@app.on_message(filters.command(["قفل كيب البحث", "قفل الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def lock_buttons(client, message: Message):
    await set_config("buttons_locked", True)
    await message.reply_text("تم تعطيل أزرار البحث.")


@app.on_message(filters.command(["تفعيل كيب البحث", "فتح الازرار"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def unlock_buttons(client, message: Message):
    await set_config("buttons_locked", False)
    await message.reply_text("تم تفعيل أزرار البحث.")


# Playlist limit admin controls (use SongDownloader methods)
@app.on_message(filters.command(["فتح الليميت", "open_limit"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def open_limit_cmd(client, message: Message):
    try:
        SongDownloader.open_limit()
        await message.reply_text("تم فتح الليمت (غير محدود).")
    except Exception as e:
        await message.reply_text(f"فشل: {e}")


@app.on_message(filters.command(["قفل الليميت", "reset_limit"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def reset_limit_cmd(client, message: Message):
    try:
        SongDownloader.reset_limit()
        await message.reply_text("تم إعادة الليمت للقيمة الافتراضية.")
    except Exception as e:
        await message.reply_text(f"فشل: {e}")


@app.on_message(filters.regex(r"^/?(?:وضع ليميت|set limit)\s+(\d+)$") & filters.user(SUDO_USERS))
async def set_limit_cmd(client, message: Message):
    try:
        parts = message.text.strip().split()
        n = int(parts[-1])
        SongDownloader.set_limit(n)
        await message.reply_text(f"تم ضبط الليمت إلى: {n}")
    except Exception as e:
        await message.reply_text(f"فشل ضبط الليمت: {e}")


@app.on_message(filters.command(["show_limit", "عرض_الليمت"], prefixes=["", "/"]) & filters.user(SUDO_USERS))
async def show_limit_cmd(client, message: Message):
    try:
        val = getattr(SongDownloader, "playlist_limit", None)
        await message.reply_text(f"الليميت الحالي: {val}")
    except Exception:
        await message.reply_text("غير قادر على جلب قيمة الليمت.")


# -------------------------
# Smart song handler (هات / ابعتلي / song) — unchanged behavior
# -------------------------
@app.on_message(filters.regex(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$") & filters.group & ~BANNED_USERS)
async def smart_song_handler(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("عذراً، التنزيل متوقف حالياً.")

    match = re.match(r"^/?(ابعتلي|هات|هاتلي|تنزيل|تحميل|song)(\s+.+)?$", message.text)
    if not match:
        return
    query = match.group(2)
    if not query or query.strip() == "":
        return await message.reply_text("يرجى كتابة اسم الأغنية أو الرابط بعد الأمر.")
    query = query.strip()

    is_video_request = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video_request = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()

    url = await YouTube.url(message)
    if not url and ("http" in query):
        url = query

    if url:
        if "youtu" not in url and "googleusercontent" not in url:
            return await message.reply_text("الرابط غير مدعوم، يرجى استخدام روابط يوتيوب.")
        return await direct_download_handler(client, message, url, is_video_request)

    mystic = await message.reply_text("**جـاري البحث...**")
    try:
        title, duration_min, duration_sec, thumbnail, vidid = await YouTube.details(query)
    except Exception:
        return await mystic.edit_text("لم يتم العثور على نتائج.")

    if int(duration_sec) > SONG_DOWNLOAD_DURATION_LIMIT:
        return await mystic.edit_text(f"عذراً، مدة المقطع تتجاوز {SONG_DOWNLOAD_DURATION} دقيقة.")

    if await get_config("buttons_locked"):
        yt_link = f"https://www.youtube.com/watch?v={vidid}"
        await mystic.delete()
        return await direct_download_handler(client, message, yt_link, is_video_request)
    else:
        buttons = song_markup(None, vidid)
        await mystic.delete()
        return await message.reply_photo(
            thumbnail,
            caption=f"**العنوان:** {title}\n**المدة:** {duration_min}\n\nاختار طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# -------------------------
# Command: يوت / yut (search or direct)
# -------------------------
@app.on_message(filters.command(["يوت", "yut"], prefixes=["", "/"]) & ~BANNED_USERS)
async def yut_command(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل مغلق حالياً.")

    if len(message.command) < 2:
        return await message.reply_text("اكتب اسم الأغنية أو الرابط بجانب الأمر.")

    query = message.text.split(None, 1)[1]

    is_video = False
    if re.search(r"\b(فيديو|video|فيد)\b", query):
        is_video = True
        query = re.sub(r"\b(فيديو|video|فيد)\b", "", query).strip()

    if "http" in query:
        url = query.split()[0]
        if "youtu" in url or "googleusercontent" in url:
            return await direct_download_handler(client, message, url, is_video)
        else:
            return await message.reply_text("رابط غير مدعوم، تأكد من رابط يوتيوب.")

    mystic = await message.reply_text("**جـاري البحث...**")
    try:
        details = await YouTube.details(query)
        if details:
            vidid = details[4]
            link = f"https://www.youtube.com/watch?v={vidid}"
            await mystic.delete()
            await direct_download_handler(client, message, link, is_video)
        else:
            await mystic.edit_text("لم يتم العثور على نتائج.")
    except Exception:
        await mystic.edit_text("حدث خطأ أثناء البحث.")


# -------------------------
# Direct download & warehouse upload flow
# -------------------------
async def direct_download_handler(client, message, url, is_video_force=False):
    mystic = await message.reply_text("**جـاري المعالجة...**")
    try:
        # fetch details
        try:
            details = await YouTube.details(url)
            if details:
                title, _, duration_sec, thumbnail_url, vidid = details
            else:
                title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None
        except Exception:
            title, duration_sec, thumbnail_url, vidid = "Unknown Track", 0, None, None

        clean_full_title = clean_title(title)
        if "-" in clean_full_title:
            parts = clean_full_title.split("-", 1)
            artist_name = parts[0].strip()
            song_title = parts[1].strip()
        else:
            artist_name = clean_full_title or "Unknown Artist"
            song_title = clean_full_title or "Unknown"

        caption_text = (
            f"**الطـلب بواسطـة:** {message.from_user.mention}\n"
            f"**عنـوان المقطـع:** {song_title}"
        )

        cache_key = f"{vidid}|{'video' if is_video_force else 'audio'}"
        cached_file_id = await get_cached_file(cache_key)

        if cached_file_id:
            await mystic.edit_text("**جـاري الرفع.**")
            try:
                if is_video_force:
                    await client.send_video(
                        message.chat.id,
                        video=cached_file_id,
                        caption=caption_text,
                        reply_to_message_id=message.id,
                    )
                else:
                    await client.send_audio(
                        message.chat.id,
                        audio=cached_file_id,
                        caption=caption_text,
                        reply_to_message_id=message.id,
                    )
                await mystic.delete()
                return
            except Exception:
                pass  # fallback to download

        await mystic.edit_text("**جـاري التنزيل.**")

        thumb_path = None
        if thumbnail_url:
            try:
                thumb_path = await YouTube.download_thumb(thumbnail_url)
            except Exception:
                thumb_path = None

        path, is_direct_link = await SongDownloader.download(url, is_video=is_video_force)
        if not path:
            return await mystic.edit_text("فشل التحميل من المصدر.")

        await mystic.edit_text("**جـاري الرفع.**")
        try:
            if is_video_force:
                log_msg = await client.send_video(
                    LOGGER_ID,
                    video=path,
                    caption=f"**Video Warehouse**\nID: `{vidid}`\nTitle: {clean_full_title}",
                    duration=duration_sec,
                    thumb=thumb_path,
                    supports_streaming=True,
                )
                file_id_to_cache = log_msg.video.file_id
            else:
                log_msg = await client.send_audio(
                    LOGGER_ID,
                    audio=path,
                    caption=f"**Audio Warehouse**\nID: `{vidid}`\nTitle: {clean_full_title}",
                    duration=duration_sec,
                    title=song_title,
                    performer=artist_name,
                    thumb=thumb_path,
                )
                file_id_to_cache = log_msg.audio.file_id

            await cache_file(cache_key, file_id_to_cache)
        except Exception as e:
            # ignore cache/upload failure but proceed to send to user
            print(f"Warehouse Upload Error: {e}")

        await mystic.edit_text("**جـاري الإرسال...**")
        try:
            if is_video_force:
                await client.send_video(
                    message.chat.id,
                    video=path,
                    caption=caption_text,
                    duration=duration_sec,
                    thumb=thumb_path,
                    supports_streaming=True,
                )
            else:
                await client.send_audio(
                    message.chat.id,
                    audio=path,
                    caption=caption_text,
                    duration=duration_sec,
                    title=song_title,
                    performer=artist_name,
                    thumb=thumb_path,
                )
        except Exception:
            pass

        await mystic.delete()

        # post-send caching in-memory
        try:
            # prefer storing file_id if cached, else local path record
            cached_after = await get_cached_file(cache_key)
            if cached_after:
                _PL_FILE_CACHE[vidid] = (cached_after, time.time(), True)
            else:
                _PL_FILE_CACHE[vidid] = (path, time.time(), False)
        except Exception:
            _PL_FILE_CACHE[vidid] = (path, time.time(), False)

        # cleanup local files if not direct link
        if not is_direct_link and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
            except Exception:
                pass

    except Exception as e:
        traceback.print_exc()
        await mystic.edit_text(f"حدث خطأ: {e}")


# -------------------------
# Playlist inspector: "ليست" / "لست"
# -------------------------
@app.on_message(filters.command(["ليست", "لست"], prefixes=["", "/"]) & ~BANNED_USERS)
async def playlist_command(client, message: Message):
    if await get_config("download_locked") and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("التنزيل متوقف حالياً.")

    args = message.text.split(None, 1)
    if len(args) < 2 or not args[1].strip():
        return await message.reply_text("أرسل رابط البلاي ليست بعد الأمر. مثال:\n/ليست https://www.youtube.com/playlist?list=...")
    link = args[1].strip()
    # quick check
    if "list=" not in link and not re.fullmatch(r"[A-Za-z0-9_-]+", link):
        return await message.reply_text("أرسل رابط بلاي ليست صحيح أو مُعرف list= ...")

    msg = await message.reply_text("تـم الـكـشـف عن بلاي ليست.\nجـاري جلب عناصر البلاي ليست...")
    try:
        limit = getattr(SongDownloader, "playlist_limit", 10)
        vid_list = await YouTube.playlist(link, limit=limit, user_id=message.from_user.id)
        if not vid_list:
            await msg.edit_text("لم أتمكن من الحصول على عناصر البلاي ليست أو هي فارغة.")
            return
        keyboard = []
        preview_lines = []
        cnt = 0
        for vid in vid_list[:limit]:
            try:
                title, _dur_min, dur_sec, thumb, vidid = await YouTube.details(vid, videoid=vid)
                label = title[:50] if title else vid
            except Exception:
                label = vid
                vidid = vid
            cnt += 1
            keyboard.append([InlineKeyboardButton(f"{cnt}. {label}", callback_data=f"pl_choose|{vidid}")])
            preview_lines.append(f"{cnt}. {label}")
        keyboard.append([InlineKeyboardButton("فتح القائمة كاملة", callback_data=f"pl_full|{link}")])
        keyboard.append([InlineKeyboardButton("إغلاق", callback_data="close")])
        await msg.edit_text("قائمة العناصر:\n\n" + "\n".join(preview_lines[:10]) + f"\n\nتم عرض أول {len(preview_lines[:10])} نتيجة.")
        sent = await message.reply_text("اختر الأغنية من الأزرار أدناه:", reply_markup=InlineKeyboardMarkup(keyboard))
        _PLAYLIST_MSG_TO_VIDS[sent.message_id] = vid_list[:limit]
    except Exception:
        traceback.print_exc()
        await msg.edit_text("فشل في جلب البلاي ليست. حاول لاحقاً.")


# -------------------------
# Playlist: pick item -> download -> send + attach play button
# -------------------------
@app.on_callback_query(filters.regex(r"^pl_choose\|") & ~BANNED_USERS)
async def pl_choose_cb(client, query: CallbackQuery):
    try:
        await query.answer("جاري التحضير...", show_alert=False)
    except Exception:
        pass
    try:
        _, vidid = query.data.split("|", 1)
    except Exception:
        return await query.answer("بيانات غير صحيحة.", show_alert=True)

    try:
        await query.edit_message_text("**جـاري التنزيل.**")
    except Exception:
        pass

    cache_key_audio = f"{vidid}|audio"
    cached = await get_cached_file(cache_key_audio)
    if cached:
        try:
            sent = await client.send_audio(
                query.message.chat.id,
                audio=cached,
                caption="تم التحميل من المخزن.",
                reply_to_message_id=query.message.message_id,
                disable_notification=True,
            )
            await client.edit_message_reply_markup(query.message.chat.id, sent.message_id, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▷", callback_data=f"pl_playnow|{vidid}")],[InlineKeyboardButton("إغلاق", callback_data="close")]]))
            _PL_FILE_CACHE[vidid] = (cached, time.time(), True)
            await query.answer("تم التحميل من المخزن.", show_alert=False)
            return
        except Exception:
            pass

    try:
        youtube_link = f"https://www.youtube.com/watch?v={vidid}"
        path, is_direct = await SongDownloader.download(youtube_link, is_video=False)
        if not path:
            await query.edit_message_text("فشل التحميل من المصدر.")
            return
        caption_text = f"تم التحميل: {vidid}"
        sent = await client.send_audio(
            query.message.chat.id,
            audio=path,
            caption=caption_text,
            reply_to_message_id=query.message.message_id,
            disable_notification=True,
        )
        try:
            file_id = sent.audio.file_id
            await cache_file(cache_key_audio, file_id)
            _PL_FILE_CACHE[vidid] = (file_id, time.time(), True)
        except Exception:
            _PL_FILE_CACHE[vidid] = (path, time.time(), False)
        await client.edit_message_reply_markup(query.message.chat.id, sent.message_id, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▷", callback_data=f"pl_playnow|{vidid}")],[InlineKeyboardButton("إغلاق", callback_data="close")]]))
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("تم التحميل.", show_alert=False)
    except Exception:
        traceback.print_exc()
        try:
            await query.edit_message_text("فشل في التحميل. حاول مرة أخرى.")
        except Exception:
            pass


# -------------------------
# Playnow -> join call + swap to 4 control buttons
# -------------------------
# Lightweight wrapper to call StreamController.join_call (best-effort)
async def _join_call_best_effort(chat_id: int, original_chat_id: int, path: str, video: bool = False):
    from AnnieXMedia.core import call as _call_mod
    SC = getattr(_call_mod, "StreamController", None) or getattr(_call_mod, "stream", None)
    # try common method names
    names = ["join_call", "join_stream", "join", "start_stream", "start_call", "play"]
    for nm in names:
        fn = getattr(SC, nm, None)
        if callable(fn):
            try:
                res = fn(chat_id, original_chat_id, path, video=video)
                if asyncio.iscoroutine(res):
                    await res
                return True
            except Exception:
                continue
    raise RuntimeError("StreamController join failed")


def _kbd_playnow(vidid: str) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("▷", callback_data=f"pl_playnow|{vidid}")],
        [InlineKeyboardButton("إغلاق", callback_data="close")],
    ]
    return InlineKeyboardMarkup(kb)


def _kbd_controls(vidid: str) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("▷", callback_data=f"pl_resume|{vidid}"),
            InlineKeyboardButton("II", callback_data=f"pl_pause|{vidid}"),
            InlineKeyboardButton("↻", callback_data=f"pl_restart|{vidid}"),
            InlineKeyboardButton("▢", callback_data=f"pl_stop|{vidid}"),
        ],
        [InlineKeyboardButton("إغلاق", callback_data="close")],
    ]
    return InlineKeyboardMarkup(kb)


@app.on_callback_query(filters.regex(r"^pl_playnow\|") & ~BANNED_USERS)
async def pl_playnow_cb(client, query: CallbackQuery):
    try:
        _, vidid = query.data.split("|", 1)
    except Exception:
        return await query.answer("بيانات غير صحيحة.", show_alert=True)

    record = _PL_FILE_CACHE.get(vidid)
    if not record:
        cached = await get_cached_file(f"{vidid}|audio")
        if cached:
            _PL_FILE_CACHE[vidid] = (cached, time.time(), True)
            record = _PL_FILE_CACHE.get(vidid)
    if not record:
        return await query.answer("الملف غير موجود. يرجى تحميله أولاً.", show_alert=True)

    path_or_id, ts, is_direct = record
    chat_id = query.message.chat.id
    original_chat_id = chat_id

    try:
        # attempt join
        await _join_call_best_effort(chat_id, original_chat_id, path_or_id, video=False)
    except Exception as e:
        traceback.print_exc()
        return await query.answer("فشل بدء التشغيل في المكالمة. تأكد أن البوت في الكول.", show_alert=True)

    try:
        await query.edit_message_reply_markup(reply_markup=_kbd_controls(vidid))
    except Exception:
        pass
    await query.answer("بدأ التشغيل.", show_alert=False)


# control callbacks
@app.on_callback_query(filters.regex(r"^pl_pause\|") & ~BANNED_USERS)
async def pl_pause_cb(client, query: CallbackQuery):
    try:
        from AnnieXMedia.core.call import StreamController
        fn = getattr(StreamController, "pause_stream", None) or getattr(StreamController, "pause", None)
        if callable(fn):
            res = fn(query.message.chat.id)
            if asyncio.iscoroutine(res):
                await res
            await query.answer("تم الإيقاف مؤقتاً.", show_alert=False)
            return
    except Exception:
        pass
    await query.answer("فشل الإيقاف المؤقت.", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_resume\|") & ~BANNED_USERS)
async def pl_resume_cb(client, query: CallbackQuery):
    try:
        from AnnieXMedia.core.call import StreamController
        fn = getattr(StreamController, "resume_stream", None) or getattr(StreamController, "resume", None)
        if callable(fn):
            res = fn(query.message.chat.id)
            if asyncio.iscoroutine(res):
                await res
            await query.answer("تم استئناف التشغيل.", show_alert=False)
            return
    except Exception:
        pass
    await query.answer("فشل الاستئناف.", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_restart\|") & ~BANNED_USERS)
async def pl_restart_cb(client, query: CallbackQuery):
    try:
        _, vidid = query.data.split("|", 1)
    except Exception:
        return await query.answer("بيانات غير صحيحة.", show_alert=True)

    rec = _PL_FILE_CACHE.get(vidid)
    if not rec:
        cached = await get_cached_file(f"{vidid}|audio")
        if cached:
            _PL_FILE_CACHE[vidid] = (cached, time.time(), True)
            rec = _PL_FILE_CACHE[vidid]
    if not rec:
        return await query.answer("الملف غير متوفر لإعادة التشغيل.", show_alert=True)

    path_or_id, _, is_direct = rec
    try:
        # stop then join
        from AnnieXMedia.core.call import StreamController
        stop_fn = getattr(StreamController, "stop_stream", None) or getattr(StreamController, "stop", None) or getattr(StreamController, "leave", None)
        if callable(stop_fn):
            res = stop_fn(query.message.chat.id)
            if asyncio.iscoroutine(res):
                await res
        await asyncio.sleep(0.4)
        await _join_call_best_effort(query.message.chat.id, query.message.chat.id, path_or_id, video=False)
        await query.answer("أعيد التشغيل.", show_alert=False)
    except Exception:
        traceback.print_exc()
        await query.answer("فشل إعادة التشغيل.", show_alert=True)


@app.on_callback_query(filters.regex(r"^pl_stop\|") & ~BANNED_USERS)
async def pl_stop_cb(client, query: CallbackQuery):
    try:
        from AnnieXMedia.core.call import StreamController
        stop_fn = getattr(StreamController, "stop_stream", None) or getattr(StreamController, "stop", None) or getattr(StreamController, "leave", None)
        if callable(stop_fn):
            res = stop_fn(query.message.chat.id)
            if asyncio.iscoroutine(res):
                await res
            await query.answer("تم إنهاء التشغيل.", show_alert=False)
            return
    except Exception:
        pass
    await query.answer("فشل إنهاء التشغيل.", show_alert=True)


# -------------------------
# Reuse existing song callbacks (formats / download)
# Expectation: song_markup callback names are "song_helper", "song_download", "song_back"
# -------------------------
@app.on_callback_query(filters.regex(pattern=r"song_back") & ~BANNED_USERS)
async def songs_back_helper(client, query: CallbackQuery):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)
    try:
        stype, vidid = query.data.strip().split(None, 1)[1].split("|")
    except Exception:
        return await query.answer("خطأ في البيانات.", show_alert=True)
    buttons = song_markup(None, vidid)
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(pattern=r"song_helper") & ~BANNED_USERS)
async def song_helper_cb(client, query: CallbackQuery):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)
    callback_data = query.data.strip()
    try:
        stype, vidid = callback_data.split(None, 1)[1].split("|")
    except Exception:
        return await query.answer("بيانات غير صحيحة.", show_alert=True)
    try:
        await query.answer("جاري جلب الصيغ...", show_alert=True)
    except Exception:
        pass

    try:
        formats_available, link = await YouTube.formats(vidid, True)
    except Exception:
        return await query.edit_message_text("فشل في جلب الجودات المتاحة.")

    keyboard = []
    done = []
    if stype == "audio":
        for x in formats_available:
            check = x.get("format", "")
            if "audio" in check:
                if x.get("filesize") is None:
                    continue
                form = x.get("format_note", "Audio").title()
                if form in done:
                    continue
                done.append(form)
                sz = convert_bytes(x["filesize"])
                fom = x["format_id"]
                keyboard.append([InlineKeyboardButton(text=f"{form} ({sz})", callback_data=f"song_download {stype}|{fom}|{vidid}")])
    else:
        supported_ids = [160, 133, 134, 135, 136, 137, 298, 299, 264, 304, 266]
        for x in formats_available:
            if x.get("filesize") is None:
                continue
            fid = int(x.get("format_id")) if str(x.get("format_id")).isdigit() else 0
            if fid not in supported_ids:
                continue
            sz = convert_bytes(x["filesize"])
            ap = x.get("format", "").split("-")[1] if "-" in x.get("format", "") else x.get("format", "")
            keyboard.append([InlineKeyboardButton(text=f"{ap} ({sz})", callback_data=f"song_download {stype}|{x['format_id']}|{vidid}")])

    keyboard.append([
        InlineKeyboardButton(text="رجوع", callback_data=f"song_back {stype}|{vidid}"),
        InlineKeyboardButton(text="إغلاق", callback_data="close"),
    ])
    return await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


@app.on_callback_query(filters.regex(pattern=r"song_download") & ~BANNED_USERS)
async def song_download_cb(client, query: CallbackQuery):
    if await get_config("download_locked") and query.from_user.id not in SUDO_USERS:
        return await query.answer("التنزيل مغلق حالياً.", show_alert=True)
    try:
        await query.answer("جـاري التنزيل...", show_alert=True)
    except Exception:
        pass
    try:
        stype, format_id, vidid = query.data.strip().split(None, 1)[1].split("|")
    except Exception:
        return await query.answer("بيانات غير صحيحة.", show_alert=True)
    mystic = await query.edit_message_text("**جـاري التنزيل.**")
    yturl = f"https://www.youtube.com/watch?v={vidid}"
    is_video = True if stype == "video" else False
    # reuse direct_download_handler (it will handle caching & upload)
    await direct_download_handler(client, query.message, yturl, is_video_force=is_video)


# -------------------------
# Close handler
# -------------------------
@app.on_callback_query(filters.regex(r"^close$") & ~BANNED_USERS)
async def close_cb(client, query: CallbackQuery):
    try:
        await query.message.delete()
    except Exception:
        try:
            await query.answer("تم الإغلاق.", show_alert=False)
        except Exception:
            pass
