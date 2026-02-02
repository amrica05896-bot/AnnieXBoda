import asyncio
import os
import sys

# =================================================================
# 1. إعداد UVLOOP وإنشاء اللوب يدوياً (الخطوة الأولى إجبارياً)
# =================================================================
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    # إنشاء اللوب يدوياً لتسجيله في الذاكرة فوراً
    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    print("✅ UVLOOP Active & Locked! 🚀")
except ImportError:
    # خطة بديلة لو uvloop مش موجود (للاحتياط)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("⚠️ UVLOOP Not Found. Using Default.")

# =================================================================
# 2. (Monkey Patch) إجبار النظام بالكامل على استخدام اللوب بتاعنا
# هذه الدالة تمنع بايثون 3.12 من إظهار خطأ "different loop"
# =================================================================
def get_my_loop():
    return loop

# استبدال دالة بايثون الأصلية بالدالة بتاعتنا
asyncio.get_event_loop = get_my_loop

# =================================================================
# 3. استيراد كود البوت (يتم الاستيراد بعد تثبيت اللوب)
# =================================================================
sys.path.insert(0, os.getcwd())

# استدعاء دالة init من ملف السورس الأصلي
from AnnieXMedia.__main__ import init

# =================================================================
# 4. تشغيل البوت
# =================================================================
if __name__ == "__main__":
    print(f"🔥 Current Event Loop: {type(loop).__name__}")
    # تشغيل الدالة داخل اللوب الذي أنشأناه في السطر 15
    loop.run_until_complete(init())
