import asyncio
import os
import sys

# 1. استيراد وتفعيل UVLOOP (يجب أن يكون أول شيء)
try:
    import uvloop
    # هذا السطر يستبدل لوب بايثون العادي بـ uvloop الصاروخي
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✅ UVLOOP is installed and ACTIVE! 🚀")
except ImportError:
    print("⚠️ UVLOOP is NOT installed. Falling back to default asyncio.")

from pyrogram import Client

# استيراد دالة التشغيل من ملفك الأساسي
# تأكد أن اسم المجلد صحيح (AnnieXMedia)
from AnnieXMedia import init, LOGGER

if __name__ == "__main__":
    # التأكد من نوع اللوب المستخدم (للاطمئنان فقط)
    loop = asyncio.get_event_loop_policy().get_event_loop()
    LOGGER("Optimizer").info(f"Current Event Loop: {type(loop).__name__}")
    
    # تشغيل البوت
    loop.run_until_complete(init())
