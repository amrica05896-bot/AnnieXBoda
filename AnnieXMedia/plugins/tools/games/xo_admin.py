# Authored By Certified Coders 2026
# Module: XO Admin (Strict MVC Pattern)

from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from AnnieXMedia import app
from AnnieXMedia.misc import SUDOERS
import config

# تهيئة المتغيرات العامة
if not hasattr(config, "XO_ENABLED"): config.XO_ENABLED = True
if not hasattr(config, "XO_CHEAT"): config.XO_CHEAT = False 

class AdminView:
    """مسؤول العرض فقط (View)"""
    @staticmethod
    def render_panel():
        state = "مفعل" if config.XO_ENABLED else "معطل"
        cheat = "مفعل" if config.XO_CHEAT else "معطل"
        
        text = (
            "**إعدادات النظام**\n\n"
            f"• الحالة: **{state}**\n"
            f"• الغش: **{cheat}**"
        )
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تغيير الحالة", callback_data="xo_adm_toggle")],
            [InlineKeyboardButton("تغيير الغش", callback_data="xo_adm_cheat")],
            [InlineKeyboardButton("إغلاق", callback_data="xo_adm_close")]
        ])
        return text, kb

@app.on_message(filters.command(["كيب اكس او", "تعطيل اكس او", "تفعيل اكس او"], prefixes=["", "/", "!"]) & SUDOERS)
async def admin_entry(_, m: Message):
    txt, kb = AdminView.render_panel()
    await m.reply_text(txt, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^xo_adm_") & SUDOERS)
async def admin_controller(_, cb: CallbackQuery):
    command = cb.data.split("_")[-1]
    
    # Controller Logic
    if command == "toggle": config.XO_ENABLED = not config.XO_ENABLED
    elif command == "cheat": config.XO_CHEAT = not config.XO_CHEAT
    elif command == "close": return await cb.message.delete()
    
    # Update View
    txt, kb = AdminView.render_panel()
    await cb.edit_message_text(txt, reply_markup=kb)
