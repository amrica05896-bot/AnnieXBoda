# plugins/ai/handlers.py
# Authored By Certified Coders (c) 2026
# AI Handlers - Smart Switching & Failover Integrated

import os
import re
import logging
from typing import Optional, Set

from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from AnnieXMedia import app
from config import OWNER_ID

# استيراد المحرك الذكي (Local Engine)
from .engine import (
    ENGINE,
    ask_ollama_stream,
    clear_user_memory,
    toggle_model,
    LIGHT_MODEL,
    HEAVY_MODEL
)

from .prompts import build_system_prompt

logger = logging.getLogger("AnnieX_AI_Handlers")
logging.basicConfig(level=logging.INFO)

# -------------------------------------------------
# OWNER / SUDO SETUP
# -------------------------------------------------
if isinstance(OWNER_ID, (list, tuple, set)):
    SUDO_USERS = set(OWNER_ID)
else:
    SUDO_USERS = {OWNER_ID}

SUDO_FILTER = filters.user(list(SUDO_USERS))

# -------------------------------------------------
# AI STATE MANAGEMENT
# -------------------------------------------------
class AIState:
    def __init__(self):
        self.permanent_users: Set[int] = set()

AI_STATE = AIState()

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def extract_prompt(text: str) -> str:
    # استخراج السؤال بعد كلمة التفعيل
    trigger = re.match(r"^(ذكاء|يا بوت|بوت|بقولك)(\s+|$)", text or "", re.IGNORECASE)
    if trigger:
        return text[trigger.end():].strip()
    return (text or "").strip()


def should_trigger_ai(message: Message, bot_id: Optional[int]) -> bool:
    if not message.from_user:
        return False

    uid = message.from_user.id
    
    # 1. لو المستخدم مفعل الوضع الدائم
    if uid in AI_STATE.permanent_users:
        return True

    # 2. لو الرسالة تبدأ بكلمة تفعيل
    return bool(re.match(r"^(ذكاء|يا بوت|بوت|بقولك)", message.text or "", re.IGNORECASE))


def owner_only_text() -> str:
    return "هذا الامر مخصص للمالك فقط."

# -------------------------------------------------
# KEYBOARDS
# -------------------------------------------------
def build_control_keyboard() -> InlineKeyboardMarkup:
    # تحديد النص بناءً على الموديل الحالي في المحرك
    if ENGINE.model == LIGHT_MODEL:
        # لو الحالي خفيف (Llama)، الزرار يكون للتبديل للتقيل (DeepSeek)
        current_status = "(Llama 3.3 - سريع)"
        switch_label = "🔄 تفعيل العبقري (DeepSeek R1)"
    else:
        # لو الحالي تقيل (DeepSeek)، الزرار يكون للتبديل للخفيف (Llama)
        current_status = "(DeepSeek R1 - عبقري)"
        switch_label = "⚡ تفعيل السريع (Llama 3.3)"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("اوامر المستخدمين", callback_data="ai_users")],
            [
                InlineKeyboardButton("اوامر المالك", callback_data="ai_owner"),
                InlineKeyboardButton("الاعدادات", callback_data="ai_settings"),
            ],
            [
                InlineKeyboardButton("تشغيل / ايقاف", callback_data="ai_toggle"),
                InlineKeyboardButton("تنظيف الذاكرة", callback_data="ai_clean"),
            ],
            [
                InlineKeyboardButton(switch_label, callback_data="ai_speed"),
                InlineKeyboardButton("اعادة تشغيل", callback_data="ai_restart"),
            ],
            [InlineKeyboardButton("اغلاق", callback_data="ai_close")],
        ]
    )


def build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Llama 3.3 (سريع)", callback_data="ai_light"),
                InlineKeyboardButton("DeepSeek R1 (عبقري)", callback_data="ai_heavy"),
            ],
            [InlineKeyboardButton("رجوع", callback_data="ai_back")],
        ]
    )

# -------------------------------------------------
# CONTROL PANEL COMMAND
# -------------------------------------------------
@app.on_message(filters.regex(r"^(اوامر الذكاء|كيب ذكاء|كيب الذكاء)$") & SUDO_FILTER)
async def ai_control_panel(_, m: Message):
    # تحديد حالة السرعة للعرض
    current_speed = "🚀 سريع (Llama 3.3)" if ENGINE.model == LIGHT_MODEL else "🧠 عبقري (DeepSeek R1)"
    
    text = (
        "**🤖 لوحة تحكم الذكاء الاصطناعي (Pro Engine)**\n\n"
        f"• **الحالة:** {'✅ مفعل' if ENGINE.enabled else '❌ معطل'}\n"
        f"• **الموديل:** `{ENGINE.model}`\n"
        f"• **الوضع:** {current_speed}\n"
        f"• **المتصلين:** `{len(AI_STATE.permanent_users)}`\n"
    )
    await m.reply_text(text, reply_markup=build_control_keyboard())

# -------------------------------------------------
# CALLBACKS HANDLER
# -------------------------------------------------
@app.on_callback_query(filters.regex("^ai_"))
async def ai_callbacks(_, q: CallbackQuery):
    data = q.data
    uid = q.from_user.id

    if data == "ai_users":
        await q.answer(
            "اوامر المستخدم:\n"
            "- ذكاء <سؤال>\n"
            "- ذكاء دائم\n"
            "- كفاية\n"
            "- مسح ذاكرتي",
            show_alert=True,
        )
        return

    if data == "ai_owner":
        if uid not in SUDO_USERS:
            await q.answer(owner_only_text(), show_alert=True)
            return
        await q.answer("لديك صلاحيات كاملة.", show_alert=True)
        return

    if data == "ai_settings":
        if uid not in SUDO_USERS:
            await q.answer(owner_only_text(), show_alert=True)
            return
        await q.message.edit_text(
            "اعدادات الذكاء الاصطناعي:",
            reply_markup=build_settings_keyboard(),
        )
        return

    if data == "ai_speed":
        if uid not in SUDO_USERS:
            await q.answer(owner_only_text(), show_alert=True)
            return
        
        # التبديل الفعلي للموديل في المحرك
        new_model = toggle_model()
        
        # تحديث نص الرسالة
        if new_model == LIGHT_MODEL:
            msg = "🚀 تم التفعيل: Llama 3.3 (السرعة)"
            current_speed = "🚀 سريع (Llama 3.3)"
        else:
            msg = "🧠 تم التفعيل: DeepSeek R1 (العبقرية)"
            current_speed = "🧠 عبقري (DeepSeek R1)"
            
        await q.answer(msg, show_alert=True)
        
        text = (
            "**🤖 لوحة تحكم الذكاء الاصطناعي (Pro Engine)**\n\n"
            f"• **الحالة:** {'✅ مفعل' if ENGINE.enabled else '❌ معطل'}\n"
            f"• **الموديل:** `{ENGINE.model}`\n"
            f"• **الوضع:** {current_speed}\n"
            f"• **المتصلين:** `{len(AI_STATE.permanent_users)}`\n"
        )
        try:
            await q.message.edit_text(text, reply_markup=build_control_keyboard())
        except:
            pass
        return

    if data == "ai_back":
        # إعادة بناء اللوحة الرئيسية
        current_speed = "🚀 سريع (Llama 3.3)" if ENGINE.model == LIGHT_MODEL else "🧠 عبقري (DeepSeek R1)"
        text = (
            "**🤖 لوحة تحكم الذكاء الاصطناعي (Pro Engine)**\n\n"
            f"• **الحالة:** {'✅ مفعل' if ENGINE.enabled else '❌ معطل'}\n"
            f"• **الموديل:** `{ENGINE.model}`\n"
            f"• **الوضع:** {current_speed}\n"
            f"• **المتصلين:** `{len(AI_STATE.permanent_users)}`\n"
        )
        await q.message.edit_text(text, reply_markup=build_control_keyboard())
        return

    if data == "ai_toggle":
        if uid not in SUDO_USERS:
            await q.answer(owner_only_text(), show_alert=True)
            return
        ENGINE.enabled = not ENGINE.enabled
        await q.answer("تم تحديث حالة الذكاء.", show_alert=True)
        
        current_speed = "🚀 سريع (Llama 3.3)" if ENGINE.model == LIGHT_MODEL else "🧠 عبقري (DeepSeek R1)"
        text = (
            "**🤖 لوحة تحكم الذكاء الاصطناعي (Pro Engine)**\n\n"
            f"• **الحالة:** {'✅ مفعل' if ENGINE.enabled else '❌ معطل'}\n"
            f"• **الموديل:** `{ENGINE.model}`\n"
            f"• **الوضع:** {current_speed}\n"
            f"• **المتصلين:** `{len(AI_STATE.permanent_users)}`\n"
        )
        try:
            await q.message.edit_text(text, reply_markup=build_control_keyboard())
        except:
            pass
        return

    if data == "ai_clean":
        if uid not in SUDO_USERS:
            await q.answer(owner_only_text(), show_alert=True)
            return
        AI_STATE.permanent_users.clear()
        await q.answer("تم تنظيف الذاكرة وقائمة المتصلين.", show_alert=True)
        return

    if data == "ai_restart":
        if uid not in SUDO_USERS:
            await q.answer(owner_only_text(), show_alert=True)
            return
        await q.answer("جاري إعادة التشغيل...", show_alert=True)
        os._exit(0)

    if data == "ai_close":
        await q.message.delete()

# -------------------------------------------------
# USER COMMANDS
# -------------------------------------------------
@app.on_message(filters.regex(r"^(ذكاء دائم)$") & ~filters.bot)
async def enable_permanent(_, m: Message):
    AI_STATE.permanent_users.add(m.from_user.id)
    await m.reply_text("**تم تفعيل وضع الذكاء الدائم.**\nالآن يمكنك التحدث مع البوت مباشرة بدون مقدمات.")

@app.on_message(filters.regex(r"^(كفاية|خروج)$") & ~filters.bot)
async def disable_permanent(_, m: Message):
    AI_STATE.permanent_users.discard(m.from_user.id)
    await m.reply_text("**تم ايقاف الذكاء الدائم.**")

@app.on_message(filters.regex(r"^(مسح ذاكرتي)$") & ~filters.bot)
async def clear_user(_, m: Message):
    clear_user_memory(m.from_user.id)
    await m.reply_text("**تم مسح ذاكرتك.**\nبدأنا صفحة جديدة.")

# -------------------------------------------------
# MAIN AI PROCESSING
# -------------------------------------------------
@app.on_message(filters.text & ~filters.bot, group=60)
async def ai_handler(client, m: Message):
    # التحقق من أن الذكاء مفعل (يسمح للمطورين بالتجاوز)
    if not ENGINE.enabled and m.from_user.id not in SUDO_USERS:
        return

    try:
        bot_id = (client.me or await client.get_me()).id
    except Exception:
        bot_id = None

    # هل يجب الرد؟
    if not should_trigger_ai(m, bot_id):
        return

    prompt = extract_prompt(m.text)
    if not prompt:
        return

    system_prompt = build_system_prompt("عام")

    # رسالة الانتظار
    wait_msg = await m.reply_text("⏳")

    # دالة التحديث المباشر (Streaming)
    async def on_update(text: str):
        try:
            # تحديث الرسالة كلما وصل جزء جديد من النص
            await wait_msg.edit(text[:4000]) # حدود تليجرام
        except Exception:
            pass

    # استدعاء المحرك
    reply = await ask_ollama_stream(
        user_id=m.from_user.id,
        prompt=prompt,
        system_prompt=system_prompt,
        on_update=on_update,
    )

    # التأكد من أن الرسالة النهائية تم عرضها
    if reply and reply != wait_msg.text:
        try:
            await wait_msg.edit(reply[:4000])
        except:
            pass
