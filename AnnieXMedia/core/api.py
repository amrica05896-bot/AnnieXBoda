# ==============================================================================
# PROJECT: OBSIDIAN API KERNEL (v16.0)
# AUTHORED BY: CERTIFIED CODERS © 2026
# SYSTEM: MASTER BACKEND GATEWAY
# COMPATIBILITY: PYTGCALLS v3.0 | FLET DASHBOARD | NATIVE STREAM ENGINE
# ==============================================================================

import os
import asyncio
import json
import time
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from aiohttp import web
from aiohttp.web import Response, json_response

# --- استيراد أساسيات البوت ---
from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from config import BOT_TOKEN

# --- استيراد منطق المنصات والستريم ---
from AnnieXMedia.platforms import YouTube
from AnnieXMedia.utils.stream.stream import stream  # الربط المباشر بمحرك الستريم

# --- إعدادات السيرفر ---
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

# --- إخراس اللوجات المزعجة (Silent Mode) ---
# يمنع السيرفر من كتابة "GET /status_json 200" كل ثانية في التيرمينال
logging.getLogger("aiohttp.access").setLevel(logging.CRITICAL)
logging.getLogger("aiohttp.server").setLevel(logging.CRITICAL)

class ObsidianBackend:
    def __init__(self):
        # السماح بطلبات ضخمة لرفع الميديا مستقبلاً
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        """خريطة توجيه الروابط (Routing Map)"""
        # إعدادات الـ CORS للسماح لتطبيق Flet بالاتصال بحرية
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        # 1. نقاط بيانات الحالة (Telemetry & Status)
        self.app.router.add_get("/status_json", self.get_live_status)
        self.app.router.add_get("/api/stats", self.get_system_telemetry)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_chat_queue)
        
        # 2. نقاط التحكم والتنفيذ (Action Controllers)
        self.app.router.add_post("/api/control", self.execute_control)
        self.app.router.add_post("/api/play", self.bridge_play_request)
        self.app.router.add_post("/api/search", self.media_neural_search)
        
        # 3. توثيق بسيط (Auth)
        self.app.router.add_post("/api/auth", self.authenticate)

    # --- CORS Middleware Helpers ---
    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS, DELETE, PUT",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        }

    async def cors_options(self, request):
        return Response(headers=self._cors_headers())

    # --- دورة حياة السيرفر (Lifecycle) ---
    async def start(self):
        # access_log=None يضمن عدم وجود دوشة في اللوجات
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()
        print(f"🚀 OBSIDIAN BACKEND ACTIVE: PORT {API_PORT} (SILENT MODE)")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # ==========================================================================
    # 📡 DATA ENDPOINTS (تجهيز البيانات للداشبورد)
    # ==========================================================================

    async def get_live_status(self, request):
        """جلب بيانات المكالمات الشغالة حالياً"""
        uptime_sec = time.time() - START_TIME
        active_chats = list(StreamController.active_calls)
        
        chats_payload = []
        for chat_id in active_chats:
            chat_obj = {
                "chat_id": chat_id,
                "title": "Resolving Stream...",
                "vidid": "",
                "stream_type": "audio",
                "duration": "Live"
            }
            
            # سحب البيانات الحقيقية من ذاكرة البوت (db)
            db_entry = db.get(chat_id)
            if db_entry and len(db_entry) > 0:
                current = db_entry[0]
                chat_obj["title"] = current.get("title", "Unknown Track")
                chat_obj["vidid"] = current.get("vidid", "") 
                chat_obj["stream_type"] = current.get("streamtype", "audio")
                chat_obj["duration"] = current.get("dur", "00:00")
            
            chats_payload.append(chat_obj)

        return json_response({
            "status": "online",
            "uptime": str(timedelta(seconds=int(uptime_sec))),
            "count": len(active_chats),
            "chats": chats_payload
        }, headers=self._cors_headers())

    async def get_system_telemetry(self, request):
        """إحصائيات المعالج والرام (120 FPS Ready)"""
        try:
            return json_response({
                "cpu": psutil.cpu_percent(interval=None),
                "ram_percent": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            }, headers=self._cors_headers())
        except:
            return json_response({"cpu": 0, "ram_percent": 0}, headers=self._cors_headers())

    async def get_chat_queue(self, request):
        """جلب طابور الانتظار لجروب معين"""
        chat_id = request.match_info.get("chat_id")
        try:
            cid = int(chat_id)
            queue_raw = db.get(cid, [])
            clean_q = []
            for item in queue_raw:
                clean_q.append({
                    "title": item.get("title", "Unknown"),
                    "duration": item.get("dur", "00:00"),
                    "requester": item.get("by", "Remote Admin")
                })
            return json_response({"queue": clean_q, "count": len(clean_q)}, headers=self._cors_headers())
        except:
            return json_response({"queue": [], "error": "Invalid ID"}, headers=self._cors_headers())

    # ==========================================================================
    # 🎮 CONTROL & BRIDGE LOGIC (التنفيذ الفعلي)
    # ==========================================================================

    async def execute_control(self, request):
        """تنفيذ أوامر (Pause, Resume, Stop, Skip)"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            value = data.get("value", 100) # للـ Volume مستقبلاً

            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Chat Inactive"}, status=404, headers=self._cors_headers())

            if action == "pause":
                await StreamController.pause_stream(chat_id)
            elif action == "resume":
                await StreamController.resume_stream(chat_id)
            elif action == "stop":
                await StreamController.stop_stream(chat_id)
            elif action == "mute":
                await StreamController.mute_stream(chat_id)
            elif action == "unmute":
                await StreamController.unmute_stream(chat_id)
            
            # --- منطق الـ Skip الاحترافي (محاكاة skip.py) ---
            elif action == "skip":
                check = db.get(chat_id)
                if check:
                    check.pop(0) # إزالة الأغنية الحالية
                    if not check:
                        await StreamController.stop_stream(chat_id)
                    else:
                        # تشغيل التالي فوراً عبر الـ Assistant
                        await StreamController.one.stop_stream(chat_id) 

            return json_response({"status": "success", "executed": action}, headers=self._cors_headers())
        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def bridge_play_request(self, request):
        """
        أهم دالة: تستقبل طلب Play من dashboard.py وتمرره لمحرك الستريم
        ليقوم البوت بإرسال الأزرار والصورة في الجروب تلقائياً.
        """
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Payload Empty"}, status=400, headers=self._cors_headers())

            # 1. إرسال رسالة "جاري المعالجة" (تتحول لاحقاً لأزرار)
            try:
                mystic = await app.send_message(
                    chat_id, 
                    "🔍 **جاري تشغيل طلب من لوحة التحكم...**"
                )
            except Exception as e:
                return json_response({"error": f"Bot cannot speak in chat: {e}"}, status=400, headers=self._cors_headers())

            # 2. البحث (Neural Search)
            try:
                # نستخدم track للحصول على التفاصيل (تدعم الروابط والبحث)
                details, track_id = await YouTube.track(query)
                if not track_id:
                    # محاولة بحث عادي إذا فشل الـ track
                    results = await YouTube.search(query, limit=1)
                    if results:
                        track_id = results[0]["vidid"]
                        details, _ = await YouTube.track(track_id)
                    else:
                        await mystic.edit_text("❌ لم يتم العثور على نتائج للطلب.")
                        return json_response({"error": "No Results"}, status=404, headers=self._cors_headers())
            except Exception as e:
                await mystic.edit_text(f"❌ خطأ في النظام: {e}")
                return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

            # 3. إطلاق مهمة الستريم (Background Task)
            # نمرر كل شيء لدالة stream() الأصلية لتقوم هي بالباقي (تنزيل، تشغيل، أزرار)
            asyncio.create_task(stream(
                None,           # Callback (غير مطلوب)
                mystic,         # الرسالة التي ستعدل للأزرار
                777000,         # ID وهمي للأدمن
                details,        # كائن تفاصيل الفيديو
                chat_id,        # Chat ID
                "Obsidian Admin",# User Name
                chat_id,        # Original Chat ID
                video=video_mode,
                streamtype="youtube",
                forceplay=False
            ))

            return json_response({
                "status": "bridged",
                "title": details.get("title"),
                "vidid": track_id
            }, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": f"Kernel Error: {e}"}, status=500, headers=self._cors_headers())

    async def media_neural_search(self, request):
        """البحث السريع للمتصفح"""
        try:
            data = await request.json()
            q = data.get("query")
            # استدعاء دالة البحث الحقيقية من YouTube.py
            results = await YouTube.search(q, limit=15)
            
            clean_results = []
            for r in results:
                vid = r.get("vidid")
                clean_results.append({
                    "title": r.get("title"),
                    "vidid": vid,
                    "duration": r.get("duration", ""),
                    "thumb": f"https://img.youtube.com/vi/${vid}/mqdefault.jpg"
                })
            return json_response({"results": clean_results}, headers=self._cors_headers())
        except:
            return json_response({"results": []}, headers=self._cors_headers())

    async def authenticate(self, request):
        """التحقق من التوكن"""
        try:
            data = await request.json()
            if data.get("token") == BOT_TOKEN:
                return json_response({"auth": True}, headers=self._cors_headers())
            return json_response({"auth": False}, status=401, headers=self._cors_headers())
        except:
            return json_response({"error": "Bad Request"}, status=400, headers=self._cors_headers())

# --- تهيئة الكائن للتشغيل ---
BotAPI = ObsidianBackend()
