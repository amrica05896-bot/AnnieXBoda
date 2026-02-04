# plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# Project: AnnieXMedia - Ultimate Speed Edition
# Optimized based on Termux Scan Results

import logging
import asyncio
import time
import random
import inspect 
from typing import Dict, Optional, Callable

from g4f.client import AsyncClient
import g4f.Provider

# ------------------------------------------------------------------
# Logger
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_AI")

# ------------------------------------------------------------------
# Dynamic Provider Loader
# ------------------------------------------------------------------
def get_provider_by_name(name_list):
    available = []
    for name in name_list:
        if hasattr(g4f.Provider, name):
            available.append(getattr(g4f.Provider, name))
    return available

# ✅ القائمة الذهبية (بناءً على فحص Termux الخاص بك)
# AnyProvider: هو مزود ذكي يختار تلقائياً
# ApiAirforce & OperaAria: مزودات سريعة جداً حالياً
SCANNER_RESULTS = ["ApiAirforce", "OperaAria", "Yqcloud", "AnyProvider"]

FAST_PROVIDERS = get_provider_by_name(SCANNER_RESULTS)
# نستخدم نفس القائمة للوضع الذكي لضمان الاستقرار
SMART_PROVIDERS = get_provider_by_name(SCANNER_RESULTS) 

# الموديلات
LIGHT_MODEL = "gpt-4o-mini" 
HEAVY_MODEL = "gpt-4o"   
DEFAULT_MODEL = LIGHT_MODEL

# اعدادات الذاكرة
USER_HISTORY: Dict[int, list] = {}
MAX_HISTORY = 6       
MAX_USERS_IN_MEM = 50 

# ------------------------------------------------------------------
# Engine State
# ------------------------------------------------------------------
class AIEngineState:
    def __init__(self):
        self.enabled: bool = True
        self.model: str = DEFAULT_MODEL

    def reset(self):
        self.enabled = True
        self.model = DEFAULT_MODEL

ENGINE = AIEngineState()

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _clean_memory_if_needed():
    if len(USER_HISTORY) > MAX_USERS_IN_MEM:
        keys = list(USER_HISTORY.keys())[:15]
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
# Core Logic
# ------------------------------------------------------------------

async def ask_ollama_stream(
    user_id: int,
    prompt: str,
    system_prompt: str = "أنت آني، مساعد ذكي، تحدث بالعربية بوضوح.",
    model: Optional[str] = None,
    on_update: Optional[Callable[[str], None]] = None,
) -> str:
    
    if not ENGINE.enabled:
        return "الذكاء الاصطناعي متوقف للصيانة."

    used_model = model or ENGINE.model
    messages = _build_messages(user_id, prompt, system_prompt)
    
    full_reply = ""
    last_update_time = time.time()
    last_sent_len = 0
    
    # خلط القائمة عشان الحمل يتوزع
    if FAST_PROVIDERS:
        random.shuffle(FAST_PROVIDERS)

    # 3 محاولات
    for attempt in range(3): 
        try:
            # اختيار المزود
            # في أول محاولة نستخدم AnyProvider لأنه مجمع
            if attempt == 0 and hasattr(g4f.Provider, "AnyProvider"):
                current_provider = g4f.Provider.AnyProvider
            elif attempt < len(FAST_PROVIDERS):
                current_provider = FAST_PROVIDERS[attempt]
            else:
                current_provider = None # Auto Mode

            client = AsyncClient(provider=current_provider)
            
            response_obj = await client.chat.completions.create(
                model=used_model,
                messages=messages,
                stream=True
            )
            
            # معالجة الرد
            response_iterator = response_obj
            if inspect.iscoroutine(response_obj):
                response_iterator = await response_obj
            
            async for chunk in response_iterator:
                content = ""
                if hasattr(chunk.choices[0].delta, "content"):
                    content = chunk.choices[0].delta.content
                elif hasattr(chunk, "content"):
                    content = chunk.content
                
                if content:
                    full_reply += content
                    now = time.time()
                    # تحديث الرسالة كل 2.5 ثانية لتفادي الـ Flood
                    if on_update and (now - last_update_time > 2.5) and (len(full_reply) - last_sent_len > 25):
                        try:
                            await on_update(f"{full_reply} ▌")
                            last_update_time = now
                            last_sent_len = len(full_reply)
                        except: pass 

            if full_reply and len(full_reply.strip()) > 1:
                break 

        except Exception as e:
            # logger.error(f"Attempt {attempt} failed: {e}")
            await asyncio.sleep(1)

    if not full_reply:
        return "عذراً، لم أتمكن من الاتصال بسيرفرات الذكاء الاصطناعي حالياً."

    # Final Update
    if on_update:
        try: await on_update(full_reply)
        except: pass

    # Save History
    _clean_memory_if_needed()
    history = USER_HISTORY.setdefault(user_id, [])
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": full_reply})
    USER_HISTORY[user_id] = history[-MAX_HISTORY:]
    
    return full_reply

# ------------------------------------------------------------------
# Exports
# ------------------------------------------------------------------
def clear_user_memory(user_id: int):
    USER_HISTORY.pop(user_id, None)

def toggle_model() -> str:
    ENGINE.model = HEAVY_MODEL if ENGINE.model == LIGHT_MODEL else LIGHT_MODEL
    return ENGINE.model

__all__ = ["ENGINE", "ask_ollama_stream", "clear_user_memory", "toggle_model"]
