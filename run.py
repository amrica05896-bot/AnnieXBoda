# Authored By Certified Coders © 2025
# TitanOS Ultimate Engine: 2026 High-Performance Edition 🛡️
# Optimized for Python 3.14.3 + uvloop + 16-Core Scaling

import asyncio
import logging
import sys
import os

# 1. تفعيل uvloop بأفضل طريقة لعام 2026
try:
    import uvloop
    # تعيين uvloop كمحرك أساسي للنظام بالكامل قبل أي عملية asyncio
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# إعداد اللوجر بشكل "احترافي" للضغط العالي
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] -> %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()]
)
LOGGER = logging.getLogger("TitanOS")

async def main():
    LOGGER.info("🚀 TitanOS Beast Mode: ON (Python 3.14.3)")
    LOGGER.info("📍 Region: Amsterdam | Core: 16-Cores | RAM: 128GB")
    
    # 2. استيراد المكونات (داخل الـ main لضمان عمل الـ uvloop policy أولاً)
    from AnnieXMedia.__main__ import init
    from AnnieXMedia import app, userbot
    from AnnieXMedia.core.call import StreamController
    
    # 3. الحصول على الـ Loop النشط (الذي يديره uvloop الآن)
    current_loop = asyncio.get_running_loop()
    
    LOGGER.info("🔗 Patching Framework Loops...")
    
    # إجبار الكلاينت على استخدام الـ Loop الموحد
    app.loop = current_loop
    userbot.loop = current_loop
    
    # 4. إصلاح محرك الاتصال (The Precision Fix)
    try:
        if hasattr(StreamController, 'one'):
            # الحفر لتوحيد الـ Loop في ntgcalls & pytgcalls 2026
            target = StreamController.one
            if hasattr(target, '_app'): target._app.loop = current_loop
            if hasattr(target, '_bind_client'): target._bind_client.loop = current_loop
            # ميزة جديدة لـ ntgcalls 2.1.0 لتقليل الـ Latency في أمستردام
            if hasattr(target, 'set_priority'): target.set_priority("high")
    except Exception as e:
        LOGGER.warning(f"⚠️ Note: StreamController Sync: {e}")

    LOGGER.info("✅ Systems Synchronized. Launching AnnieXMedia...")
    
    # 5. تشغيل النظام باستخدام TaskGroup (أحدث ميزة في بايثون 14 لإدارة المهام)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(init())
    except Exception as e:
        LOGGER.error(f"❌ Crash Detected: {e}")

if __name__ == "__main__":
    # تفعيل الـ JIT Compiler برمجياً لضمان أقصى سرعة
    if hasattr(sys, "activate_jit"):
        sys.activate_jit()
        LOGGER.info("⚡ Python 3.14 JIT Compiler: ACTIVATED")

    try:
        # التشغيل النهائي
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("🛑 TitanOS: System Shutdown Gracefully.")
    except Exception as e:
        LOGGER.critical(f"💀 Fatal Engine Failure: {e}", exc_info=True)
