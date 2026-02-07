# Authored By Certified Coders (c) 2026
# System: Azan Admin Panel (Timezone Fixed)
# Location: AnnieXMedia/plugins/AzanSystem/az_admin.py

import asyncio
import pytz # 🛑 إضافة مكتبة التوقيت
from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

# استدعاء مكتبات السورس الأساسية
from AnnieXMedia import app
from config import BANNED_USERS

# استدعاء المتغيرات والدوال من ملفات الأذان
from .az_conf import (
    MAIN_OWNER, DEVS, AZAN_GROUP, PRAYER_NAMES_AR, PRAYER_NAMES_REV, DEFAULT_RESOURCES,
    local_cache, admin_state, resources_db, settings_db, 
    CURRENT_RESOURCES, CURRENT_DUA_STICKER
)
from .az_utils import (
    check_rights, get_chat_doc, update_doc, start_azan_stream, 
    get_azan_times, extract_vidid, scheduler, init_azan_scheduler
)

# --- [ الثوابت ] ---
CAIRO_TZ = pytz.timezone('Africa/Cairo') # 🛑 تعريف توقيت القاهرة

# --- [ 0. نظام التشغيل الآمن ] ---
is_azan_system_started = False

@app.on_message(group=AZAN_GROUP + 1)
async def auto_start_azan_system_safe(_, __):
    """تشغيل المجدول تلقائياً مع أول رسالة لضمان الجاهزية"""
    global is_azan_system_started
    if not is_azan_system_started:
        try:
            init_azan_scheduler()
            is_azan_system_started = True
        except Exception:
            pass

# --- [ 1. أوامر المعلومات العامة ] ---

@app.on_message(filters.regex(r"^(الصلاة|مواعيد الصلاة|اوقات الصلاة|الصلاه)$") & filters.group, group=AZAN_GROUP)
async def next_prayer_info(client, message):
    """عرض مواقيت الصلاة"""
    chat_id = message.chat.id
    doc = await get_chat_doc(chat_id)
    
    if not doc.get("azan_active"):
        return await message.reply_text("خدمة الأذان متوقفة في هذه المجموعة.")

    times = await get_azan_times()
    if not times:
        return await message.reply_text("تعذر الحصول على المواقيت حالياً.")

    # 🛑 التصحيح هنا: نأخذ وقت القاهرة ونزيل معلومات المنطقة الزمنية ليطابق صيغة المواقيت
    now = datetime.now(CAIRO_TZ).replace(tzinfo=None)
    
    text = "مواقيت الصلاة بتوقيت القاهرة:\n\n"
    next_prayer = None
    min_diff = float('inf')

    for key, name in PRAYER_NAMES_AR.items():
        t = times[key]
        # المواقيت تأتي بصيغة HH:MM بدون تاريخ، نضيف لها تاريخ اليوم
        prayer_time = datetime.strptime(t, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        
        display_time = prayer_time.strftime("%I:%M %p")
        
        diff = (prayer_time - now).total_seconds()
        if 0 < diff < min_diff:
            min_diff = diff
            next_prayer = (name, diff)

        text += f"- {name}: {display_time}\n"

    text += "\n"
    if next_prayer:
        name, seconds = next_prayer
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        
        remaining = ""
        if hours > 0: remaining += f"{hours} ساعة و "
        remaining += f"{minutes} دقيقة"
        
        text += f"الصلاة القادمة: {name} (بعد {remaining})."
    else:
        text += "انتهت صلوات اليوم، موعدنا الفجر بإذن الله."

    await message.reply_text(text)

# --- [ 2. أوامر المشرفين (التحكم) ] ---

@app.on_message(filters.regex(r"^تفعيل الاذان$") & filters.group & ~BANNED_USERS, group=AZAN_GROUP)
async def admin_enable_azan(_, m):
    if not await check_rights(m.from_user.id, m.chat.id):
        return await m.reply_text("للمشرفين فقط.")
    
    doc = await get_chat_doc(m.chat.id)
    if doc.get("azan_active"): 
        return await m.reply_text("الخدمة مفعلة بالفعل.")
    
    await update_doc(m.chat.id, "azan_active", True)
    await m.reply_text("تم تفعيل خدمة الأذان.")

@app.on_message(filters.regex(r"^قفل الاذان$") & filters.group & ~BANNED_USERS, group=AZAN_GROUP)
async def admin_disable_azan(_, m):
    if not await check_rights(m.from_user.id, m.chat.id):
        return await m.reply_text("للمشرفين فقط.")
    
    doc = await get_chat_doc(m.chat.id)
    
    if doc.get("forced_active", False):
        if m.from_user.id not in DEVS:
            return await m.reply_text("لا يمكن الإيقاف (تفعيل إجباري).")

    if not doc.get("azan_active"): 
        return await m.reply_text("الخدمة متوقفة بالفعل.")
        
    await update_doc(m.chat.id, "azan_active", False)
    await m.reply_text("تم تعطيل خدمة الأذان.")

@app.on_message(filters.regex(r"^(تفعيل الاذكار|تفعيل الدعاء)$") & filters.group & ~BANNED_USERS, group=AZAN_GROUP)
async def admin_enable_duas(_, m):
    if not await check_rights(m.from_user.id, m.chat.id): return
    await update_doc(m.chat.id, "dua_active", True)
    await update_doc(m.chat.id, "night_dua_active", True)
    await m.reply_text("تم تفعيل الأذكار.")

@app.on_message(filters.regex(r"^(قفل الاذكار|قفل الدعاء)$") & filters.group & ~BANNED_USERS, group=AZAN_GROUP)
async def admin_disable_duas(_, m):
    if not await check_rights(m.from_user.id, m.chat.id): return
    doc = await get_chat_doc(m.chat.id)

    if doc.get("forced_dua_active", False) and m.from_user.id not in DEVS:
        return await m.reply_text("لا يمكن الإيقاف (تفعيل إجباري).")

    await update_doc(m.chat.id, "dua_active", False)
    await update_doc(m.chat.id, "night_dua_active", False)
    await m.reply_text("تم تعطيل الأذكار.")


# --- [ 3. لوحة التحكم ] ---

@app.on_message(filters.regex(r"^(اعدادات الاذان|انلاين الاذان|الاذان|أوامر الاذان)$") & filters.group & ~BANNED_USERS, group=AZAN_GROUP)
async def azan_commands_panel(_, m):
    user_id = m.from_user.id
    chat_id = m.chat.id
    
    if user_id in DEVS:
        text = "لوحة تحكم الأذان (المطور):"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("إعدادات المطور", callback_data=f"cmd_owner_{chat_id}")],
            [InlineKeyboardButton("إعدادات المجموعة", callback_data=f"cmd_admin_{chat_id}")],
            [InlineKeyboardButton("إغلاق", callback_data="cmd_close")]
        ])
    elif await check_rights(user_id, chat_id):
        text = "لوحة تحكم الأذان (المشرف):"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("إعدادات المجموعة", callback_data=f"cmd_admin_{chat_id}")],
            [InlineKeyboardButton("إغلاق", callback_data="cmd_close")]
        ])
    else:
        return await m.reply_text("للمشرفين فقط.")

    await m.reply_text(text, reply_markup=kb)

@app.on_message(filters.regex("^/start azset_") & filters.private, group=AZAN_GROUP)
async def open_panel_private(_, m):
    try: target_cid = int(m.text.split("azset_")[1])
    except: return
    
    if not await check_rights(m.from_user.id, target_cid):
        return await m.reply("يجب أن تكون مشرفاً.")
        
    await show_panel(m, target_cid, m.from_user.id in DEVS)

async def show_panel(m, chat_id, is_dev):
    if chat_id in local_cache: del local_cache[chat_id]
    doc = await get_chat_doc(chat_id)
    prayers = doc.get("prayers", {})
    if not prayers: prayers = {k: True for k in CURRENT_RESOURCES.keys()}
    
    kb = []
    
    st_main = "مفعل" if doc.get("azan_active", True) else "معطل"
    kb.append([InlineKeyboardButton(f"الأذان العام: {st_main}", callback_data=f"set_main_{chat_id}")])
    
    st_dua = "مفعل" if doc.get("dua_active", True) else "معطل"
    st_ndua = "مفعل" if doc.get("night_dua_active", True) else "معطل"
    kb.append([
        InlineKeyboardButton(f"الصباح: {st_dua}", callback_data=f"set_dua_{chat_id}"),
        InlineKeyboardButton(f"المساء: {st_ndua}", callback_data=f"set_ndua_{chat_id}")
    ])

    if is_dev:
        row = []
        for k, name in PRAYER_NAMES_AR.items():
            is_active = prayers.get(k, True)
            pst = "مفعل" if is_active else "معطل"
            row.append(InlineKeyboardButton(f"{name}: {pst}", callback_data=f"set_p_{k}_{chat_id}"))
            if len(row) == 2: kb.append(row); row = []
        if row: kb.append(row)

        kb.append([InlineKeyboardButton("تجربة الأذان", callback_data=f"test_azan_single_{chat_id}")])
    
    kb.append([InlineKeyboardButton("تحديث", callback_data=f"refresh_{chat_id}")])
    
    text = f"إعدادات المجموعة: {chat_id}"
    try:
        if isinstance(m, Message): await m.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else: await m.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    except: pass

# --- [ Callback Handler ] ---

@app.on_callback_query(filters.regex(r"^(set_|cmd_|devset_|test_|refresh_|dev_cancel)"), group=AZAN_GROUP)
async def cb_handler(_, q):
    data = q.data
    uid = q.from_user.id
    
    try:
        if "_" in data and data.split("_")[-1].lstrip("-").isdigit():
            chat_id = int(data.split("_")[-1])
        else:
            chat_id = q.message.chat.id
    except: chat_id = 0

    if data == "cmd_close":
        if not await check_rights(uid, chat_id):
            return await q.answer("للمشرفين فقط", show_alert=True)
        return await q.message.delete()

    if data.startswith("cmd_owner"):
        if uid not in DEVS: return await q.answer("للمطورين فقط", show_alert=True)
        
        active_count = await settings_db.count_documents({"azan_active": True})
        text = (
            f"لوحة المطور\n"
            f"المجموعات المفعلة: {active_count}\n\n"
            "التحكم في الوسائط:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تغيير الصوت", callback_data="devset_menu_sound")],
            [InlineKeyboardButton("تغيير الملصق", callback_data="devset_menu_sticker")],
            [InlineKeyboardButton("بث تجريبي للكل", callback_data="test_azan_global")],
            [InlineKeyboardButton("رجوع", callback_data="cmd_back_main")]
        ])
        return await q.edit_message_text(text, reply_markup=kb)

    if data.startswith("cmd_admin"):
        if not await check_rights(uid, chat_id): return await q.answer("للمشرفين فقط", show_alert=True)
        bot_user = (await app.get_me()).username
        url = f"https://t.me/{bot_user}?start=azset_{chat_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("فتح الإعدادات", url=url)]])
        return await q.edit_message_text("اضغط لفتح الإعدادات:", reply_markup=kb)

    if data == "cmd_back_main":
        await azan_commands_panel(_, q.message)
        return

    if data.startswith("refresh_"):
        if not await check_rights(uid, chat_id): return await q.answer("لا تملك صلاحية")
        await show_panel(q, chat_id, uid in DEVS)
        await q.answer("تم التحديث")
        return

    if data.startswith("test_azan_"):
        if uid not in DEVS: 
            return await q.answer("للمطورين فقط", show_alert=True)
        
        if data == "test_azan_global":
            await q.answer("جاري البث...", show_alert=True)
            await q.message.reply("جاري نشر تجربة الأذان لجميع المجموعات...")
            
            count = 0
            tasks = []
            async for doc in settings_db.find({"azan_active": True}):
                c_id = doc.get("chat_id")
                if c_id:
                    tasks.append(start_azan_stream(c_id, "Fajr", None, force_test=True))
                    count += 1
                    if len(tasks) >= 10:
                        await asyncio.gather(*tasks, return_exceptions=True)
                        tasks = []
                        await asyncio.sleep(1)
            
            if tasks: await asyncio.gather(*tasks, return_exceptions=True)
            await q.message.reply(f"تم الإرسال لـ {count} مجموعة.")
            return

        if "single" in data:
            await q.answer("جاري التجربة...", show_alert=False)
            try:
                await start_azan_stream(chat_id, "Fajr", None, force_test=True)
            except Exception as e:
                await q.message.reply(f"خطأ: {e}")
            return

    if data.startswith("set_"):
        if not await check_rights(uid, chat_id): return await q.answer("لا تملك صلاحية")
        
        parts = data.split("_")
        
        if "_p_" in data and uid not in DEVS:
            return await q.answer("للمطورين فقط", show_alert=True)

        if "_p_" in data: 
            pkey = parts[2]
            doc = await get_chat_doc(chat_id)
            new_st = not doc.get("prayers", {}).get(pkey, True)
            await update_doc(chat_id, new_st, new_st, sub_key=pkey)
            
        elif "main" in data: 
            doc = await get_chat_doc(chat_id)
            if doc.get("forced_active", False) and uid not in DEVS:
                return await q.answer("تفعيل إجباري", show_alert=True)
            await update_doc(chat_id, "azan_active", not doc.get("azan_active", True))
            
        elif "dua" in data or "ndua" in data: 
            key = "dua_active" if "_dua_" in data else "night_dua_active"
            doc = await get_chat_doc(chat_id)
            await update_doc(chat_id, key, not doc.get(key, True))
            
        await show_panel(q, chat_id, uid in DEVS)
        return

    if data == "devset_menu_sticker":
        if uid not in DEVS: return
        kb = []
        for k, n in PRAYER_NAMES_AR.items():
            kb.append([InlineKeyboardButton(f"{n}", callback_data=f"devset_sticker_{k}")])
        kb.append([InlineKeyboardButton("الأذكار", callback_data="devset_sticker_dua")])
        kb.append([InlineKeyboardButton("إغلاق", callback_data="dev_cancel")])
        await q.edit_message_text("اختر للتغيير:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "devset_menu_sound":
        if uid not in DEVS: return
        kb = []
        for k, n in PRAYER_NAMES_AR.items():
            kb.append([InlineKeyboardButton(f"{n}", callback_data=f"devset_sound_{k}")])
        kb.append([InlineKeyboardButton("إغلاق", callback_data="dev_cancel")])
        await q.edit_message_text("اختر للتغيير:", reply_markup=InlineKeyboardMarkup(kb))
        return
        
    if data == "dev_cancel":
        if uid in admin_state: del admin_state[uid]
        await q.message.delete()
        return

    if data.startswith("devset_"):
        if uid not in DEVS: return await q.answer("للمطورين فقط", show_alert=True)
        parts = data.split("_")
        atype, pkey = parts[1], parts[2]
        
        if pkey == "dua":
            admin_state[uid] = {"action": "wait_dua_sticker"}
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("إغلاق", callback_data="dev_cancel")]])
            await q.message.edit_text("أرسل الملصق الجديد:", reply_markup=kb)
        else:
            admin_state[uid] = {"action": f"wait_azan_{atype}", "key": pkey}
            req = "ملصق" if atype == "sticker" else "ملف صوتي"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("استعادة الافتراضي", callback_data=f"devset_restore_{pkey}")],
                [InlineKeyboardButton("إغلاق", callback_data="dev_cancel")]
            ])
            await q.message.edit_text(f"أرسل {req} صلاة {PRAYER_NAMES_AR[pkey]} الآن:", reply_markup=kb)
            
        return
        
    if data.startswith("devset_restore_"):
        if uid not in DEVS: return
        pkey = data.split("_")[2]
        
        default_link = DEFAULT_RESOURCES[pkey]["link"]
        default_vid = DEFAULT_RESOURCES[pkey]["vidid"]
        
        CURRENT_RESOURCES[pkey]["link"] = default_link
        CURRENT_RESOURCES[pkey]["vidid"] = default_vid
        await resources_db.update_one({"type": "azan_data"}, {"$set": {f"data.{pkey}.link": default_link, f"data.{pkey}.vidid": default_vid}}, upsert=True)
        
        await q.answer("تمت الاستعادة", show_alert=True)
        await q.message.delete()
        return

# --- [ 4. استقبال مدخلات المطور ] ---

@app.on_message((filters.all) & filters.user(DEVS), group=AZAN_GROUP)
async def dev_input_wait(_, m):
    uid = m.from_user.id
    if uid not in admin_state: return
    state = admin_state[uid]
    action = state["action"]

    if action == "wait_dua_sticker" or "sticker" in action:
        if not m.sticker: return await m.reply("أرسل ملصقاً فقط.")
        
        file_id = m.sticker.file_id
        if action == "wait_dua_sticker":
            global CURRENT_DUA_STICKER
            CURRENT_DUA_STICKER = file_id
            await resources_db.update_one({"type": "dua_sticker"}, {"$set": {"sticker_id": CURRENT_DUA_STICKER}}, upsert=True)
            await m.reply("تم الحفظ.")
        else:
            pkey = state["key"]
            CURRENT_RESOURCES[pkey]["sticker"] = file_id
            await resources_db.update_one({"type": "azan_data"}, {"$set": {f"data.{pkey}.sticker": file_id}}, upsert=True)
            await m.reply("تم الحفظ.")
        
        del admin_state[uid]

    elif "sound" in action: 
        pkey = state["key"]
        file_id = None
        
        if m.audio: file_id = m.audio.file_id
        elif m.voice: file_id = m.voice.file_id
        elif m.video: file_id = m.video.file_id
        elif m.document: file_id = m.document.file_id
        elif m.text and ("http" in m.text or "www" in m.text):
            file_id = m.text
        
        if not file_id:
            return await m.reply("أرسل ملفاً أو رابطاً صحيحاً.")
            
        CURRENT_RESOURCES[pkey]["link"] = file_id
        vid = extract_vidid(file_id) if isinstance(file_id, str) and "http" in file_id else "TelegramFile"
        CURRENT_RESOURCES[pkey]["vidid"] = vid
        
        await resources_db.update_one({"type": "azan_data"}, {"$set": {f"data.{pkey}.link": file_id, f"data.{pkey}.vidid": vid}}, upsert=True)
        await m.reply("تم الحفظ.")
            
        del admin_state[uid]

# --- [ 5. أوامر المالك الخاصة ] ---

@app.on_message(filters.regex("^/start test_global") & filters.private, group=AZAN_GROUP)
async def test_global_start_trigger(_, m):
    if m.from_user.id != MAIN_OWNER: return
    status_msg = await m.reply("جاري البث...")
    count = 0
    
    async for doc in settings_db.find({"azan_active": True}):
        cid = doc.get("chat_id")
        if cid:
            asyncio.create_task(start_azan_stream(cid, "Fajr", force_test=True))
            count += 1
            if count % 10 == 0: await status_msg.edit(f"تم الإرسال لـ {count}...")
            await asyncio.sleep(0.5)
            
    await status_msg.edit(f"تم الإرسال لـ {count} مجموعة.")

@app.on_message(filters.regex(r"^تجربة صباح$") & filters.user(DEVS), group=AZAN_GROUP)
async def tst_morning(client, message):
    if message.from_user.id != MAIN_OWNER: return
    await message.reply("جاري التجربة...")
    from .az_utils import send_duas_batch, MORNING_DUAS
    await send_duas_batch(MORNING_DUAS, None, "أذكار الصباح", target_chat_id=message.chat.id)

@app.on_message(filters.regex(r"^تجربة مساء$") & filters.user(DEVS), group=AZAN_GROUP)
async def tst_evening(client, message):
    if message.from_user.id != MAIN_OWNER: return
    await message.reply("جاري التجربة...")
    from .az_utils import send_duas_batch, NIGHT_DUAS
    await send_duas_batch(NIGHT_DUAS, None, "أذكار المساء", target_chat_id=message.chat.id)

@app.on_message(filters.regex(r"^فحص الاذان$") & filters.group, group=AZAN_GROUP)
async def activate_and_debug(client, message):
    if not await check_rights(message.from_user.id, message.chat.id):
        return 
    
    log = "حالة النظام:\n\n"
    msg = await message.reply_text(log + "جاري الفحص...")
    
    try:
        await settings_db.find_one({})
        log += "- قاعدة البيانات: متصلة\n"
    except Exception as e:
        log += f"- قاعدة البيانات: خطأ ({e})\n"
    
    try:
        times = await get_azan_times()
        if times: log += "- المواقيت: متصلة\n"
        else: log += "- المواقيت: لا يوجد استجابة\n"
    except Exception as e:
        log += f"- المواقيت: خطأ ({e})\n"

    if not scheduler.running:
        init_azan_scheduler()
        log += "- المجدول: أعيد تشغيله\n"
    else:
        log += "- المجدول: يعمل\n"
        
    await msg.edit_text(log + "\nتم الفحص.")

@app.on_message(filters.regex(r"^تفعيل الاذان الاجباري$") & filters.user(DEVS), group=AZAN_GROUP)
async def force_enable(_, m):
    if m.from_user.id != MAIN_OWNER: return
    msg = await m.reply("جاري التفعيل...")
    c = 0
    
    async for doc in settings_db.find({}):
        chat_id = doc.get("chat_id")
        await settings_db.update_one(
            {"_id": doc["_id"]}, 
            {"$set": {"azan_active": True, "forced_active": True}}
        )
        try: 
            await app.send_message(chat_id, "تم تفعيل الأذان إجبارياً.")
            c += 1
            if c % 20 == 0: await asyncio.sleep(1)
        except: pass
        
    local_cache.clear()
    await msg.edit_text(f"تم التفعيل لـ {c} مجموعة.")

@app.on_message(filters.regex(r"^قفل الاذان الاجباري$") & filters.user(DEVS), group=AZAN_GROUP)
async def force_disable(_, m):
    if m.from_user.id != MAIN_OWNER: return
    msg = await m.reply("جاري الإيقاف...")
    c = 0
    
    async for doc in settings_db.find({}):
        chat_id = doc.get("chat_id")
        await settings_db.update_one(
            {"_id": doc["_id"]}, 
            {"$set": {"azan_active": False, "forced_active": False}}
        )
        try: 
            await app.send_message(chat_id, "تم إيقاف الأذان مؤقتاً.")
            c += 1
        except: pass
        
    local_cache.clear()
    await msg.edit_text(f"تم الإيقاف لـ {c} مجموعة.")
