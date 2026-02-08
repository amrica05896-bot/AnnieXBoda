# Authored By Certified Coders 2026
# Module: XO Admin Control Panel (Clean Version)

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from AnnieXMedia import app
from AnnieXMedia.misc import SUDOERS
import config

if not hasattr(config, "XO_ENABLED"): config.XO_ENABLED = True
if not hasattr(config, "XO_CHEAT"): config.XO_CHEAT = False 

@app.on_message(filters.command(["كيب اكس او", "تعطيل اكس او", "تفعيل اكس او"], prefixes=["", "/", "!"]) & SUDOERS)
async def xo_admin_panel(_, message):
    await send_control_panel(message)

async def send_control_panel(message):
    st = "مفعل" if config.XO_ENABLED else "معطل"
    ch = "نشط (سهل)" if config.XO_CHEAT else "غير نشط (ذكي)"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"حالة اللعبة : {st}", callback_data="xo_adm_toggle")],
        [InlineKeyboardButton(f"وضع الغش : {ch}", callback_data="xo_adm_cheat")],
        [InlineKeyboardButton("اغلاق اللوحة", callback_data="xo_adm_close")]
    ])

    txt = (
        "**لوحة تحكم نظام XO**\n\n"
        "**الحالة الحالية:**\n"
        f"• اللعبة: **{st}**\n"
        f"• وضع الغش: **{ch}**\n\n"
        "**ملاحظة:**\n"
        "- وضع الغش: يجعل البوت يلعب دائماً المستوى السهل حتى لو اختار العضو الصعب."
    )

    if isinstance(message, CallbackQuery):
        try: await message.edit_message_text(txt, reply_markup=kb)
        except: pass
    else:
        await message.reply_text(txt, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^xo_adm_") & SUDOERS)
async def xo_admin_cb(_, query: CallbackQuery):
    data = query.data
    if data == "xo_adm_toggle":
        config.XO_ENABLED = not config.XO_ENABLED
    elif data == "xo_adm_cheat":
        config.XO_CHEAT = not config.XO_CHEAT
    elif data == "xo_adm_close":
        return await query.message.delete()
    
    await send_control_panel(query)
