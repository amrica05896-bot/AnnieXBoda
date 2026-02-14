# plugins/ai/handlers.py
# Authored By Certified Coders (c) 2026
# AI Handler System - Enterprise Edition
# Features: Timeouts, Scope Isolation, Media Transformation, No Emojis.

import os
import re
import logging
import asyncio
from typing import Dict, Optional, Union, Set

# Pyrogram & Pyromod
from pyrogram import filters, Client
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatAction
)
import pyromod.listen  # تفعيل خاصية الانتظار

# Project Imports
from AnnieXMedia import app
from config import OWNER_ID

# Engine Import
from .engine import (
    ask_ollama_stream,
    clear_user_memory,
    get_engine_status,
    set_engine_state
)

# Media Engine Import
from .media_engine import process_media

# ------------------------------------------------------------------
# CONFIGURATION & LOGGING
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_AI_Handlers")
logger.setLevel(logging.INFO)

# إعداد المطورين
if isinstance(OWNER_ID, (list, tuple, set)):
    SUDO_USERS = set(OWNER_ID)
else:
    SUDO_USERS = {OWNER_ID}

SUDO_FILTER = filters.user(list(SUDO_USERS))

# ------------------------------------------------------------------
# SESSION MANAGEMENT CLASS
# ------------------------------------------------------------------
class SessionManager:
    """
    يدير جلسات المستخدمين، التوقيت، ونطاق الشات.
    """
    def __init__(self):
        # الهيكل: {user_id: {"chat_id": int, "task": asyncio.Task}}
        self._sessions: Dict[int, Dict[str, Union[int, asyncio.Task]]] = {}
        self._lock = asyncio.Lock()

    async def start_session(self, client: Client, user_id: int, chat_id: int):
        """يبدأ جلسة جديدة أو يجدد جلسة حالية"""
        async with self._lock:
            # إلغاء أي مؤقت سابق
            if user_id in self._sessions:
                old_task = self._sessions[user_id].get("task")
                if old_task and not old_task.done():
                    old_task.cancel()

            # بدء مؤقت جديد
            task = asyncio.create_task(self._inactivity_monitor(client, user_id, chat_id))
            self._sessions[user_id] = {
                "chat_id": chat_id,
                "task": task
            }

    async def end_session(self, user_id: int):
        """إنهاء الجلسة يدوياً"""
        async with self._lock:
            if user_id in self._sessions:
                task = self._sessions[user_id].get("task")
                if task and not task.done():
                    task.cancel()
                del self._sessions[user_id]

    def is_active(self, user_id: int, chat_id: int) -> bool:
        """هل المستخدم نشط في هذا الشات بالتحديد؟"""
        if user_id not in self._sessions:
            return False
        return self._sessions[user_id]["chat_id"] == chat_id

    async def _inactivity_monitor(self, client: Client, user_id: int, chat_id: int):
        """مراقب الخمول: ينتظر 60 ثانية ثم يغلق الجلسة"""
        try:
            await asyncio.sleep(60)
            
            # إذا وصلنا هنا، يعني الوقت انتهى
            async with self._lock:
                if user_id in self._sessions:
                    del self._sessions[user_id]
            
            # إرسال تنبيه
            try:
                await client.send_message(chat_id, "تم انهاء الذكاء الدائم لعدم وجود رد.")
            except Exception as e:
                logger.warning(f"Failed to send timeout message: {e}")

        except asyncio.CancelledError:
            # تم إلغاء المهمة (المستخدم أرسل رسالة جديدة)
            pass

# تهيئة مدير الجلسات
SESSIONS = SessionManager()

# ------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------
def extract_prompt_text(text: str) -> str:
    """استخراج النص الصافي بعد كلمات التفعيل"""
    triggers = ["ذكاء", "يا بوت", "بوت", "بقولك"]
    pattern = r"^(" + "|".join(triggers) + r")(\s+|$)"
    match = re.match(pattern, text or "", re.IGNORECASE)
    
    if match:
        return text[match.end():].strip()
    return (text or "").strip()

def is_trigger_message(text: str) -> bool:
    """هل الرسالة تبدأ بكلمة تفعيل؟"""
    triggers = ["ذكاء", "يا بوت", "بوت", "بقولك"]
    pattern = r"^(" + "|".join(triggers) + r")"
    return bool(re.match(pattern, text or "", re.IGNORECASE))

# ------------------------------------------------------------------
# COMMAND: TRANSFORM (تحويل)
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^تحويل(\s+.*)?$"))
async def transform_handler(client: Client, message: Message):
    """
    معالج أمر التحويل.
    المنطق:
    1. ريبلاي -> تنفيذ فوري.
    2. بدون ريبلاي -> طلب ملف وانتظار الرد.
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # استخراج التعليمات الإضافية (مثل: تحويل خلفية حمراء)
    parts = message.text.split(maxsplit=1)
    instructions = parts[1] if len(parts) > 1 else ""

    target_message = None

    # السيناريو 1: المستخدم قام بالرد على رسالة
    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.video or replied.photo or replied.animation:
            target_message = replied
        else:
            await message.reply_text("الرد يجب ان يكون على فيديو او صورة.")
            return

    # السيناريو 2: طلب ملف جديد
    else:
        # زر الإلغاء
        cancel_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("الغاء", callback_data="cancel_transform")]]
        )
        
        prompt_msg = await message.reply_text(
            "ارسل الان الفيديو او الصورة المطلوبة.",
            reply_markup=cancel_kb
        )

        try:
            # انتظار رد المستخدم (Pyromod)
            response: Message = await client.listen(
                chat_id=chat_id, 
                user_id=user_id, 
                filters=filters.incoming, # قبول أي رد وارد من المستخدم
                timeout=60
            )
            
            # التحقق من نص الإلغاء
            if response.text == "الغاء":
                await prompt_msg.delete()
                await message.reply_text("تم الغاء الطلب.")
                return

            # التحقق من نوع الملف
            if response.video or response.photo or response.animation:
                target_message = response
                # تنظيف الرسائل
                try: await prompt_msg.delete()
                except: pass
            else:
                await message.reply_text("الملف غير مدعوم او لم يتم ارسال ملف.")
                return

        except asyncio.TimeoutError:
            await prompt_msg.edit_text("انتهى وقت الانتظار.")
            return

    # مرحلة التنفيذ (Processing)
    if target_message:
        # تحديد رسالة الحالة بناءً على نوع الملف
        if target_message.video or target_message.animation:
            status_text = "جـاري تحويل الفيديو."
        else:
            status_text = "جـاري تحويل الصور."
            
        status_msg = await message.reply_text(status_text)
        
        input_file = None
        output_file = None
        
        try:
            # تحميل الملف
            await client.send_chat_action(chat_id, ChatAction.DOWNLOAD_DOCUMENT)
            input_file = await target_message.download()
            
            # استدعاء محرك الميديا
            output_file = await process_media(input_file, instructions)
            
            if not output_file:
                await status_msg.edit_text("لم اتمكن من معالجة هذا الطلب.")
                return

            # رفع الملف الناتج
            await client.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
            caption_text = f"تم التحويل بنجاح.\nالطلب: {instructions}"
            
            if output_file.endswith(".mp4"):
                await message.reply_video(output_file, caption=caption_text)
            else:
                await message.reply_photo(output_file, caption=caption_text)
            
            await status_msg.delete()

        except Exception as e:
            logger.error(f"Error in transform process: {e}")
            await status_msg.edit_text(f"حدث خطأ اثناء المعالجة: {str(e)}")
        
        finally:
            # تنظيف الملفات
            if input_file and os.path.exists(input_file):
                os.remove(input_file)
            if output_file and os.path.exists(output_file) and output_file != input_file:
                os.remove(output_file)

# زر الإلغاء (Callback)
@app.on_callback_query(filters.regex("^cancel_transform$"))
async def cancel_transform_callback(client: Client, query: CallbackQuery):
    # نستخدم client.stop_listening لإنهاء الانتظار في pyromod إذا كان مدعوماً
    # أو ببساطة نحذف الرسالة، مما سيجعل التايمر ينتهي أو المستخدم يرسل رسالة جديدة
    await query.message.delete()
    await query.answer("تم الالغاء")

# ------------------------------------------------------------------
# COMMAND: PERMANENT AI (ذكاء دائم)
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^(ذكاء دائم)$") & ~filters.bot)
async def enable_permanent_ai(client: Client, message: Message):
    """تفعيل وضع الذكاء المستمر"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    await SESSIONS.start_session(client, user_id, chat_id)
    await message.reply_text(
        "تم تفعيل وضع الذكاء الدائم.\n"
        "سيتم الرد عليك في هذا الجروب فقط.\n"
        "سيتم الاغلاق تلقائيا بعد دقيقة من الصمت."
    )

@app.on_message(filters.regex(r"^(كفاية|خروج)$") & ~filters.bot)
async def disable_permanent_ai(client: Client, message: Message):
    """إيقاف وضع الذكاء المستمر"""
    user_id = message.from_user.id
    
    await SESSIONS.end_session(user_id)
    await message.reply_text("تم ايقاف الذكاء الدائم.")

# ------------------------------------------------------------------
# COMMAND: CLEAR MEMORY (مسح ذاكرتي)
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^(مسح ذاكرتي)$") & ~filters.bot)
async def clear_memory_handler(client: Client, message: Message):
    clear_user_memory(message.from_user.id)
    await message.reply_text("تم مسح ذاكرتك.")

# ------------------------------------------------------------------
# ADMIN CONTROL PANEL
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^(اوامر الذكاء|كيب ذكاء)$") & SUDO_FILTER)
async def admin_panel(client: Client, message: Message):
    status = get_engine_status()
    state_text = "مفعل" if status["enabled"] else "معطل"
    
    text = (
        "**لوحة تحكم الذكاء الاصطناعي**\n\n"
        f"• الحالة: {state_text}\n"
        f"• المحرك: {status['model']}\n"
        f"• المستخدمين النشطين: {status['active_users']}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("اوامر المستخدمين", callback_data="ai_help")],
        [InlineKeyboardButton("تشغيل / ايقاف", callback_data="ai_toggle")],
        [InlineKeyboardButton("تنظيف الذاكرة", callback_data="ai_flush")],
        [InlineKeyboardButton("اعادة تشغيل", callback_data="ai_reboot")],
        [InlineKeyboardButton("اغلاق", callback_data="ai_close")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^ai_"))
async def admin_callbacks(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if user_id not in SUDO_USERS and data != "ai_help":
        await query.answer("هذا الامر للمطورين فقط.", show_alert=True)
        return

    if data == "ai_help":
        help_text = (
            "اوامر المستخدم:\n"
            "- ذكاء <سؤال>\n"
            "- ذكاء دائم\n"
            "- كفاية\n"
            "- تحويل (معالجة ميديا)\n"
            "- مسح ذاكرتي"
        )
        await query.answer(help_text, show_alert=True)

    elif data == "ai_toggle":
        status = get_engine_status()
        new_state = not status["enabled"]
        set_engine_state(new_state)
        await query.answer("تم تغيير الحالة.", show_alert=True)
        new_status_text = "مفعل" if new_state else "معطل"
        try:
            await query.message.edit_text(
                f"**لوحة تحكم الذكاء الاصطناعي**\n\n• الحالة: {new_status_text}\n• المحرك: {status['model']}",
                reply_markup=query.message.reply_markup
            )
        except:
            pass

    elif data == "ai_flush":
        SESSIONS._sessions.clear()
        await query.answer("تم تصفير الجلسات.", show_alert=True)

    elif data == "ai_reboot":
        await query.answer("جاري اعادة التشغيل...", show_alert=True)
        os._exit(0)

    elif data == "ai_close":
        await query.message.delete()

# ------------------------------------------------------------------
# MAIN AI MESSAGE HANDLER
# ------------------------------------------------------------------
@app.on_message(filters.text & ~filters.bot, group=60)
async def main_ai_handler(client: Client, message: Message):
    """
    المعالج الرئيسي للرسائل.
    """
    engine_status = get_engine_status()
    if not engine_status["enabled"] and message.from_user.id not in SUDO_USERS:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    
    should_reply = False
    
    if SESSIONS.is_active(user_id, chat_id):
        should_reply = True
        await SESSIONS.start_session(client, user_id, chat_id)
    
    elif is_trigger_message(message.text):
        should_reply = True
        
    if not should_reply:
        return

    prompt = extract_prompt_text(message.text)
    if not prompt:
        if SESSIONS.is_active(user_id, chat_id):
            prompt = "مرحبا"
        else:
            return

    await client.send_chat_action(chat_id, ChatAction.TYPING)
    wait_msg = await message.reply_text("...")

    async def update_response_text(text: str):
        try:
            if text and text != wait_msg.text:
                safe_text = text[:4000]
                await wait_msg.edit(safe_text)
        except Exception:
            pass

    try:
        final_reply = await ask_ollama_stream(
            user_id=user_id,
            prompt=prompt,
            on_update=update_response_text
        )

        if final_reply and final_reply != wait_msg.text:
            await wait_msg.edit(final_reply[:4000])
            
    except Exception as e:
        logger.error(f"Handler Error: {e}")
        await wait_msg.edit("حدث خطأ اثناء المعالجة.")
