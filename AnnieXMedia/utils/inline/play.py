# Authored By Certified Coders © 2026
# Module: Inline Keyboard Markups (Full & Fixed)
# Features: Dynamic Progress Bar, Custom Boda Buttons, Fixed Missing Functions

import math
import time
from pyrogram.types import InlineKeyboardButton
from AnnieXMedia.utils.formatters import time_to_seconds

# Cache to prevent FloodWait errors from Telegram
LAST_UPDATE_TIME = {}

def get_progress_bar(percentage):
    """
    Generates a high-precision, aesthetic progress bar.
    Style: —————◉—————
    """
    p = min(max(percentage, 0), 100)
    length = 12 
    filled_length = int(length * p // 100)
    
    if filled_length == 0:
        bar = "◉" + "—" * (length - 1)
    elif filled_length >= length:
        bar = "—" * (length - 1) + "◉"
    else:
        bar = "—" * filled_length + "◉" + "—" * (length - filled_length - 1)
    
    return bar

def should_update_progress(chat_id):
    now = time.time()
    last = LAST_UPDATE_TIME.get(chat_id, 0)
    if now - last >= 8:
        LAST_UPDATE_TIME[chat_id] = now
        return True
    return False

# --- Unified Control Buttons ---
def control_buttons(chat_id):
    return [
        [
            InlineKeyboardButton(text="▷", callback_data=f"ADMIN Resume|{chat_id}"),
            InlineKeyboardButton(text="II", callback_data=f"ADMIN Pause|{chat_id}"),
            InlineKeyboardButton(text="↻", callback_data=f"ADMIN Replay|{chat_id}"),
            InlineKeyboardButton(text="‣‣I", callback_data=f"ADMIN Skip|{chat_id}"),
            InlineKeyboardButton(text="▢", callback_data=f"ADMIN Stop|{chat_id}"),
        ]
    ]

# --- Markup Generators ---

def stream_markup_timer(_, chat_id, played, dur):
    """
    The Main Player UI with Timer and Progress Bar.
    """
    if not should_update_progress(chat_id):
        return None

    played_sec = time_to_seconds(played)
    duration_sec = time_to_seconds(dur)
    
    if duration_sec == 0:
        percentage = 0
    else:
        percentage = (played_sec / duration_sec) * 100

    bar = get_progress_bar(percentage)

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{played} {bar} {dur}",
                callback_data="GetTimer"
            )
        ]
    ]
    # 1. أزرار التحكم
    buttons.extend(control_buttons(chat_id))
    
    # 2. ✅ الأزرار المزخرفة
    buttons.append([
        InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
        InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
    ])
    
    # 3. زر الإغلاق
    buttons.append([
        InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
    ])
    return buttons

def stream_markup(_, chat_id):
    """
    Fallback markup for live streams.
    """
    buttons = control_buttons(chat_id)
    
    buttons.append([
        InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
        InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
    ])
    
    buttons.append([
        InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
    ])
    return buttons

def telegram_markup(_, chat_id):
    """
    Markup for Telegram Audio Files.
    """
    buttons = control_buttons(chat_id)
    
    buttons.append([
        InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
        InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
    ])
    
    buttons.append([
        InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
    ])
    return buttons

# --- ✅ Missing Functions Added Below (aq_markup, close_markup) ---

def aq_markup(_, chat_id):
    """
    Markup for 'Added to Queue' messages.
    """
    buttons = [
        [
            InlineKeyboardButton(text="▷", callback_data=f"ADMIN Resume|{chat_id}"),
            InlineKeyboardButton(text="II", callback_data=f"ADMIN Pause|{chat_id}"),
            InlineKeyboardButton(text="‣‣I", callback_data=f"ADMIN Skip|{chat_id}"),
            InlineKeyboardButton(text="▢", callback_data=f"ADMIN Stop|{chat_id}"),
        ],
        [
            InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
            InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
        ],
        [
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
        ]
    ]
    return buttons

def close_markup(_):
    """
    Simple Close Button.
    """
    return [
        [
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
        ]
    ]

# --- Selection & Menu Markups ---

def playlist_markup(_, videoid, user_id, ptype, channel, fplay):
    return [
        [
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

def track_markup(_, videoid, user_id, channel, fplay):
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

def slider_markup(_, videoid, user_id, query, query_type, channel, fplay):
    short_query = query[:20]
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
                text="◁",
                callback_data=f"slider B|{query_type}|{short_query}|{user_id}|{channel}|{fplay}",
            ),
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=f"forceclose {short_query}|{user_id}",
            ),
            InlineKeyboardButton(
                text="▷",
                callback_data=f"slider F|{query_type}|{short_query}|{user_id}|{channel}|{fplay}",
            ),
        ],
    ]

def livestream_markup(_, videoid, user_id, mode, channel, fplay):
    return [
        [
            InlineKeyboardButton(
                text=_["P_B_3"],
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
