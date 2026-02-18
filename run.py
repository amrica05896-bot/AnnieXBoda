# Authored By Certified Coders © 2026
# System: Root Launcher (TitanOS Bootloader)
# Path: /root/run.py

import asyncio
import logging
import os
import glob
import sys

# إعداد اللوجر
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[logging.StreamHandler()]
)
LOGGER = logging.getLogger("TitanOS")

def clean_garbage():
    """حذف ملفات الجلسة التالفة قبل بدء الـ Loop"""
    try:
        junk_files = glob.glob("*.session") + glob.glob("*.session-journal")
        if junk_files:
            LOGGER.info(f"🧹 Cleaning junk sessions: {junk_files}")
            for f in junk_files:
                try:
                    os.remove(f)
                except: pass
    except: pass

async def main():
    # 1. التنظيف
    clean_garbage()
    
    LOGGER.info("⚡ Initializing System...")

    # 2. استدعاء دالة التشغيل من داخل السورس
    # (لاحظ: بنناديها هنا عشان تشتغل جوه الـ Loop اللي run.py عمله)
    from AnnieXMedia.__main__ import init_bot
    
    await init_bot()

if __name__ == "__main__":
    # تفعيل uvloop للسرعة القصوى
    try:
        import uvloop
        uvloop.install()
        LOGGER.info("🌀 UVLOOP Enabled")
    except:
        LOGGER.info("⚠️ UVLOOP Not found (Using Standard)")

    try:
        # هذه هي الـ asyncio.run الوحيدة في المشروع كله
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("🛑 Stopped by User")
    except Exception as e:
        LOGGER.error(f"❌ Fatal Error: {e}", exc_info=True)
