# Authored By Certified Coders © 2026
# RADIO SYSTEM - AnnieXMedia SOURCE
# High Stability Stream Logic | No-Prefix Commands
# Fixed: TypeError in put_queue by setting video=False explicitly

import asyncio
from pyrogram import filters, enums
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    InviteRequestSent,
    UserNotParticipant,
)
from pyrogram.types import Message

from config import BANNED_USERS
from strings import get_string
from AnnieXMedia import app
from AnnieXMedia.misc import SUDOERS
from AnnieXMedia.utils.database import (
    get_assistant,
    get_cmode,
    get_lang,
)
from AnnieXMedia.utils.stream.stream import stream

# ==========================
# قائمة المحطات الإذاعية
# ==========================

RADIO_STATIONS = {
    "القرآن الكريم": "https://stream.radiojar.com/8s5u5tpdtwzuv",
    "نجوم اف ام": "https://ssl.mz-audiostreaming.com/nogoumfm",
    "نايل اف ام": "https://ssl.mz-audiostreaming.com/nilefm",
    "نغم اف ام": "https://ssl.mz-audiostreaming.com/naghamfm",
    "ميجا اف ام": "https://ssl.mz-audiostreaming.com/megafm",
    "الراديو 9090": "https://9090streaming.mobtada.com/9090FMEGYPT",
    "راديو مصر": "https://live.radiomasr.net/RADIOMASR",
    "محطة مصر": "https://s3.radio.co/s95f66299d/listen",
    "شعبى اف ام": "https://radio.masr.me/sha3byfm",
    "اون سبورت اف ام": "https://stream.radiojar.com/4884313205tv",
}

def normalize_text(text):
    """توحيد النص العربي للبحث الذكي"""
    if not text:
        return ""
    return (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
        .strip()
    )

STATIONS_LIST = "\n".join([f"• {name}" for name in sorted(RADIO_STATIONS.keys())])

# ==========================
# معالج أمر الراديو
# ==========================

@app.on_message(
    filters.regex(r"^(راديو|radio|راديو القنوات|cradio)(.*)$")
    & filters.group
    & ~BANNED_USERS
)
async def radio_handler(client, message: Message):
    # 1. التحقق من صلاحيات المشرفين
    user_id = message.from_user.id
    if user_id not in SUDOERS:
        try:
            member = await app.get_chat_member(message.chat.id, user_id)
            if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return await message.reply_text("هذا الامر مخصص للمشرفين فقط.")
        except Exception:
            return

    # 2. استخراج اسم المحطة
    cmd_text = message.text or message.caption
    input_station = ""
    
    # فصل الكلمة الأولى (الأمر) عن اسم المحطة
    parts = cmd_text.split(None, 1)
    if len(parts) < 2:
        return await message.reply_text(
            f"يرجى اختيار محطة للتشغيل:\\n\\n{STATIONS_LIST}\\n\\nمثال: راديو القرآن الكريم"
        )
    
    input_station = normalize_text(parts[1])
    target_url = None
    target_name = None

    # البحث الذكي عن المحطة
    for name, url in RADIO_STATIONS.items():
        if normalize_text(name) == input_station:
            target_url = url
            target_name = name
            break

    if not target_url:
        return await message.reply_text(f"لم يتم العثور على هذه المحطة.\\n\\nالمحطات المتاحة:\\n{STATIONS_LIST}")

    # 3. تجهيز المساعد
    status_msg = await message.reply_text("جاري تجهيز البث المباشر...")
    
    try:
        assistant = await get_assistant(message.chat.id)
        try:
            await app.get_chat_member(message.chat.id, assistant.id)
        except UserNotParticipant:
            if message.chat.username:
                invite_link = message.chat.username
            else:
                invite_link = await client.export_chat_invite_link(message.chat.id)
            
            try:
                await assistant.join_chat(invite_link)
            except InviteRequestSent:
                await app.approve_chat_join_request(message.chat.id, assistant.id)
            except Exception as e:
                return await status_msg.edit(f"فشل انضمام المساعد: {e}")

    except Exception as e:
        return await status_msg.edit(f"خطأ في جلب المساعد: {e}")

    # 4. بدء البث
    language = await get_lang(message.chat.id)
    _ = get_string(language)
    
    # التحقق من وضع القنوات (cradio)
    if parts[0].lower().startswith("c") or parts[0] == "راديو القنوات":
        chat_id = await get_cmode(message.chat.id)
        if not chat_id:
            return await status_msg.edit("يرجى ربط قناة أولاً لاستخدام بث القنوات.")
    else:
        chat_id = message.chat.id

    try:
        # 🔥 التصحيح هنا: video=False بدلاً من None
        await stream(
            _,
            status_msg,
            user_id,
            target_url,
            chat_id,
            message.from_user.first_name,
            message.chat.id,
            video=False, # Must be boolean for new Stream Engine
            streamtype="index",
        )
    except Exception as e:
        await status_msg.edit(f"حدث خطأ أثناء تشغيل الراديو: {e}")

    await status_msg.delete()

# معلومات الموديول لسورسك
__MODULE__ = "الراديو"
__HELP__ = f"راديو [اسم المحطة]\\n\\nالمحطات المتاحة:\\n{STATIONS_LIST}"
