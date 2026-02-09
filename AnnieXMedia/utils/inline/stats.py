# Authored By Certified Coders © 2026
# Module: Stats Inline Keyboard (Dev Boda Edition)

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

class StatsCallbacks:
    SHOW_OVERVIEW = "stats:overview"
    SHOW_BOT_STATS = "stats:bot"
    BACK = "stats:back"
    CLOSE = "stats:close"

def build_stats_keyboard(_, is_sudo: bool) -> InlineKeyboardMarkup:
    # 1. الصفوف الأساسية (حسب رتبة المستخدم)
    if is_sudo:
        main_row = [
            InlineKeyboardButton(
                text=_["SA_B_2"],  # 🤖 System Stats
                callback_data=StatsCallbacks.SHOW_BOT_STATS,
            ),
            InlineKeyboardButton(
                text=_["SA_B_3"],  # 📊 Overall Stats
                callback_data=StatsCallbacks.SHOW_OVERVIEW,
            ),
        ]
    else:
        main_row = [
            InlineKeyboardButton(
                text=_["SA_B_1"],  # 📊 Top Stats
                callback_data=StatsCallbacks.SHOW_OVERVIEW,
            )
        ]

    rows = [main_row]

    # 2. إضافة أزرار القناة والمطور المزخرفة (Boda Brand)
    rows.append([
        InlineKeyboardButton(text="ᏟᎻᎪᏁᏁᎬᏞ", url="https://t.me/SourceBoda"),
        InlineKeyboardButton(text="ᎾᎳᏁᎬᏒ", url="https://t.me/S_G0C7"),
    ])

    # 3. زر الإغلاق
    rows.append([
        InlineKeyboardButton(
            text=_["CLOSE_BUTTON"],
            callback_data=StatsCallbacks.CLOSE,
        )
    ])

    return InlineKeyboardMarkup(rows)

def build_back_keyboard(_) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_["BACK_BUTTON"],
                callback_data=StatsCallbacks.BACK,
            ),
            InlineKeyboardButton(
                text=_["CLOSE_BUTTON"],
                callback_data=StatsCallbacks.CLOSE,
            ),
        ]
    ]
    return InlineKeyboardMarkup(rows)
