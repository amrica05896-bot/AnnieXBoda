# Authored By Certified Coders © 2026
# System: Main Launcher (Clean & Optimized)

import sys
import os
import asyncio
import importlib
from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

# إصلاح المسارات
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
    # 1. التحقق من تفعيل UVLOOP (للاطمئنان)
    current_loop = asyncio.get_running_loop()
    loop_type = type(current_loop).__name__
    if "uvloop" in str(type(current_loop)).lower() or "Loop" == loop_type:
        LOGGER("TitanOS").info(f"🌀 UVLOOP IS ACTIVE: {loop_type} (Speed Mode ON)")
    else:
        LOGGER("TitanOS").warning(f"⚠️ UVLOOP NOT DETECTED: {loop_type} (Using Standard Asyncio)")

    # 2. التحقق من الجلسات
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error("Please fill a Pyrogram Session...")
        exit()

    # 3. محاولة جلب الكوكيز
    try:
        await fetch_and_store_cookies()
        LOGGER("AnnieXMedia").info("Youtube Cookies Loaded ✅")
    except Exception as e:
        LOGGER("AnnieXMedia").warning(f"⚠️ Cookie Error: {e}")

    # 4. تحميل إعدادات Sudo وقواعد البيانات
    await sudo()
    try:
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
    except:
        pass

    # 5. تشغيل البوت
    await app.start()
    
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)

    LOGGER("AnnieXMedia.plugins").info("Modules Loaded...")

    # 6. تشغيل المساعد والمكالمات
    await userbot.start()
    await StreamController.start()

    try:
        await StreamController.stream_call("http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4")
    except NoActiveGroupCall:
        LOGGER("AnnieXMedia").error("Please turn on Voice Chat...")
        exit()
    except:
        pass

    await StreamController.decorators()
    LOGGER("AnnieXMedia").info("✅ Annie Music Bot Started Successfully.")
    
    # 7. وضع الخمول (انتظار الأوامر)
    await idle()
    
    # 8. الإغلاق النظيف
    await app.stop()
    await userbot.stop()
    LOGGER("AnnieXMedia").info("Stopping Annie Music Bot...")

# ⛔️ الكود ده معطل لأن run.py هو المسؤول عن التشغيل
# if __name__ == "__main__":
#     asyncio.get_event_loop().run_until_complete(init())
