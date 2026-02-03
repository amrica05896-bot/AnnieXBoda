# plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# Project: AnnieXMedia - Ultimate Speed Edition
# Optimized for Zero-Flood & Arabic UI

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
# Dynamic Provider Loader (2026 Stable Providers)
# ------------------------------------------------------------------
def get_provider_by_name(name_list):
    available = []
    for name in name_list:
        if hasattr(g4f.Provider, name):
            available.append(getattr(g4f.Provider, name))
    return available

# مزودات طلقة ومستقرة ولا تطلب كوكيز أو ملفات HAR
FAST_NAMES = ["Blackbox2", "PollinationsAI", "DarkAI", "ChatGptEs", "DuckDuckGo"]
SMART_NAMES = ["Blackbox2", "Liaobots", "ChatGptEs"]

FAST_PROVIDERS = get_provider_by_name(FAST_NAMES)
SMART_PROVIDERS = get_provider_by_name(SMART_NAMES)

# الموديلات المستقرة (الابتعاد عن GPT-3.5 الميت)
LIGHT_MODEL = "gpt-4o-mini" 
HEAVY_MODEL = "gpt-4o"   
DEFAULT_MODEL = LIGHT_MODEL

# اعدادات الذاكرة (Memory)
USER_HISTORY: Dict[int, list] = {}
CACHE: Dict[str, str] = {}
MAX_HISTORY = 6       
MAX_USERS_IN_MEM = 50 

# ------------------------------------------------------------------
# Engine State
# ------------------------------------------------------------------
class AIEngineState:
    def __init__(self):
        self.enabled: bool = True
        self.model: str = DEFAULT_MODEL
        self.temperature: float = 0.7 

    def reset(self):
        self.enabled = True
        self.model = DEFAULT_MODEL

ENGINE = AIEngineState()

# ------------------------------------------------------------------
# Internal Helpers
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
# Core Logic (Anti-Flood & Arabic)
# ------------------------------------------------------------------

async def ask_ollama_stream(
    user_id: int,
    prompt: str,
    system_prompt: str = "أنت آني، مساعد ذكي في تليجرام، ردك يجب أن يكون مختصراً ومفيداً باللغة العربية.",
    model: Optional[str] = None,
    on_update: Optional[Callable[[str], None]] = None,
) -> str:
    
    if not ENGINE.enabled:
        return "الذكاء الاصطناعي متوقف حالياً للصيانة."

    used_model = model or ENGINE.model
    messages = _build_messages(user_id, prompt, system_prompt)
    
    full_reply = ""
    last_update_time = time.time()
    last_sent_len = 0

    # محاولة الاتصال مع 3 محاولات بمزودات مختلفة
    for attempt in range(3): 
        try:
            # اختيار مزود عشوائي في كل محاولة للهرب من الـ 502
            target_list = FAST_PROVIDERS if used_model == LIGHT_MODEL else SMART_PROVIDERS
            current_provider = random.choice(target_list) if target_list else None
            
            client = AsyncClient(provider=current_provider)
            
            response_obj = client.chat.completions.create(
                model=used_model,
                messages=messages,
                stream=True
            )
            
            # فحص نوع الرد (Async Generator Fix)
            if inspect.iscoroutine(response_obj):
                response = await response_obj
            else:
                response = response_obj
            
            async for chunk in response:
                content = ""
                if hasattr(chunk.choices[0].delta, "content"):
                    content = chunk.choices[0].delta.content
                elif hasattr(chunk, "content"):
                    content = chunk.content
                
                if content:
                    full_reply += content
                    
                    # --- منطق منع الـ FloodWait الذكي ---
                    # تحديث تليجرام فقط كل 3 ثواني وبشرط وجود زيادة كافية في النص
                    now = time.time()
                    if on_update and (now - last_update_time > 3.0) and (len(full_reply) - last_sent_len > 40):
                        try:
                            await on_update(f"{full_reply}\n\n**جاري التفكير...**")
                            last_update_time = now
                            last_sent_len = len(full_reply)
                        except Exception:
                            pass 

            if full_reply:
                break 

        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            if attempt == 2: 
                return "البوت مشغول حالياً، حاول في وقت آخر."
            await asyncio.sleep(2)

    if not full_reply:
        return "البوت مشغول حالياً، حاول في وقت آخر."

    # التحديث النهائي للرسالة
    if on_update:
        try:
            await on_update(full_reply)
        except:
            pass

    # حفظ التاريخ في الذاكرة
    _clean_memory_if_needed()
    history = USER_HISTORY.setdefault(user_id, [])
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": full_reply})
    USER_HISTORY[user_id] = history[-MAX_HISTORY:]
    
    return full_reply

# ------------------------------------------------------------------
# Controls & Exports
# ------------------------------------------------------------------
def clear_user_memory(user_id: int):
    USER_HISTORY.pop(user_id, None)

def toggle_model() -> str:
    ENGINE.model = HEAVY_MODEL if ENGINE.model == LIGHT_MODEL else LIGHT_MODEL
    return ENGINE.model

__all__ = ["ENGINE", "ask_ollama_stream", "clear_user_memory", "toggle_model"]
