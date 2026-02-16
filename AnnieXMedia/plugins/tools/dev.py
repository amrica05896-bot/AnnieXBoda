# Authored By Certified Coders © 2026
# Ultimate Dev Module: Eval, Shell, and System Diagnostics
# Features: Pre-loaded imports, Async Execution, Auto-File Upload

import os
import re
import subprocess
import sys
import traceback
import asyncio
import io
import time
from io import StringIO

# ✅ مكتبات جاهزة للاستخدام الفوري داخل Eval
import requests
import yt_dlp
import json
import shutil
from datetime import datetime

from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import OWNER_ID
from AnnieXMedia import app

# --- Helper Function to Fix Scope Issues ---
async def aexec(code, client, message):
    # نجهز بيئة العمل بالمتغيرات المهمة عشان متعملش import كل مرة
    local_env = {
        "c": client,
        "m": message,
        "msg": message,
        "client": client,
        "requests": requests,
        "yt_dlp": yt_dlp,
        "os": os,
        "sys": sys,
        "json": json,
        "app": app,
        "print": print, # التأكد من وجود print
    }
    
    # دمج الـ Globals لضمان رؤية المكتبات المستوردة فوق
    exec(
        "async def __aexec(client, message): "
        + "".join(f"\n {a}" for a in code.split("\n")),
        globals(),
        local_env
    )
    return await local_env["__aexec"](client, message)

async def edit_or_reply(msg: Message, **kwargs):
    func = msg.edit_text if msg.from_user.is_self else msg.reply
    await func(**kwargs)

# ================= /eval Command (Python) =================
@app.on_edited_message(filters.command("eval") & filters.user(OWNER_ID))
@app.on_message(filters.command("eval") & filters.user(OWNER_ID))
async def executor(client: Client, message: Message):
    if len(message.command) < 2:
        return await edit_or_reply(message, text="<b>💻 هات كود بايثون عشان أنفذه!</b>\nمثال: <code>/eval print('hello')</code>")

    try:
        cmd = message.text.split(" ", maxsplit=1)[1]
    except IndexError:
        return await message.delete()

    t1 = time.time()
    
    # توجيه المخرجات (Capture Prints)
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    redirected_error = sys.stderr = StringIO()
    stdout, stderr, exc = None, None, None

    try:
        # تنفيذ الكود
        await aexec(cmd, client, message)
    except Exception:
        exc = traceback.format_exc()

    # استرجاع المخرجات
    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = ""
    if exc: evaluation += exc
    elif stderr: evaluation += stderr
    elif stdout: evaluation += stdout
    else: evaluation += "✅ Success (No Output)"

    final_output = f"<b>⥤ 🐍 Python Eval :</b>\n<pre language='python'>{cmd[:50]}...</pre>\n\n<b>⥤ 📤 Result :</b>\n<pre language='python'>{evaluation}</pre>"

    t2 = time.time()
    runtime = round(t2 - t1, 3)

    # لو النتيجة طويلة، ارفعها في ملف
    if len(final_output) > 4096:
        filename = f"eval_output_{int(t1)}.txt"
        with open(filename, "w+", encoding="utf8") as out_file:
            out_file.write(str(evaluation))
        
        await message.reply_document(
            document=filename,
            caption=f"<b>⥤ Eval Executed</b> in {runtime}s",
            quote=False
        )
        os.remove(filename)
    else:
        await edit_or_reply(message, text=final_output)

# ================= /sh Command (Terminal) =================
@app.on_edited_message(filters.command("sh") & filters.user(OWNER_ID))
@app.on_message(filters.command("sh") & filters.user(OWNER_ID))
async def shellrunner(client: Client, message: Message):
    if len(message.command) < 2:
        return await edit_or_reply(message, text="<b>⌨️ هات أمر تيرمينال!</b>\nمثال: <code>/sh pip install speedtest-cli</code>")

    cmd_text = message.text.split(None, 1)[1]
    
    # رسالة انتظار
    status_msg = await edit_or_reply(message, text="<b>🔄 جاري المعالجة...</b>")
    
    try:
        # تنفيذ الأمر
        process = await asyncio.create_subprocess_shell(
            cmd_text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        result = str(stdout.decode().strip()) + str(stderr.decode().strip())
    except Exception as e:
        result = str(e)

    if not result:
        result = "✅ Command Executed (No Output)"

    # لو النتيجة طويلة، ارفعها في ملف
    if len(result) > 4096:
        filename = f"sh_output_{int(time.time())}.txt"
        with open(filename, "w+", encoding="utf8") as file:
            file.write(result)
        await app.send_document(
            message.chat.id,
            filename,
            caption=f"<b>⥤ Shell:</b> <code>{cmd_text}</code>",
            reply_to_message_id=message.id
        )
        os.remove(filename)
        await status_msg.delete()
    else:
        await status_msg.edit_text(f"<b>⥤ 🐚 Shell :</b>\n<pre>{cmd_text}</pre>\n\n<b>⥤ 📤 Output :</b>\n<pre>{result}</pre>")

# ================= أدوات مساعدة =================
# أمر سريع لفحص السيرفر
@app.on_message(filters.command("sys") & filters.user(OWNER_ID))
async def sys_info(client, message):
    # فحص المعالج والرامات
    cpu = "Unknown"
    ram = "Unknown"
    try:
        # Linux only commands
        cpu = subprocess.getoutput("nproc")
        ram_cmd = subprocess.getoutput("free -h | awk '/^Mem/ {print $2}'")
        ram = ram_cmd if ram_cmd else "Unknown"
    except: pass
    
    await message.reply_text(f"🖥 <b>Server Stats:</b>\nCPU Cores: {cpu}\nTotal RAM: {ram}")

