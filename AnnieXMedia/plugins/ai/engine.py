# plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# DeepSeek-R1 Local Inference Engine - H200 Optimized
# Strict No-Emoji Policy Enforced

import logging
import json
import time
import asyncio
import aiohttp
from typing import Dict, List, Optional, Callable, Any

# ------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ------------------------------------------------------------------

# عنوان سيرفر Ollama المحلي داخل الدوكر
OLLAMA_API_URL = "http://localhost:11434/api/chat"

# الموديل الأساسي والثابت (DeepSeek-R1 70B)
# تم اختياره ليكون الموديل الوحيد لضمان استقرار الذاكرة
CURRENT_MODEL = "deepseek-r1:70b"

# إعدادات الذاكرة والسياق
MAX_HISTORY_LENGTH = 15       # عدد الرسائل المحفوظة في السياق
MAX_CONTEXT_TOKENS = 8192     # حجم السياق للموديل
REQUEST_TIMEOUT = 120         # مهلة انتظار الرد (ثانية)

# إعدادات التوليد (Generation Parameters)
GENERATION_OPTIONS = {
    "temperature": 0.6,       # توازن بين الإبداع والدقة
    "top_p": 0.9,
    "num_ctx": MAX_CONTEXT_TOKENS,
    "num_predict": 2048,      # أقصى عدد كلمات للرد
    "repeat_penalty": 1.1     # منع تكرار الكلام
}

# ------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_DeepSeek_Engine")
logger.setLevel(logging.INFO)

# ------------------------------------------------------------------
# MEMORY MANAGEMENT CLASS
# ------------------------------------------------------------------
class MemoryManager:
    """
    class لادارة ذاكرة المستخدمين وتنظيفها تلقائياً
    """
    def __init__(self):
        self._history: Dict[int, List[Dict[str, str]]] = {}
        self._last_access: Dict[int, float] = {}
        self._max_users = 200  # أقصى عدد مستخدمين في الرام

    def get_history(self, user_id: int) -> List[Dict[str, str]]:
        """جلب سجل محادثة المستخدم"""
        self._last_access[user_id] = time.time()
        return self._history.get(user_id, [])

    def add_message(self, user_id: int, role: str, content: str):
        """إضافة رسالة جديدة للذاكرة"""
        if user_id not in self._history:
            self._history[user_id] = []
        
        # إضافة الرسالة
        self._history[user_id].append({"role": role, "content": content})
        self._last_access[user_id] = time.time()

        # تشذيب الذاكرة (Pruning)
        if len(self._history[user_id]) > MAX_HISTORY_LENGTH:
            # نحتفظ بأول رسالة (لو كانت system prompt) وآخر N رسائل
            # هنا نفترض أننا نحتفظ بآخر MAX_HISTORY_LENGTH فقط
            self._history[user_id] = self._history[user_id][-MAX_HISTORY_LENGTH:]

    def clear_history(self, user_id: int):
        """مسح ذاكرة مستخدم معين"""
        if user_id in self._history:
            del self._history[user_id]
        if user_id in self._last_access:
            del self._last_access[user_id]

    def cleanup_old_sessions(self):
        """تنظيف الجلسات الخاملة لتوفير الرام"""
        if len(self._history) < self._max_users:
            return

        current_time = time.time()
        # حذف من لم يتحدث منذ ساعة
        users_to_delete = [
            uid for uid, timestamp in self._last_access.items()
            if current_time - timestamp > 3600
        ]
        
        for uid in users_to_delete:
            self.clear_history(uid)
            
        logger.info(f"Memory Cleanup: Removed {len(users_to_delete)} idle sessions.")

# تهيئة مدير الذاكرة
MEMORY = MemoryManager()

# ------------------------------------------------------------------
# ENGINE STATE
# ------------------------------------------------------------------
class EngineState:
    def __init__(self):
        self.enabled: bool = True
        self.system_prompt: str = (
            "انت مساعد ذكي ومتطور. "
            "اجاباتك دقيقة ومختصرة ومفيدة. "
            "تحدث باللغة العربية بطلاقة. "
            "لا تستخدم الايموجي ابدا في ردودك. "
            "كن مهذبا ومحترفا."
        )

ENGINE_STATE = EngineState()

# ------------------------------------------------------------------
# CORE INFERENCE FUNCTION
# ------------------------------------------------------------------
async def ask_ollama_stream(
    user_id: int,
    prompt: str,
    system_prompt: Optional[str] = None,
    on_update: Optional[Callable[[str], None]] = None
) -> str:
    """
    الدالة الرئيسية للتحدث مع DeepSeek-R1
    
    Args:
        user_id: معرف المستخدم للذاكرة
        prompt: سؤال المستخدم
        system_prompt: توجيهات النظام (اختياري)
        on_update: دالة callback لتحديث الرسالة اثناء الكتابة
        
    Returns:
        الرد النهائي كنص
    """
    
    # 1. التحقق من حالة المحرك
    if not ENGINE_STATE.enabled:
        return "النظام متوقف حاليا للصيانة."

    # 2. تجهيز سجل الرسائل
    messages = []
    
    # إضافة System Prompt
    sys_prompt_text = system_prompt or ENGINE_STATE.system_prompt
    messages.append({"role": "system", "content": sys_prompt_text})
    
    # إضافة تاريخ المحادثة
    history = MEMORY.get_history(user_id)
    messages.extend(history)
    
    # إضافة السؤال الحالي
    messages.append({"role": "user", "content": prompt})

    # 3. تجهيز بيانات الطلب (Payload)
    payload = {
        "model": CURRENT_MODEL,
        "messages": messages,
        "stream": True,  # تفعيل الرد المتتابع
        "options": GENERATION_OPTIONS
    }

    full_response = ""
    last_update_time = time.time()
    
    try:
        # 4. بدء الاتصال بـ Ollama
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_API_URL, json=payload) as response:
                
                # التحقق من نجاح الاتصال
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API Error: {response.status} - {error_text}")
                    return f"حدث خطأ في الخادم الداخلي: {response.status}"

                # 5. معالجة الرد المتتابع (Streaming)
                async for line in response.content:
                    if not line:
                        continue
                        
                    try:
                        # فك تشفير JSON
                        chunk_data = json.loads(line)
                        
                        # استخراج النص
                        if "message" in chunk_data:
                            content = chunk_data["message"].get("content", "")
                            if content:
                                full_response += content
                                
                                # تحديث الرسالة للمستخدم (كل 0.5 ثانية لعدم الضغط على API تيليجرام)
                                current_time = time.time()
                                if on_update and (current_time - last_update_time > 0.5):
                                    try:
                                        await on_update(full_response)
                                        last_update_time = current_time
                                    except Exception as e:
                                        # تجاهل اخطاء تحديث الرسالة (مثل FloodWait)
                                        pass
                                        
                        # التحقق من انتهاء الرد
                        if chunk_data.get("done", False):
                            break
                            
                    except json.JSONDecodeError:
                        continue

    except asyncio.TimeoutError:
        logger.error("Ollama Request Timed Out")
        return "عذرا، استغرق الخادم وقتا طويلا للرد. حاول مرة اخرى."
        
    except aiohttp.ClientError as e:
        logger.error(f"Network Error connecting to Ollama: {e}")
        return "فشل الاتصال بمحرك الذكاء الاصطناعي."
        
    except Exception as e:
        logger.exception(f"Unexpected Error in ask_ollama_stream: {e}")
        return "حدث خطأ غير متوقع اثناء المعالجة."

    # 6. حفظ الرد في الذاكرة
    if full_response.strip():
        MEMORY.add_message(user_id, "user", prompt)
        MEMORY.add_message(user_id, "assistant", full_response)
        
        # تنظيف دوري للذاكرة
        if len(MEMORY._history) % 10 == 0:
            MEMORY.cleanup_old_sessions()

    return full_response

# ------------------------------------------------------------------
# PUBLIC EXPORTS
# ------------------------------------------------------------------
def clear_user_memory(user_id: int):
    """واجهة لمسح الذاكرة من الخارج"""
    MEMORY.clear_history(user_id)

def get_engine_status():
    """معرفة حالة المحرك"""
    return {
        "model": CURRENT_MODEL,
        "enabled": ENGINE_STATE.enabled,
        "active_users": len(MEMORY._history)
    }

def set_engine_state(enabled: bool):
    """تغيير حالة التشغيل"""
    ENGINE_STATE.enabled = enabled

__all__ = ["ask_ollama_stream", "clear_user_memory", "get_engine_status", "set_engine_state"]
