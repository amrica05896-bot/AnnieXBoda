# Authored By Certified Coders © 2026
# Module: Volume Control
# Description: Controls stream volume (0-200%) via PyTgCalls v3.0

from pyrogram import filters
from pyrogram.types import Message

from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.utils.database import get_lang
from AnnieXMedia.utils.decorators import AdminRightsCheck
from AnnieXMedia.utils.inline import close_markup
from strings import get_string

# قمنا بإضافة كلمات "علي" و "وطي" ومشتقاتها
COMMANDS = [
    "volume", "vol", "changevolume", 
    "الصوت", "صوت", "مستوى الصوت",
    "علي", "عالي", "ارفع",
    "وطي", "واطي", "نزل", "خفض"
]

@app.on_message(
    filters.command(COMMANDS, prefixes=["/", "!", "%", ",", "", ".", "@", "#"])
    & filters.group
)
@AdminRightsCheck
async def change_volume_command(cli, message: Message, _, chat_id):
    lang = await get_lang(chat_id)
    _strings = get_string(lang)

    # التحقق من وجود قيمة (مثال: علي 150)
    if len(message.command) < 2:
        return await message.reply_text(
            _strings["admin_28"], reply_markup=close_markup(_strings)
        )

    query = message.text.split(None, 1)[1].strip()

    if not query.isnumeric():
        return await message.reply_text(
            _strings["admin_29"], reply_markup=close_markup(_strings)
        )

    volume = int(query)

    # قيود الأمان (0 - 200%)
    if volume > 200:
        volume = 200
        await message.reply_text(
            " تم ضبط الصوت على الحد الأقصى (200%) تلقائياً.",
            reply_markup=close_markup(_strings)
        )
    elif volume < 0:
        volume = 0

    try:
        await StreamController.change_volume_call(chat_id, volume)
        
        # رسالة تأكيد لطيفة
        await message.reply_text(
            _strings["admin_30"].format(volume),
            reply_markup=close_markup(_strings)
        )
    except Exception as e:
        await message.reply_text(f" حدث خطأ: {e}")
