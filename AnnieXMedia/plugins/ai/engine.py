# plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# Project: AnnieXMedia - B200 Local Power Edition
# Cleaned: No G4F, Only Pure Local Ollama

import logging
import asyncio
import time
from typing import Dict, Optional, Callable

# مكتبة الذكاء المحلي فقط (Ollama)
from ollama import AsyncClient as OllamaClient

# ------------------------------------------------------------------
# Logger
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_AI_Engine")

# ------------------------------------------------------------------
# Models Configuration (B200 Optimized)
# ------------------------------------------------------------------
# الموديلات التي قمنا بتحميلها في الـ Docker
LIGHT_MODEL = "llama3.2"       # 3B (سريع جداً - وضع السرعة)
HEAVY_MODEL = "llama3.1:70b"   # 70B (الوحش الذكي - وضع العبقرية)

DEFAULT_MODEL = LIGHT_MODEL

# اعدادات الذاكرة
USER_HISTORY: Dict[int, list] = {}
MAX_HISTORY = 8       # زدنا الذاكرة لأن السيرفر المحلي يتحمل
MAX_USERS_IN_MEM = 100 

# ------------------------------------------------------------------
# Engine State
# ------------------------------------------------------------------
class AIEngineState:
    def __init__(self):
        self.enabled: bool = True
        self.model: str = DEFAULT_MODEL 

ENGINE = AIEngineState()

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _clean_memory_if_needed():
    if len(USER_HISTORY) > MAX_USERS_IN_MEM:
        keys = list(USER_HISTORY.keys())[:20]
        for k in keys: del USER_HISTORY[k]

def _build_messages(user_id: int, prompt: str, system_prompt: str) -> list:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    history = USER_HISTORY.get(user_id, [])
    messages.extend(history[-MAX_HISTORY:])
    messages.append({"role": "user", "content": prompt})
    return messages

# ------------------------------------------------------------------
# Core Logic (Ollama Only)
# ------------------------------------------------------------------

async def ask_ollama_stream(
    user_id: int,
    prompt: str,
    system_prompt: str = "أنت آني، مساعد ذكي، تحدث بالعربية بوضوح.",
    model: Optional[str] = None,
    on_update: Optional[Callable[[str], None]] = None,
) -> str:
    
    if not ENGINE.enabled:
        return "⚠️ الذكاء الاصطناعي متوقف حالياً للصيانة."

    used_model = model or ENGINE.model
    messages = _build_messages(user_id, prompt, system_prompt)
    
    full_reply = ""
    last_update_time = time.time()
    last_sent_len = 0
    
    try:
        # الاتصال بـ localhost لأن Ollama يعمل داخل نفس السيرفر (Docker)
        client = OllamaClient(host='http://localhost:11434')
        
        # بدء المحادثة (Streaming)
        async for chunk in await client.chat(model=used_model, messages=messages, stream=True):
            content = chunk.get('message', {}).get('content', '')
            if content:
                full_reply += content
                now = time.time()
                # تحديث الرسالة كل 0.5 ثانية (استجابة سريعة جداً للمحلي)
                if on_update and (now - last_update_time > 0.5) and (len(full_reply) - last_sent_len > 8):
                    try:
                        await on_update(f"{full_reply} ▌")
                        last_update_time = now
                        last_sent_len = len(full_reply)
                    except: pass
        
        if not full_reply:
             return "❌ لم يصل رد من الموديل المحلي. (تأكد أن الموديل تم تحميله في الـ start.sh)"

    except Exception as e:
        logger.error(f"Ollama Error: {e}")
        return f"❌ خطأ داخلي في محرك B200: {str(e)}"

    # التحديث النهائي للنص
    if on_update:
        try: await on_update(full_reply)
        except: pass

    # حفظ الذاكرة
    _clean_memory_if_needed()
    history = USER_HISTORY.setdefault(user_id, [])
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": full_reply})
    USER_HISTORY[user_id] = history[-MAX_HISTORY:]
    
    return full_reply

# ------------------------------------------------------------------
# Exports & Controls
# ------------------------------------------------------------------
def clear_user_memory(user_id: int):
    USER_HISTORY.pop(user_id, None)

def toggle_model() -> str:
    """
    يقوم بالتبديل بين الموديل الخفيف والذكاء العالي ويعيد الاسم الجديد
    """
    if ENGINE.model == LIGHT_MODEL:
        ENGINE.model = HEAVY_MODEL
    else:
        ENGINE.model = LIGHT_MODEL
    return ENGINE.model

__all__ = ["ENGINE", "ask_ollama_stream", "clear_user_memory", "toggle_model", "LIGHT_MODEL", "HEAVY_MODEL"]
