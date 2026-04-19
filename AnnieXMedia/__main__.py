# Authored By Certified Coders © 2026
# System: Main Launcher (Standard Asyncio - Python 3.13+ Optimized)

import sys
import os
import asyncio
import importlib
from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

# إصلاح المسارات لتجنب مشاكل الاستيراد في البيئات الحديثة
sys.path.insert(0, os.getcwd())

import config
from AnnieXMedia import LOGGER, app, userbot
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import sudo
from AnnieXMedia.plugins import ALL_MODULES
from AnnieXMedia.utils.database import get_banned_users, get_gbanned
from AnnieXMedia.utils.cookie_handler import fetch_and_store_cookies
from config import BANNED_USERS


async def init():
    LOGGER("AnnieXMedia").info("🚀 Starting Annie Music Bot with Standard Asyncio...")

    # 1. التحقق من الجلسات (Sessions)
    if not any([config.STRING1, config.STRING2, config.STRING3, config.STRING4, config.STRING5]):
        LOGGER(__name__).error("❌ Assistant session not filled, please fill a Pyrogram session...")
        sys.exit()

    # 2. محاولة جلب الكوكيز من يوتيوب
    try:
        await fetch_and_store_cookies()
        LOGGER("AnnieXMedia").info("✅ YouTube Cookies Loaded Successfully.")
    except Exception as e:
        LOGGER("AnnieXMedia").warning(f"⚠️ Cookie Error: {e}")

    # 3. تحميل إعدادات المطور وقواعد البيانات
    await sudo()
    try:
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
    except Exception:
        pass

    # 4. تشغيل البوت وتحميل الإضافات
    await app.start()
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)
    LOGGER("AnnieXMedia.plugins").info("✅ Modules Loaded Successfully.")

    # 5. تشغيل الحساب المساعد ومتحكم المكالمات
    await userbot.start()
    await StreamController.start()

    try:
        await StreamController.stream_call("http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4")
    except NoActiveGroupCall:
        LOGGER("AnnieXMedia").error("❌ Please turn on the voice chat of your log group/channel. Bot stopped...")
        sys.exit()
    except Exception:
        pass

    await StreamController.decorators()
    LOGGER("AnnieXMedia").info("✅ Annie Music Bot Started Successfully.")
    
    # 6. وضع الخمول (انتظار الأوامر من المستخدمين)
    await idle()
    
    # 7. الإغلاق النظيف عند إيقاف البوت
    await app.stop()
    await userbot.stop()
    LOGGER("AnnieXMedia").info("🛑 Stopping Annie Music Bot...")


if __name__ == "__main__":
    # الطريقة الحديثة والآمنة لتشغيل الـ Asyncio في Python 3.13+
    try:
        asyncio.run(init())
    except KeyboardInterrupt:
        LOGGER("AnnieXMedia").info("Bot process killed by user (Ctrl+C).")
