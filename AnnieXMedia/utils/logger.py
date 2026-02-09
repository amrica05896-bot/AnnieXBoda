# Authored By Certified Coders © 2026
# Module: Logger (Clean Text Edition - No Emojis)

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from AnnieXMedia import app
from AnnieXMedia.utils.database import is_on_off
from config import LOGGER_ID

async def play_logs(message, streamtype, query: str = None):
    if await is_on_off(2):
        if not query:
            if message.text:
                try:
                    query = message.text.split(None, 1)[1]
                except:
                    query = "Direct Link"
            else:
                query = "File"

        # تصميم نصي بسيط واحترافي (Terminal Style)
        logger_text = f"""
<b>AnnieXMedia Play Log</b>

<b>Chat:</b> {message.chat.title}
<b>Chat ID:</b> <code>{message.chat.id}</code>
<b>Link:</b> @{message.chat.username if message.chat.username else "Private"}

<b>User:</b> {message.from_user.mention}
<b>User ID:</b> <code>{message.from_user.id}</code>
<b>User Link:</b> @{message.from_user.username if message.from_user.username else "None"}

<b>Query:</b> {query}
<b>Stream Type:</b> {streamtype}
"""
        
        buttons = []
        
        if message.chat.username:
            buttons.append([
                InlineKeyboardButton("View Group", url=f"https://t.me/{message.chat.username}")
            ])
        
        # الأزرار المزخرفة كما طلبت
        buttons.append([
            InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
            InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
        ])

        if message.chat.id != LOGGER_ID:
            try:
                await app.send_message(
                    chat_id=LOGGER_ID,
                    text=logger_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    disable_web_page_preview=True,
                )
            except Exception:
                pass
        return
