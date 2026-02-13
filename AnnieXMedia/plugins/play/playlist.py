# Authored By Certified Coders © 2026
# System: Playlist Manager (Interactive Buttons)
# Compatibility: AnnieXMedia & PyTgCalls v3.0

import os
from random import randint

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import BANNED_USERS, SERVER_PLAYLIST_LIMIT, OWNER_ID
from AnnieXMedia import Carbon, YouTube, app
from AnnieXMedia.utils.database import (
    delete_playlist,
    get_playlist,
    get_playlist_names,
    save_playlist,
)
from AnnieXMedia.utils.decorators.language import language, languageCB
from AnnieXMedia.utils.inline.playlist import (
    botplaylist_markup,
    get_playlist_markup,
    warning_markup,
)
from AnnieXMedia.utils.stream.stream import stream

# ==========================================
#  أوامر عرض البلاي ليست (تفاعلية)
# ==========================================

@app.on_message(filters.command(["playlist", "قائمتي", "ماي ليست"], prefixes=["/", "!", "", "."]) & ~BANNED_USERS)
@language
async def check_playlist(client, message: Message, _):
    _playlist = await get_playlist_names(message.from_user.id)
    
    if not _playlist:
        return await message.reply_text(_["playlist_3"])
    
    buttons = []
    # إضافة أزرار للأغاني (زر لكل أغنية للحذف)
    for vidid in _playlist:
        _note = await get_playlist(message.from_user.id, vidid)
        title = _note["title"]
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{title[:25]} 🗑️",
                    callback_data=f"del_playlist {vidid}"
                )
            ]
        )
        
    # أزرار التحكم السفلية
    buttons.append(
        [
            InlineKeyboardButton(
                text="• تشغيل الكل •",
                callback_data=f"play_playlist {message.from_user.id}"
            )
        ]
    )
    
    # زر المالك (بالزخرفة المطلوبة وبدون رابط ظاهر)
    owner_id = OWNER_ID
    if isinstance(owner_id, list):
        owner_id = owner_id[0]
        
    buttons.append(
        [
            InlineKeyboardButton(
                text="ᎾᎳᏁᎬᏒ",  # الاسم المزخرف
                user_id=owner_id # يفتح البروفايل مباشرة
            )
        ]
    )
    
    buttons.append(
        [
            InlineKeyboardButton(
                text="إغلاق",
                callback_data="close"
            )
        ]
    )
    
    await message.reply_text(
        text=f"🎵 **القائمة الخاصة بك يا {message.from_user.mention}:**\n\n- اضغط على اسم الأغنية لحذفها.\n- اضغط تشغيل الكل لبدء الاستماع.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ==========================================
#  أوامر الحذف (باقي الملف)
# ==========================================

@app.on_message(filters.command(["delplaylist", "حذف قائمتي", "حذف البلاي ليست"], prefixes=["/", "!", "", "."]) & filters.group & ~BANNED_USERS)
@language
async def del_group_message(client, message: Message, _):
    upl = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=_["PL_B_6"],
                    url=f"https://t.me/{app.username}?start=delplaylists",
                ),
            ]
        ]
    )
    await message.reply_text(_["playlist_6"], reply_markup=upl)


async def get_keyboard(_, user_id):
    _playlist = await get_playlist_names(user_id)
    count = len(_playlist)
    buttons = []
    for x in _playlist:
        _note = await get_playlist(user_id, x)
        title = _note["title"]
        title = title.title()
        buttons.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"del_playlist {x}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(text=_["PL_B_5"], callback_data="delete_warning"),
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close"),
        ]
    )
    keyboard = InlineKeyboardMarkup(buttons)
    return keyboard, count


@app.on_message(filters.command(["delplaylist", "حذف قائمتي"], prefixes=["/", "!", "", "."]) & filters.private & ~BANNED_USERS)
@language
async def del_plist_msg(client, message: Message, _):
    _playlist = await get_playlist_names(message.from_user.id)
    if _playlist:
        get = await message.reply_text(_["playlist_2"])
    else:
        return await message.reply_text(_["playlist_3"])
    keyboard, count = await get_keyboard(_, message.from_user.id)
    await get.edit_text(_["playlist_7"].format(count), reply_markup=keyboard)


# ==========================================
#  Callbacks (تشغيل - إضافة - حذف)
# ==========================================

@app.on_callback_query(filters.regex("play_playlist") & ~BANNED_USERS)
@languageCB
async def play_playlist(client, CallbackQuery, _):
    # استقبال ID المستخدم من البيانات
    user_id = int(CallbackQuery.data.split()[1])
    
    if CallbackQuery.from_user.id != user_id:
        return await CallbackQuery.answer("هذه القائمة ليست لك!", show_alert=True)

    _playlist = await get_playlist_names(user_id)
    
    if not _playlist:
        try:
            return await CallbackQuery.answer(
                _["playlist_3"],
                show_alert=True,
            )
        except Exception:
            return
            
    chat_id = CallbackQuery.message.chat.id
    user_name = CallbackQuery.from_user.first_name
    await CallbackQuery.message.delete()
    
    try:
        await CallbackQuery.answer("جاري التشغيل...")
    except Exception:
        pass
        
    mystic = await CallbackQuery.message.reply_text(_["play_1"])
    result = list(_playlist)
    
    try:
        await stream(
            _,
            mystic,
            user_id,
            result,
            chat_id,
            user_name,
            CallbackQuery.message.chat.id,
            video=False,
            streamtype="playlist",
        )
    except Exception as e:
        await mystic.edit_text(f"خطأ أثناء التشغيل: {e}")
    
    return await mystic.delete()


@app.on_callback_query(filters.regex("add_playlist") & ~BANNED_USERS)
@languageCB
async def add_playlist(client, CallbackQuery, _):
    try:
        callback_data = CallbackQuery.data.strip()
        videoid = callback_data.split(None, 1)[1]
        user_id = CallbackQuery.from_user.id
        
        _check = await get_playlist(user_id, videoid)
        if _check:
            return await CallbackQuery.answer(_["playlist_8"], show_alert=True)
            
        _count = await get_playlist_names(user_id)
        count = len(_count)
        if count == SERVER_PLAYLIST_LIMIT:
            return await CallbackQuery.answer(
                _["playlist_9"].format(SERVER_PLAYLIST_LIMIT),
                show_alert=True,
            )
            
        (
            title,
            duration_min,
            duration_sec,
            thumbnail,
            vidid,
        ) = await YouTube.details(videoid, True)
        
        title = (title[:50]).title()
        plist = {
            "videoid": vidid,
            "title": title,
            "duration": duration_min,
        }
        
        await save_playlist(user_id, videoid, plist)
        return await CallbackQuery.answer(
            _["playlist_10"].format(title[:30]), show_alert=True
        )
        
    except Exception as e:
        return await CallbackQuery.answer(f"Error: {e}", show_alert=True)


@app.on_callback_query(filters.regex("del_playlist") & ~BANNED_USERS)
@languageCB
async def del_plist(client, CallbackQuery, _):
    callback_data = CallbackQuery.data.strip()
    videoid = callback_data.split(None, 1)[1]
    user_id = CallbackQuery.from_user.id
    
    deleted = await delete_playlist(CallbackQuery.from_user.id, videoid)
    if deleted:
        try:
            await CallbackQuery.answer(_["playlist_11"], show_alert=True)
            # تحديث القائمة فوراً بعد الحذف
            _playlist = await get_playlist_names(user_id)
            
            if not _playlist:
                return await CallbackQuery.message.edit_text(_["playlist_3"])
            
            buttons = []
            for vid in _playlist:
                _note = await get_playlist(user_id, vid)
                title = _note["title"]
                buttons.append([InlineKeyboardButton(text=f"{title[:25]} 🗑️", callback_data=f"del_playlist {vid}")])
            
            buttons.append([InlineKeyboardButton(text="• تشغيل الكل •", callback_data=f"play_playlist {user_id}")])
            
            # زر المالك في التحديث
            owner_id = OWNER_ID
            if isinstance(owner_id, list): owner_id = owner_id[0]
            buttons.append([InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", user_id=owner_id)])
            
            buttons.append([InlineKeyboardButton(text="إغلاق", callback_data="close")])
            
            await CallbackQuery.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
            
        except Exception:
            pass
    else:
        try:
            return await CallbackQuery.answer(_["playlist_12"], show_alert=True)
        except Exception:
            return


@app.on_callback_query(filters.regex("delete_whole_playlist") & ~BANNED_USERS)
@languageCB
async def del_whole_playlist(client, CallbackQuery, _):
    _playlist = await get_playlist_names(CallbackQuery.from_user.id)
    for x in _playlist:
        await delete_playlist(CallbackQuery.from_user.id, x)
    return await CallbackQuery.edit_message_text(_["playlist_13"])


@app.on_callback_query(filters.regex("get_playlist_playmode") & ~BANNED_USERS)
@languageCB
async def get_playlist_playmode_(client, CallbackQuery, _):
    try:
        await CallbackQuery.answer()
    except Exception:
        pass
    buttons = get_playlist_markup(_)
    return await CallbackQuery.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex("delete_warning") & ~BANNED_USERS)
@languageCB
async def delete_warning_message(client, CallbackQuery, _):
    try:
        await CallbackQuery.answer()
    except Exception:
        pass
    upl = warning_markup(_)
    return await CallbackQuery.edit_message_text(_["playlist_14"], reply_markup=upl)


@app.on_callback_query(filters.regex("home_play") & ~BANNED_USERS)
@languageCB
async def home_play_(client, CallbackQuery, _):
    try:
        await CallbackQuery.answer()
    except Exception:
        pass
    buttons = botplaylist_markup(_)
    return await CallbackQuery.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex("del_back_playlist") & ~BANNED_USERS)
@languageCB
async def del_back_playlist(client, CallbackQuery, _):
    user_id = CallbackQuery.from_user.id
    _playlist = await get_playlist_names(user_id)
    if _playlist:
        try:
            await CallbackQuery.answer(_["playlist_2"], show_alert=True)
        except Exception:
            pass
    else:
        try:
            return await CallbackQuery.answer(_["playlist_3"], show_alert=True)
        except Exception:
            return
    keyboard, count = await get_keyboard(_, user_id)
    return await CallbackQuery.edit_message_text(
        _["playlist_7"].format(count), reply_markup=keyboard
    )
