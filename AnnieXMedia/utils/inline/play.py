# Authored By Certified Coders © 2026
# Module: Advanced Inline Keyboard System (Language Support Enabled 🌍)
# Features: Python 3.13 Compatible, Modern Progress Bar (▰▱), Multi-Language Support

import math
from typing import List, Union
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from AnnieXMedia.utils.formatters import time_to_seconds
from config import SUPPORT_CHAT, SUPPORT_CHANNEL

# --- [ 1. The Engine: High-Precision Progress Bar ] ---
def get_progress_bar(percentage: float) -> str:
    """
    Generates a modern progress bar using ▰ and ▱.
    """
    p = min(max(percentage, 0), 100)
    length = 10 
    filled_length = int(length * p // 100)
    return "▰" * filled_length + "▱" * (length - filled_length)

# --- [ 2. The Skeleton: Reusable Button Components ] ---
def _get_controls(chat_id: Union[int, str]) -> List[InlineKeyboardButton]:
    """Returns the standard playback control buttons (Icons are universal)."""
    return [
        InlineKeyboardButton(text="▷", callback_data=f"ADMIN Resume|{chat_id}"),
        InlineKeyboardButton(text="II", callback_data=f"ADMIN Pause|{chat_id}"),
        InlineKeyboardButton(text="↻", callback_data=f"ADMIN Replay|{chat_id}"),
        InlineKeyboardButton(text="‣‣I", callback_data=f"ADMIN Skip|{chat_id}"),
        InlineKeyboardButton(text="▢", callback_data=f"ADMIN Stop|{chat_id}"),
    ]

def _get_footer(_) -> List[List[InlineKeyboardButton]]:
    """Returns the footer buttons using Language File for text."""
    return [
        [
            InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
            InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
        ],
        [
            # ✅ هنا الاعتماد على ملف اللغة
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
        ],
    ]

# --- [ 3. The Interface: Main Markups ] ---

def stream_markup_timer(_, chat_id: int, played: str, dur: str) -> InlineKeyboardMarkup:
    """
    Dynamic Player UI with Live Timer.
    """
    played_sec = time_to_seconds(played)
    duration_sec = time_to_seconds(dur)
    
    percentage = (played_sec / duration_sec) * 100 if duration_sec > 0 else 0
    bar = get_progress_bar(percentage)

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{played} {bar} {dur}",
                callback_data="GetTimer"
            )
        ],
        _get_controls(chat_id)
    ]
    buttons.extend(_get_footer(_)) # Pass lang dict
    
    return InlineKeyboardMarkup(buttons)

def stream_markup(_, chat_id: int) -> List[List[InlineKeyboardButton]]:
    """
    Standard markup for streams.
    """
    buttons = [_get_controls(chat_id)]
    buttons.extend(_get_footer(_))
    return buttons

def telegram_markup(_, chat_id: int) -> List[List[InlineKeyboardButton]]:
    """Markup for Telegram Audio Files."""
    buttons = [_get_controls(chat_id)]
    buttons.extend(_get_footer(_))
    return buttons

def aq_markup(_, chat_id: int) -> List[List[InlineKeyboardButton]]:
    """Markup for 'Added to Queue' messages."""
    buttons = [_get_controls(chat_id)]
    buttons.extend(_get_footer(_))
    return buttons

def close_markup(_) -> List[List[InlineKeyboardButton]]:
    """Simple Close Button."""
    return [[InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")]]

# --- [ 4. Advanced Menus (Playlist / Slider) ] ---

def playlist_markup(_, videoid, user_id, ptype, channel, fplay) -> List[List[InlineKeyboardButton]]:
    return [
        [
            # ✅ استخدام مفاتيح اللغة (P_B_1 للصوت، P_B_2 للفيديو)
            InlineKeyboardButton(
                text=_["P_B_1"], 
                callback_data=f"AnniePlaylists {videoid}|{user_id}|{ptype}|a|{channel}|{fplay}"
            ),
            InlineKeyboardButton(
                text=_["P_B_2"],
                callback_data=f"AnniePlaylists {videoid}|{user_id}|{ptype}|v|{channel}|{fplay}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {videoid}|{user_id}"
            ),
        ],
    ]

def track_markup(_, videoid, user_id, channel, fplay) -> List[List[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=_["P_B_1"],
                callback_data=f"MusicStream {videoid}|{user_id}|a|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["P_B_2"],
                callback_data=f"MusicStream {videoid}|{user_id}|v|{channel}|{fplay}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {videoid}|{user_id}"
            )
        ],
    ]

def slider_markup(_, videoid, user_id, query, query_type, channel, fplay) -> List[List[InlineKeyboardButton]]:
    query = f"{query[:20]}"
    return [
        [
            InlineKeyboardButton(
                text=_["P_B_1"],
                callback_data=f"MusicStream {videoid}|{user_id}|a|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["P_B_2"],
                callback_data=f"MusicStream {videoid}|{user_id}|v|{channel}|{fplay}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="❮",
                callback_data=f"slider B|{query_type}|{query}|{user_id}|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {query}|{user_id}",
            ),
            InlineKeyboardButton(
                text="❯",
                callback_data=f"slider F|{query_type}|{query}|{user_id}|{channel}|{fplay}",
            ),
        ],
    ]

def livestream_markup(_, videoid, user_id, mode, channel, fplay) -> List[List[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=_["P_B_3"], # ✅ مفتاح زرار اللايف
                callback_data=f"LiveStream {videoid}|{user_id}|{mode}|{channel}|{fplay}",
            )
        ],
        [
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {videoid}|{user_id}"
            )
        ],
    ]
