# Authored By Certified Coders © 2026
# Module: Advanced Error Handling (Boda Edition)
# Features: Smart Logging, Auto-Pastebin, Custom Buttons

import sys
import traceback
import os
from functools import wraps
from datetime import datetime

import aiofiles
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden

from AnnieXMedia import app
from config import LOGGER_ID, DEBUG_IGNORE_LOG, SUPPORT_CHAT
from AnnieXMedia.utils.exceptions import is_ignored_error
from AnnieXMedia.utils.pastebin import ANNIEBIN

# Log file for ignored errors
DEBUG_LOG_FILE = "ignored_errors.log"

# --- Buttons for Error Logs ---
def error_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
            InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
        ],
        [
            InlineKeyboardButton(text="• sᴜᴘᴘᴏʀᴛ •", url=SUPPORT_CHAT),
        ]
    ])

# --- Helper Functions ---

async def send_large_error(text: str, caption: str, filename: str):
    """Fallback: Uploads text as file if too long or Pastebin fails."""
    try:
        paste_url = await ANNIEBIN(text)
        if paste_url:
            await app.send_message(
                LOGGER_ID,
                f"{caption}\n\n🔗 <b>Pastebin:</b> {paste_url}",
                reply_markup=error_buttons(),
                disable_web_page_preview=True
            )
            return
    except Exception:
        pass

    # Create local file
    path = f"{filename}.txt"
    async with aiofiles.open(path, "w") as f:
        await f.write(text)
    
    await app.send_document(
        LOGGER_ID,
        path,
        caption=f"{caption[:1000]}...\n\n❌ <b>Log File Attached</b>",
        reply_markup=error_buttons()
    )
    if os.path.exists(path):
        os.remove(path)

def format_traceback(err, tb, label: str, extras: dict = None) -> str:
    exc_type = type(err).__name__
    
    # Header
    parts = [
        f"<b>🚨 AnnieXMedia System Alert</b>",
        f"<b>⚠️ Error:</b> <code>{exc_type}</code>",
        f"<b>📍 Source:</b> <code>{label}</code>"
    ]
    
    # Extra Info (User, Chat, Command)
    if extras:
        for k, v in extras.items():
            parts.append(f"<b>▪️ {k}:</b> {v}")
            
    # Traceback (Shortened for caption)
    parts.append(f"\n<b>Traceback:</b>\n<pre language='python'>{tb[-1000:] if len(tb) > 1000 else tb}</pre>")
    
    return "\n".join(parts)

async def handle_trace(err, tb, label, filename, extras=None):
    if is_ignored_error(err):
        await log_ignored_error(err, tb, label, extras)
        return

    full_caption = format_traceback(err, tb, label, extras)
    
    if len(full_caption) > 4000:
        await send_large_error(tb, full_caption.split("\nTraceback:")[0], filename)
    else:
        await app.send_message(
            LOGGER_ID,
            full_caption,
            reply_markup=error_buttons(),
            disable_web_page_preview=True
        )

async def log_ignored_error(err, tb, label, extras=None):
    if not DEBUG_IGNORE_LOG:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"\n--- Ignored Error | {label} @ {timestamp} ---",
        f"Type: {type(err).__name__}",
        *(f"{key}: {val}" for key, val in (extras or {}).items()),
        "Traceback:",
        tb.strip(),
        "------------------------------------------\n"
    ]
    async with aiofiles.open(DEBUG_LOG_FILE, "a") as log:
        await log.write("\n".join(lines))

# ========== Decorators (The Core) ==========

def capture_err(func):
    """Decorator for Command Handlers"""
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except ChatWriteForbidden:
            # Leave chat if we can't write
            try: await app.leave_chat(message.chat.id)
            except: pass
        except Exception as err:
            tb = "".join(traceback.format_exception(*sys.exc_info()))
            extras = {
                "User": message.from_user.mention if message.from_user else "Unknown",
                "Chat": f"{message.chat.title} (`{message.chat.id}`)",
                "Command": message.text or "Media/Unknown"
            }
            filename = f"error_cmd_{message.chat.id}_{datetime.now().strftime('%H%M%S')}"
            await handle_trace(err, tb, "Command Handler", filename, extras)
    return wrapper

def capture_callback_err(func):
    """Decorator for Callback Queries"""
    @wraps(func)
    async def wrapper(client, callback_query, *args, **kwargs):
        try:
            return await func(client, callback_query, *args, **kwargs)
        except Exception as err:
            tb = "".join(traceback.format_exception(*sys.exc_info()))
            extras = {
                "User": callback_query.from_user.mention,
                "Chat": f"{callback_query.message.chat.title} (`{callback_query.message.chat.id}`)",
                "Data": callback_query.data
            }
            filename = f"error_cb_{callback_query.message.chat.id}_{datetime.now().strftime('%H%M%S')}"
            await handle_trace(err, tb, "Callback Handler", filename, extras)
    return wrapper

def capture_internal_err(func):
    """Decorator for Internal Functions"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as err:
            tb = "".join(traceback.format_exception(*sys.exc_info()))
            extras = {"Function": func.__name__}
            filename = f"error_internal_{func.__name__}_{datetime.now().strftime('%H%M%S')}"
            await handle_trace(err, tb, "Internal Core", filename, extras)
    return wrapper
