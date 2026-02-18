# Authored By Certified Coders © 2026
# System: Core Logic & Services Init
# Path: /root/AnnieXMedia/__main__.py

import sys
import os
import asyncio
import importlib
from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

import config
from AnnieXMedia import LOGGER, app, userbot, BotAPI
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import sudo
from AnnieXMedia.plugins import ALL_MODULES
from AnnieXMedia.utils.database import get_banned_users, get_gbanned
from AnnieXMedia.utils.cookie_handler import fetch_and_store_cookies
from config import BANNED_USERS

# تم تغيير الاسم لـ init_bot لتوضيح أنها دالة تُستدعى ولا تعمل وحدها
async def init_bot():
    # 1. توحيد الـ Event Loop (أهم خطوة لمنع التضارب)
    # بنجيب الـ Loop اللي run.py عمله وبنجبر الكل يستخدمه
    current_loop = asyncio.get_running_loop()
    
    app.loop = current_loop
    userbot.loop = current_loop
    # StreamController بيظبط نفسه تلقائي، بس ممكن نأكد عليه لو لزم الأمر

    # 2. التحقق من التوكنات
    if not (config.STRING1 or config.STRING2 or config.STRING3 or config.STRING4 or config.STRING5):
        LOGGER("Startup").error("Please fill Pyrogram Session")
        sys.exit()

    # 3. تحميل الكوكيز والبيانات
    try:
        await fetch_and_store_cookies()
    except: pass
    
    await sudo()
    try:
        users = await get_gbanned()
        for user_id in users: BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users: BANNED_USERS.add(user_id)
    except: pass

    # 4. تشغيل العملاء (Clients)
    LOGGER("AnnieX").info("🚀 Starting Bot & Userbot...")
    await app.start()
    await userbot.start()

    # 5. تحميل الملحقات (Plugins)
    for all_module in ALL_MODULES:
        importlib.import_module("AnnieXMedia.plugins" + all_module)
    LOGGER("Modules").info(f"Loaded {len(ALL_MODULES)} Modules.")

    # 6. تشغيل نظام المكالمات
    LOGGER("CallSystem").info("🎧 Starting Stream Controller...")
    await StreamController.start()

    # محاولة وهمية لتنشيط السواقة (اختياري)
    try:
        await StreamController.stream_call("http://docs.evostream.com/sample_content/assets/sintel1m720p.mp4")
    except NoActiveGroupCall:
        LOGGER("Error").error("Please turn on Voice Chat in Logger Group!")
        sys.exit()
    except: pass

    await StreamController.decorators()

    # 7. 🔥 تشغيل الـ Enterprise API (الموقع)
    # بيشتغل Parallel مع البوت على نفس الـ Loop
    LOGGER("WebSystem").info("🌐 Starting Enterprise API Server (Port 8080)...")
    await BotAPI.start()

    LOGGER("AnnieX").info("✅ System Online & Ready.")
    
    # 8. وضع الخمول (Idle)
    # هنا البوت بيفضل شغال لحد ما تدوس Ctrl+C
    await idle()
    
    # 9. الإغلاق الآمن (عند الخروج)
    LOGGER("Shutdown").info("🛑 Stopping Services...")
    await app.stop()
    await userbot.stop()
    await BotAPI.stop()
    LOGGER("Shutdown").info("👋 Goodbye!")

# ⛔️ ملاحظة هامة جداً:
# شيلنا (if __name__ == "__main__") من هنا نهائياً
# لأن ملف run.py هو اللي هيشغل الدالة دي.
