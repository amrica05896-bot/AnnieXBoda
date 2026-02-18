# Authored By Certified Coders © 2026
# System: TitanOS API Bridge (Stream Linker - V2 Final)
# Logic: Web Request -> Fake Message -> Native stream() -> Telegram UI

import os
import asyncio
import json
import time
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from aiohttp import web
from aiohttp.web import Response, json_response

# --- Core Imports ---
from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from config import BOT_TOKEN

# --- Platform & Stream Logic ---
from AnnieXMedia.platforms import YouTube
from AnnieXMedia.utils.stream.stream import stream  # استدعاء دالة الستريم الأصلية

# --- Server Config ---
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

# --- Silence Logs ---
logging.getLogger("aiohttp.access").setLevel(logging.CRITICAL)

class TitanApi:
    def __init__(self):
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        """Routing Table"""
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        self.app.router.add_get("/", self.serve_dashboard)
        self.app.router.add_get("/status_json", self.get_live_status)
        self.app.router.add_get("/api/stats", self.get_hardware_stats)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_queue)
        
        self.app.router.add_post("/api/control", self.execute_control)
        self.app.router.add_post("/api/play", self.bridge_play)  # 🔥 الدالة الجديدة
        self.app.router.add_post("/api/search", self.media_search)
        self.app.router.add_post("/api/download", self.media_download)

    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def cors_options(self, request):
        return Response(headers=self._cors_headers())

    async def start(self):
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()
        print(f"✅ TitanOS Bridge API Active on Port {API_PORT}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # ==========================
    # 📡 DATA & DASHBOARD
    # ==========================

    async def serve_dashboard(self, request):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            if os.path.exists(html_path):
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return Response(text=content, content_type="text/html", headers=self._cors_headers())
            return Response(text="Dashboard Not Found", status=404)
        except Exception as e:
            return Response(text=str(e), status=500)

    async def get_live_status(self, request):
        uptime_sec = time.time() - START_TIME
        active_chats = list(StreamController.active_calls)
        chats_payload = []
        for chat_id in active_chats:
            chat_obj = {
                "chat_id": chat_id,
                "title": "Loading...",
                "vidid": "",
                "stream_type": "audio",
                "duration": "Live"
            }
            db_entry = db.get(chat_id)
            if db_entry and len(db_entry) > 0:
                current = db_entry[0]
                chat_obj["title"] = current.get("title", "Unknown")
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

    async def get_hardware_stats(self, request):
        try:
            return json_response({
                "cpu": psutil.cpu_percent(interval=None),
                "ram_percent": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            }, headers=self._cors_headers())
        except:
            return json_response({"cpu": 0}, headers=self._cors_headers())

    async def get_queue(self, request):
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
            queue_raw = db.get(chat_id, [])
            clean_q = []
            for item in queue_raw:
                clean_q.append({
                    "title": item.get("title", "Unknown"),
                    "duration": item.get("dur", "00:00"),
                    "requester": item.get("by", "Unknown")
                })
            return json_response({"queue": clean_q}, headers=self._cors_headers())
        except:
            return json_response({"queue": []}, headers=self._cors_headers())

    # ==========================
    # 🔥 THE BRIDGE (الربط بـ stream.py)
    # ==========================

    async def bridge_play(self, request):
        """
        هذه الدالة تستقبل الطلب من الموقع، وتقوم بإنشاء 'mystic' (رسالة)
        ثم تمرر كل شيء لدالة stream() الأصلية لتقوم هي بالباقي (أزرار، طابور، الخ).
        """
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Empty Payload"}, status=400, headers=self._cors_headers())

            # 1. إرسال رسالة "جاري المعالجة" للجروب (هذه ستصبح mystic)
            try:
                mystic = await app.send_message(
                    chat_id, 
                    "🔍 **جاري تشغيل طلب الداشبورد...**"
                )
            except Exception as e:
                return json_response({"error": f"Bot cannot speak in chat: {e}"}, status=500, headers=self._cors_headers())

            # 2. البحث عن التفاصيل (مطلوب لدالة stream)
            try:
                # نستخدم track للحصول على التفاصيل (تدعم الروابط والبحث)
                details, track_id = await YouTube.track(query)
                if not track_id:
                    # محاولة بحث عادي
                    results = await YouTube.search(query, limit=1)
                    if results:
                        track_id = results[0]["vidid"]
                        details, _ = await YouTube.track(track_id)
                    else:
                        await mystic.edit_text("❌ لم يتم العثور على نتائج.")
                        return json_response({"error": "No results"}, status=404, headers=self._cors_headers())
            except Exception as e:
                await mystic.edit_text(f"❌ خطأ في البحث: {e}")
                return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

            # 3. استدعاء دالة stream الأصلية
            # هذه الدالة ستقوم بالتحميل، الانضمام، التعديل على mystic، وإضافة الأزرار
            # تماماً كما لو كتب المستخدم الأمر في الجروب
            asyncio.create_task(stream(
                _,              # CallbackQuery (غير مستخدم هنا، نمرر أي شيء)
                mystic,         # الرسالة التي سيتم تعديلها للأزرار
                777000,         # User ID (Dashboard Admin)
                details,        # تفاصيل الفيديو
                chat_id,        # Chat ID
                "Titan Admin",  # User Name
                chat_id,        # Original Chat ID
                video=video_mode,
                streamtype="youtube",
                forceplay=False # نتركه False عشان لو في أغنية شغالة يروح طابور
            ))

            return json_response({
                "status": "bridged", 
                "message": "Request passed to Stream Controller",
                "title": details.get("title")
            }, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": f"Bridge Error: {e}"}, status=500, headers=self._cors_headers())

    async def execute_control(self, request):
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            
            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Inactive"}, status=404, headers=self._cors_headers())

            if action == "pause": await StreamController.pause_stream(chat_id)
            elif action == "resume": await StreamController.resume_stream(chat_id)
            elif action == "stop": await StreamController.stop_stream(chat_id)
            elif action == "mute": await StreamController.mute_stream(chat_id)
            elif action == "unmute": await StreamController.unmute_stream(chat_id)
            elif action == "skip":
                # محاكاة أمر التخطي
                check = db.get(chat_id)
                if check:
                    check.pop(0)
                    if not check:
                        await StreamController.stop_stream(chat_id)
                    else:
                        await StreamController.one.stop_stream(chat_id) # Force next track via decorator

            return json_response({"status": "executed"}, headers=self._cors_headers())
        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def media_search(self, request):
        try:
            data = await request.json()
            query = data.get("query")
            results = await YouTube.search(query, limit=12)
            clean = []
            for r in results:
                vid = r.get("vidid")
                clean.append({
                    "title": r.get("title"),
                    "vidid": vid,
                    "duration": r.get("duration", ""),
                    "thumb": f"https://img.youtube.com/vi/${vid}/mqdefault.jpg"
                })
            return json_response({"results": clean}, headers=self._cors_headers())
        except:
            return json_response({"results": []}, headers=self._cors_headers())

    async def media_download(self, request):
        return json_response({"status": "queued"}, headers=self._cors_headers())

# تهيئة الكائن
BotAPI = TitanApi()
