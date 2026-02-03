# Authored By Certified Coders © 2025
# TitanOS Ultimate Engine: Force Loop Binding 🛡️

import asyncio
import logging
import sys

# 1. تفعيل uvloop فوراً
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass

# إعداد اللوجر
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[logging.StreamHandler()]
)
LOGGER = logging.getLogger("TitanOS")

async def main():
    LOGGER.info("⚡ Initializing TitanOS Core...")
    
    # 2. استدعاء ملفات البوت (يتم الاستدعاء هنا داخل الدالة لضمان الترتيب)
    from AnnieXMedia.__main__ import init
    from AnnieXMedia import app, userbot
    from AnnieXMedia.core.call import StreamController
    
    # 3. الحصول على الـ Loop الحالي النشط
    current_loop = asyncio.get_running_loop()
    
    LOGGER.info("🔗 Patching Client Loops (The Magic Fix)...")
    
    # 4. (الحل الجذري) إجبار البوت والمساعد وتطبيقات الاتصال على استخدام نفس الـ Loop
    # بنغير الـ loop property جوه الكائنات دي عشان متضربش error
    app.loop = current_loop
    userbot.loop = current_loop
    
    # إصلاح مشكلة PyTgCalls (StreamController)
    try:
        if hasattr(StreamController, 'one'):
            # بنحفر جوه المكتبة عشان نغير الـ Loop للعميل الداخلي
            if hasattr(StreamController.one, '_app'):
                StreamController.one._app.loop = current_loop
            if hasattr(StreamController.one, '_bind_client'):
                StreamController.one._bind_client.loop = current_loop
    except Exception as e:
        LOGGER.warning(f"⚠️ Note: Could not patch StreamController: {e}")

    LOGGER.info("✅ All Loops Synchronized. Starting System...")
    
    # 5. تشغيل البوت
    await init()

if __name__ == "__main__":
    try:
        # استخدام asyncio.run هو الطريقة الوحيدة الصحيحة مع بايثون 3.12+
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("🛑 Stopped by user")
    except Exception as e:
        LOGGER.error(f"❌ Fatal Error: {e}", exc_info=True)
