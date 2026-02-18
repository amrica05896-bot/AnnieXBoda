# Authored By Certified Coders © 2026
# TitanOS Ultimate Engine: Force Loop Binding + Auto-Clean 🛡️

import asyncio
import logging
import sys
import os
import glob

# ==========================================
# 🔥 1. نظام التنظيف النووي (قبل أي شيء)
# ==========================================
def clean_garbage():
    """حذف ملفات الجلسة التالفة لمنع خطأ struct.error"""
    try:
        # بنمسح أي ملف ينتهي بـ .session أو .session-journal
        junk_files = glob.glob("*.session") + glob.glob("*.session-journal")
        if junk_files:
            print(f"🧹 TitanOS: Found junk sessions: {junk_files}")
            for f in junk_files:
                try:
                    os.remove(f)
                    print(f"✅ Deleted: {f}")
                except Exception as e:
                    print(f"❌ Failed to delete {f}: {e}")
        else:
            print("✅ TitanOS: System clean. No junk sessions found.")
    except Exception as e:
        print(f"⚠️ Clean error: {e}")

# تنفيذ التنظيف فوراً
clean_garbage()

# ==========================================
# 🚀 2. إعدادات النظام
# ==========================================

# تفعيل uvloop فوراً
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
    
    # استدعاء ملفات البوت (بعد التنظيف)
    from AnnieXMedia.__main__ import init
    from AnnieXMedia import app, userbot
    from AnnieXMedia.core.call import StreamController
    
    # 3. الحصول على الـ Loop الحالي النشط
    current_loop = asyncio.get_running_loop()
    
    LOGGER.info("🔗 Patching Client Loops (The Magic Fix)...")
    
    # 4. إجبار البوت والمساعد وتطبيقات الاتصال على استخدام نفس الـ Loop
    try:
        app.loop = current_loop
        userbot.loop = current_loop
        if hasattr(app, 'storage'): app.storage.loop = current_loop
    except Exception as e:
        LOGGER.error(f"Loop patch error: {e}")

    # إصلاح مشكلة PyTgCalls (StreamController)
    try:
        # محاولة الوصول للعملاء وتوحيد الـ Loop
        if hasattr(StreamController, 'one') and StreamController.one:
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
