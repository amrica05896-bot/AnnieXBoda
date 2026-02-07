# Authored By Certified Coders (c) 2026
# System: Azan Maestro (Direct Call Engine Mode)
# Location: AnnieXMedia/plugins/AzanSystem/az_utils.py
# FIX: Direct StreamController call to bypass stream.py buttons logic.

import asyncio
import aiohttp
import random
import logging
import pytz
import re
import functools
from datetime import datetime
from typing import Optional, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import enums
from pyrogram.errors import (
    FloodWait,
    UserNotParticipant,
    ChatAdminRequired,
    UserAlreadyParticipant
)

# --- [ Internal Imports ] ---
from AnnieXMedia import app, YouTube
# 🛑 استيراد المتحكم في الكول مباشرة (بدلاً من stream.py)
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.utils.database import get_client, add_active_video_chat
from AnnieXMedia.misc import db
from AnnieXMedia.core.userbot import assistants

# --- [ Configuration & Local DB ] ---
from .az_conf import (
    settings_db,
    resources_db,
    azan_logs_db,
    local_cache,
    CURRENT_RESOURCES,
    CURRENT_DUA_STICKER,
    DEVS,
    MORNING_DUAS,
    NIGHT_DUAS
)

# --- [ Logging Setup ] ---
logging.basicConfig(
    format='%(asctime)s - [AzanEngine] - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("Azan_Maestro_Direct")

# --- [ Constants ] ---
CAIRO_TZ = pytz.timezone('Africa/Cairo')
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)
MAX_CONCURRENT_STREAMS = 15  
stream_semaphore = asyncio.Semaphore(MAX_CONCURRENT_STREAMS)

# ==================================================================
# [SECTION 1] Database & Rights Helpers
# ==================================================================

def retry_operation(max_retries=3, delay=2):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
            logger.error(f"Function {func.__name__} failed: {last_exc}")
            raise last_exc
        return wrapper
    return decorator

def extract_vidid(url: str) -> Optional[str]:
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

async def check_rights(user_id: int, chat_id: int) -> bool:
    if user_id in DEVS: return True
    try:
        mem = await app.get_chat_member(chat_id, user_id)
        return mem.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except: return False

async def get_chat_doc(chat_id: int) -> Dict[str, Any]:
    if chat_id in local_cache:
        return local_cache[chat_id]
    try:
        doc = await settings_db.find_one({"chat_id": chat_id})
        if not doc:
            doc = {
                "chat_id": chat_id,
                "azan_active": True,
                "dua_active": True,
                "night_dua_active": True,
                "prayers": {k: True for k in CURRENT_RESOURCES.keys()}
            }
            await settings_db.insert_one(doc)
        local_cache[chat_id] = doc
        return doc
    except Exception:
        return {}

async def update_doc(chat_id: int, key: str, value, sub_key: str = None):
    try:
        if sub_key:
            await settings_db.update_one({"chat_id": chat_id}, {"$set": {f"prayers.{sub_key}": value}}, upsert=True)
            if chat_id in local_cache: local_cache[chat_id].setdefault("prayers", {})[sub_key] = value
        else:
            await settings_db.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)
            if chat_id in local_cache: local_cache[chat_id][key] = value
    except Exception:
        pass

@retry_operation(max_retries=3)
async def load_resources():
    try:
        stored_res = await resources_db.find_one({"type": "azan_data"})
        if stored_res:
            for k, v in stored_res.get("data", {}).items():
                if k in CURRENT_RESOURCES: CURRENT_RESOURCES[k].update(v)
        
        dua_res = await resources_db.find_one({"type": "dua_sticker"})
        if dua_res:
            global CURRENT_DUA_STICKER
            CURRENT_DUA_STICKER = dua_res.get("sticker_id")
        logger.info("Resources Loaded.")
    except Exception as e:
        logger.error(f"Resource Load Error: {e}")

# ==================================================================
# [SECTION 2] Smart Assistant Prep
# ==================================================================

async def prepare_assistant_membership(chat_id: int):
    try:
        userbot = await get_client(random.choice(assistants))
        try:
            await app.add_chat_members(chat_id, userbot.me.username)
            return True
        except UserAlreadyParticipant:
            return True
        except Exception:
            pass

        try:
            await userbot.get_chat_member(chat_id, "me")
            return True 
        except UserNotParticipant:
            try:
                try:
                    invite_link = await app.export_chat_invite_link(chat_id)
                except:
                    chat = await app.get_chat(chat_id)
                    invite_link = chat.username

                if invite_link:
                    if "+" in str(invite_link): 
                        await userbot.join_chat(invite_link)
                    else: 
                        await userbot.join_chat(str(invite_link))
                    await asyncio.sleep(1)
                    return True
            except Exception as e:
                logger.warning(f"Assistant join failed for {chat_id}: {e}")
                return False
        except Exception:
            return True
    except Exception as e:
        logger.error(f"Assistant Prep Error: {e}")
        return False

# ==================================================================
# [SECTION 3] The Direct Execution Engine (StreamController Direct)
# ==================================================================

# Helper to join call safely across versions
async def _direct_join_call(chat_id, file_path):
    candidates = ["join_call", "join_stream", "join", "start_stream", "start_call"]
    for name in candidates:
        fn = getattr(StreamController, name, None)
        if callable(fn):
            try:
                # محاولة الاتصال بالكول مباشرة
                res = fn(chat_id, chat_id, file_path, video=False)
                if asyncio.iscoroutine(res): await res
                return True
            except Exception:
                continue
    return False

async def start_azan_stream(chat_id: int, prayer_key: str, play_target: str = None, force_test: bool = False):
    if not force_test:
        doc = await get_chat_doc(chat_id)
        if not doc.get("azan_active", True): return
        if not doc.get("prayers", {}).get(prayer_key, True): return

    async with stream_semaphore:
        try:
            res = CURRENT_RESOURCES.get(prayer_key)
            if not res: return
            
            final_link = play_target if play_target else res.get("link")
            if not final_link: return

            # 1. إيقاف أي بث حالي (Force Stop)
            try:
                stop_fn = getattr(StreamController, "force_stop_stream", None) or getattr(StreamController, "stop_stream", None)
                if stop_fn: await stop_fn(chat_id)
            except: pass

            # 2. تنظيف الداتابيز وتجهيزها لوضع الأذان
            db[chat_id] = []
            await add_active_video_chat(chat_id)
            
            # إضافة بيانات وهمية عشان البوت ميفصلش الكول
            # Markup = adhan (عشان التايمر ميبصش عليه)
            db[chat_id].append({
                "vidid": "adhan",
                "title": f"أذان {res.get('name')}",
                "duration": "04:00",
                "streamtype": "adhan",
                "by": "System",
                "user_id": 777,
                "chat_id": chat_id,
                "file": final_link, # مهم جداً
                "markup": "adhan",  # 🛑 السر هنا: مفيش مارك أب
                "mystic": None,     # 🛑 مفيش رسالة يعدل عليها
            })

            # 3. التأكد من المساعد
            await prepare_assistant_membership(chat_id)

            # 4. تحميل الملف (لضمان إنه رابط مباشر أو ملف)
            file_path = final_link
            try:
                # بنحاول نجيب الرابط المباشر لو هو رابط يوتيوب
                if "http" in final_link and "youtu" in final_link:
                     f_path, direct = await YouTube.download(final_link, None, video=False, videoid="adhan")
                     if f_path: file_path = f_path
            except:
                pass

            # 5. الانضمام للكول (تشغيل الصوت)
            success = await _direct_join_call(chat_id, file_path)
            if not success:
                # محاولة أخيرة برابط مباشر بدون تحميل
                await _direct_join_call(chat_id, final_link)

            # 6. إرسال الاستيكر
            if res.get("sticker"):
                try: await app.send_sticker(chat_id, res["sticker"])
                except: pass
            
            # 7. إرسال الرسالة النصية (بدون أزرار نهائياً)
            caption = f"<b>🕌 حان الآن موعد أذان {res.get('name','')}</b>\n<b>حي على الصلاة، حي على الفلاح.</b>"
            try: 
                await app.send_message(chat_id, caption, reply_markup=None)
            except: pass

            # 8. تسجيل في السجل
            if not force_test:
                try:
                    now = datetime.now(CAIRO_TZ)
                    log_key = f"{chat_id}_{now.strftime('%Y-%m-%d_%H:%M')}"
                    await azan_logs_db.insert_one({
                        "chat_id": chat_id,
                        "key": log_key,
                        "prayer_key": prayer_key,
                        "time": now.strftime("%I:%M %p")
                    })
                except: pass

        except Exception as e:
            logger.error(f"Azan Stream Failed {chat_id}: {e}")
            if force_test: await app.send_message(chat_id, f"خطأ في البث: {e}")

# ==================================================================
# [SECTION 4] Broadcaster & Scheduler
# ==================================================================

async def broadcast_azan(prayer_key: str):
    logger.info(f"STARTING AZAN: {prayer_key}")
    res = CURRENT_RESOURCES.get(prayer_key)
    if not res: return
    
    play_link = res["link"]

    tasks = []
    async for doc in settings_db.find({"azan_active": True}):
        c_id = doc.get("chat_id")
        if c_id:
            tasks.append(start_azan_stream(c_id, prayer_key, play_link))
            if len(tasks) >= 10:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                await asyncio.sleep(1) 

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Azan Broadcast Finished.")

async def send_duas_batch(dua_list, setting_key, title, target_chat_id=None):
    # دعم الـ target_chat_id للتست الفردي
    if target_chat_id:
        selected = random.sample(dua_list, min(4, len(dua_list)))
        text = f"<b>{title}</b>\n\n" + "\n\n".join([f"• {d} 🤍" for d in selected])
        text += "\n\n<b>تقبل الله منا ومنكم</b>"
        if CURRENT_DUA_STICKER:
             try: await app.send_sticker(target_chat_id, CURRENT_DUA_STICKER)
             except: pass
        await app.send_message(target_chat_id, text)
        return

    selected = random.sample(dua_list, min(4, len(dua_list)))
    text = f"<b>{title}</b>\n\n" + "\n\n".join([f"• {d} 🤍" for d in selected])
    text += "\n\n<b>تقبل الله منا ومنكم</b>"

    async for entry in settings_db.find({setting_key: True}):
        try:
            c_id = entry.get("chat_id")
            if c_id:
                if CURRENT_DUA_STICKER:
                    try: await app.send_sticker(c_id, CURRENT_DUA_STICKER)
                    except: pass
                await app.send_message(c_id, text)
                await asyncio.sleep(1.5)
        except: continue

# ==================================================================
# [SECTION 5] Init & Updates
# ==================================================================

async def get_azan_times() -> Optional[Dict[str, str]]:
    try:
        async with aiohttp.ClientSession() as session:
            url = "http://api.aladhan.com/v1/timingsByCity"
            params = {"city": "Cairo", "country": "Egypt", "method": "5"}
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["data"]["timings"]
    except: return None

async def update_scheduler():
    await load_resources()
    times = await get_azan_times()
    if not times: return
    
    for job in scheduler.get_jobs():
        if str(job.id).startswith("azan_"): job.remove()
        
    for key in CURRENT_RESOURCES.keys():
        if key in times:
            t_str = times[key].split(" ")[0]
            try:
                h, m = map(int, t_str.split(":"))
                scheduler.add_job(broadcast_azan, "cron", hour=h, minute=m, args=[key], id=f"azan_{key}")
            except: continue
    logger.info("Scheduler Updated with new times.")

def init_azan_scheduler():
    if not scheduler.running:
        scheduler.add_job(lambda: asyncio.create_task(update_scheduler()), "cron", hour=0, minute=5)
        scheduler.add_job(lambda: asyncio.create_task(send_duas_batch(MORNING_DUAS, "dua_active", "أذكار الصباح")), "cron", hour=7, minute=0)
        scheduler.add_job(lambda: asyncio.create_task(send_duas_batch(NIGHT_DUAS, "night_dua_active", "أذكار المساء")), "cron", hour=20, minute=0)
        scheduler.start()
        asyncio.get_event_loop().create_task(update_scheduler())
