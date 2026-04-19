import sys
import os
import asyncio

# 🚀 الضربة الاستباقية: إنشاء Event Loop وتثبيتها قبل استدعاء أي ملف!
# ده بيجبر MongoDB و Pyrogram وكل المكتبات إنها تستخدم نفس الـ Loop دي من البداية.
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import importlib
from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

# إصلاح المسارات
sys.path.insert(0, os.getcwd())

# دلوقتي لما الملفات دي تتعملها Import، هتمسك في الـ Loop اللي جهزناها فوق بأمان تام
import config
from AnnieXMedia import LOGGER, app, userbot
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import sudo
from AnnieXMedia.plugins import ALL_MODULES
from AnnieXMedia.utils.database import get_banned_users, get_gbanned
from AnnieXMedia.utils.cookie_handler import fetch_and_store_cookies
from config import BANNED_USERS


async def init():
    LOGGER("AnnieXMedia").info("🚀 Starting Annie Music Bot with Synchronized Event Loop...")

    if not any([config.STRING1, config.STRING2, config.STRING3, config.STRING4, config.STRING5]):
        LOGGER(__name__).error("❌ Assistant session not filled, please fill a Pyrogram session...")
        sys.exit()

    try:
        await fetch_and_store_cookies()
        LOGGER("AnnieXMedia").info("✅ YouTube Cookies Loaded Successfully.")
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
    except Exception:
        pass

    await app.start()
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)
    LOGGER("AnnieXMedia.plugins").info("✅ Modules Loaded Successfully.")

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
    
    await idle()
    
    await app.stop()
    await userbot.stop()
    LOGGER("AnnieXMedia").info("🛑 Stopping Annie Music Bot...")


if __name__ == "__main__":
    try:
        # نشغل البوت على اللوب اللي جهزناها فوق خالص، ومفيش أي تعارض هيحصل!
        loop.run_until_complete(init())
    except KeyboardInterrupt:
        LOGGER("AnnieXMedia").info("🛑 Bot process killed by user (Ctrl+C).")
    except Exception as e:
        LOGGER("AnnieXMedia").error(f"⚠️ Fatal Error Occurred: {e}")
