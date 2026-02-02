import asyncio
import os
import sys
import importlib

# =================================================================
# 1. إعداد UVLOOP وإنشاء الـ Event Loop يدوياً (القلب النابض) ❤️
# =================================================================
try:
    import uvloop
    # تفعيل سياسة uvloop لتسريع البايثون
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    # إنشاء اللوب فوراً وتسجيله في النظام
    # (هذا السطر هو الذي يمنع خطأ "There is no current event loop")
    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("✅ UVLOOP is Installed, Active, and Registered! 🚀")
except ImportError:
    # خطة بديلة في حالة عدم وجود uvloop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("⚠️ UVLOOP Not Found. Falling back to default asyncio.")

# =================================================================
# 2. استيراد المكتبات (بعد ضمان وجود اللوب)
# =================================================================
from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

# إصلاح مسار المجلد الحالي
sys.path.insert(0, os.getcwd())

import config
from AnnieXMedia import LOGGER, app, userbot
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import sudo
from AnnieXMedia.plugins import ALL_MODULES
from AnnieXMedia.utils.database import get_banned_users, get_gbanned
from AnnieXMedia.utils.cookie_handler import fetch_and_store_cookies
from config import BANNED_USERS

# =================================================================
# 3. دالة التشغيل الرئيسية
# =================================================================
async def init():
    # التحقق من المتغيرات
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error("Please fill a Pyrogram Session...")
        exit()

    # تحميل الكوكيز (يوتيوب)
    try:
        await fetch_and_store_cookies()
        LOGGER("AnnieXMedia").info("Youtube Cookies Loaded ✅")
    except Exception as e:
        LOGGER("AnnieXMedia").warning(f"⚠️ Cookie Error: {e}")

    # تحميل صلاحيات المطورين
    await sudo()

    # تحميل المحظורים
    try:
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
    except:
        pass

    # تشغيل بوت التليجرام
    print("🤖 Starting Pyrogram Client...")
    await app.start()
    
    # تحميل الموديولات (Plugins)
    print("📂 Loading Modules...")
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)
    LOGGER("AnnieXMedia.plugins").info("Modules Loaded...")

    # تشغيل اليوزربوت والمكالمات
    print("🔊 Starting Userbot & Calls...")
    await userbot.start()
    await StreamController.start()

    # تجربة الانضمام لمكالمة (تنشيط)
    try:
        await StreamController.stream_call("http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4")
    except NoActiveGroupCall:
        LOGGER("AnnieXMedia").error("Please turn on Voice Chat...")
        exit()
    except:
        pass

    # تفعيل الديكورات والإضافات
    await StreamController.decorators()
    LOGGER("AnnieXMedia").info("✅ Annie Music Bot Started Successfully.")
    
    # الإبقاء على البوت حياً (Idle)
    await idle()
    
    # إيقاف التشغيل عند الخروج
    await app.stop()
    await userbot.stop()

# =================================================================
# 4. نقطة الانطلاق
# =================================================================
if __name__ == "__main__":
    # التأكد من استخدام اللوب الذي أنشأناه في البداية
    print(f"🔥 Current Event Loop: {type(loop).__name__}")
    
    # تشغيل دالة init داخل اللوب
    loop.run_until_complete(init())
