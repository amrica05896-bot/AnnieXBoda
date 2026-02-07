# AnnieXMedia/utils/inline/custom.py
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ضفنا الـ (_) هنا عشان يتوافق مع استدعاء ملف stream.py
def custom_markup(_, chat_id, vidid):
    buttons = [
        [
            InlineKeyboardButton(text="▷", callback_data=f"stream_admin Resume|{chat_id}"),
            InlineKeyboardButton(text="II", callback_data=f"stream_admin Pause|{chat_id}"),
            InlineKeyboardButton(text="↻", callback_data=f"stream_admin Replay|{chat_id}"),
            InlineKeyboardButton(text="▢", callback_data=f"song_stop_custom|{chat_id}|{vidid}"),
        ],
        [
            InlineKeyboardButton(text="إغلاق", callback_data="close")
        ]
    ]
    return InlineKeyboardMarkup(buttons)
