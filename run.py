import asyncio
import os
import sys
import importlib

# 1. تفعيل UVLOOP وإنشاء اللوب يدوياً (الحل السحري) 🪄
try:
    import uvloop
    # تفعيل السياسة
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    # ⚠️ الخطوة اللي كانت ناقصة: خلق اللوب فوراً قبل أي استيراد
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("✅ UVLOOP is installed, ACTIVE, and Running! 🚀")
except ImportError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("⚠️ UVLOOP is NOT installed. Falling back to default asyncio.")

# دلوقتي نقدر نستورد المكتبات بأمان لأن اللوب موجود خلاص
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
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error("Please fill a Pyrogram Session...")
        exit()

    # محاولة جلب الكوكيز
    try:
        await fetch_and_store_cookies()
        LOGGER("AnnieXMedia").info("Youtube Cookies Loaded ✅")
    except Exception as e:
        LOGGER("AnnieXMedia").warning(f"⚠️ Cookie Error: {e}")

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

    # تشغيل البوت
    print("🤖 Starting Pyrogram Client...")
    await app.start()
    
    print("📂 Loading Modules...")
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)
    LOGGER("AnnieXMedia.plugins").info("Modules Loaded...")

    print("🔊 Starting Userbot & Calls...")
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
    
    # الإبقاء على البوت حياً
    await idle()
    
    await app.stop()
    await userbot.stop()

if __name__ == "__main__":
    # استخدام اللوب اللي خلقناه فوق
    print(f"🔥 Current Event Loop: {type(loop).__name__}")
    loop.run_until_complete(init())
