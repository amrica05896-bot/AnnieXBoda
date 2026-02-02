# Authored By Certified Coders © 2025
import sys
import os
import asyncio
import importlib

# 1. تفعيل UVLOOP (أول خطوة للأداء القصوى) 🚀
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✅ UVLOOP is installed and ACTIVE! 🚀")
except ImportError:
    print("⚠️ UVLOOP is NOT installed. Falling back to default asyncio.")

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
    await app.start()
    
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)

    LOGGER("AnnieXMedia.plugins").info("Modules Loaded...")

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
    
    await idle()
    
    await app.stop()
    await userbot.stop()
    LOGGER("AnnieXMedia").info("Stopping Annie Music Bot...")

if __name__ == "__main__":
    # التأكد من نوع اللوب المستخدم
    loop = asyncio.get_event_loop_policy().get_event_loop()
    print(f"🔥 Current Event Loop: {type(loop).__name__}")
    
    # تشغيل البوت
    loop.run_until_complete(init())
