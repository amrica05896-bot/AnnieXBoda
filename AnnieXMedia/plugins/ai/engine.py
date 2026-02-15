# file: AnnieXMedia/plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# DeepSeek-R1 Engine (Ollama Async)
# Fixes: ImportError ENGINE, Memory Management, Streaming

import os
import logging
import json
import time
import asyncio
import aiohttp
from typing import Dict, List, Callable, Any, Optional

# ------------------------------------------------------------------
# ⚙️ CONFIGURATION
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_Engine")
logger.setLevel(logging.INFO)

# إعدادات الاتصال بـ Ollama (داخل الدوكر)
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_CHAT_API = f"{OLLAMA_HOST}/api/chat"
TARGET_MODEL = "deepseek-r1:70b"

# الذاكرة المؤقتة (RAM)
# Structure: {user_id: [{"role": "user", "content": "..."}, ...]}
_MEMORY: Dict[int, List[Dict[str, str]]] = {}

# حالة المحرك
_IS_ENABLED = True

# ------------------------------------------------------------------
# 🛠️ CORE FUNCTIONS (API)
# ------------------------------------------------------------------

async def ask_ollama_stream(
    user_id: int, 
    prompt: str, 
    on_update: Callable[[str], Any] = None
) -> str:
    """
    دالة المحادثة الرئيسية مع دعم الذاكرة والرد المتتابع (Streaming).
    تستخدم aiohttp مباشرة لسرعة H200.
    """
    if not _IS_ENABLED:
        return "⚠️ الذكاء الاصطناعي معطل حالياً للصيانة."

    # 1. تجهيز الذاكرة
    if user_id not in _MEMORY:
        _MEMORY[user_id] = []
        # System Prompt
        _MEMORY[user_id].append({
            "role": "system", 
            "content": "You are Annie, a helpful AI assistant. Answer directly and briefly in Arabic. Do NOT use emojis."
        })
    
    # إضافة رسالة المستخدم
    _MEMORY[user_id].append({"role": "user", "content": prompt})
    
    # الاحتفاظ بآخر 12 رسالة فقط لتوفير الذاكرة
    if len(_MEMORY[user_id]) > 12:
        # نحافظ على الـ System Prompt (index 0) ونقص الباقي
        sys_msg = _MEMORY[user_id][0]
        recent = _MEMORY[user_id][-11:]
        _MEMORY[user_id] = [sys_msg] + recent

    full_response = ""
    last_update_time = time.time()
    
    payload = {
        "model": TARGET_MODEL,
        "messages": _MEMORY[user_id],
        "stream": True,
        "options": {
            "temperature": 0.6,
            "num_ctx": 8192  # حجم سياق كبير للـ H200
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_CHAT_API, json=payload) as response:
                
                if response.status != 200:
                    return f"❌ خطأ من الخادم: {response.status}"

                async for line in response.content:
                    if not line: continue
                    
                    try:
                        chunk = json.loads(line)
                        if "message" in chunk:
                            content = chunk["message"].get("content", "")
                            full_response += content
                            
                            # تحديث الرسالة كل 0.8 ثانية لتجنب FloodWait
                            now = time.time()
                            if on_update and (now - last_update_time > 0.8):
                                await on_update(full_response + " ⏳...")
                                last_update_time = now
                        
                        if chunk.get("done", False):
                            break
                            
                    except: pass

        # 3. حفظ رد البوت في الذاكرة
        _MEMORY[user_id].append({"role": "assistant", "content": full_response})
        return full_response

    except Exception as e:
        logger.error(f"Ollama Error: {e}")
        return f"❌ حدث خطأ في الاتصال بالمحرك: {str(e)}"

def clear_user_memory(user_id: int):
    """مسح ذاكرة مستخدم معين"""
    if user_id in _MEMORY:
        del _MEMORY[user_id]

def get_engine_status():
    """جلب حالة المحرك للإحصائيات"""
    return {
        "enabled": _IS_ENABLED,
        "model": TARGET_MODEL,
        "active_users": len(_MEMORY)
    }

def set_engine_state(state: bool):
    """تفعيل أو تعطيل الذكاء"""
    global _IS_ENABLED
    _IS_ENABLED = state

# ------------------------------------------------------------------
# 🛡️ COMPATIBILITY LAYER (حل مشكلة ImportError ENGINE)
# ------------------------------------------------------------------
class LegacyEngineWrapper:
    """
    كلاس وهمي لإرضاء ملف __init__.py القديم
    يمنع خطأ: cannot import name 'ENGINE'
    """
    def __init__(self):
        self.model = TARGET_MODEL
        self.is_running = True
        self.memory = _MEMORY

# ✅ هذا هو السطر الذي يحل المشكلة الحالية
ENGINE = LegacyEngineWrapper()

# تصدير الدوال عشان handlers.py يشوفها
__all__ = ["ask_ollama_stream", "clear_user_memory", "get_engine_status", "set_engine_state", "ENGINE"]
