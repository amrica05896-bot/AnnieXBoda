# Authored By Certified Coders © 2026
# System: AnnieX Enterprise API & Backend Server
# Features: Dashboard Hosting, Full Stream Control, System Stats, Queue Management

import os
import asyncio
import json
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any

from aiohttp import web
from aiohttp.web import Response, json_response

# استيراد أدوات البوت
from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import get_lang
from config import BOT_TOKEN

# استيراد يوتيوب محلياً لمنع التداخل (Circular Import)
from AnnieXMedia.platforms import YouTubeAPI
YouTube = YouTubeAPI()

# إعدادات السيرفر
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

class EnterpriseApi:
    def __init__(self):
        # زيادة حجم الطلب المسموح به (لرفع ملفات المستقبل)
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        """تعريف مسارات الـ API"""
        # 1. إعدادات CORS (للسماح للمتصفح بالاتصال)
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        # 2. الواجهة الرئيسية (الداشبورد)
        self.app.router.add_get("/", self.serve_dashboard)
        
        # 3. روابط البيانات (JSON)
        self.app.router.add_get("/status_json", self.get_dashboard_data) # للداشبورد HTML
        self.app.router.add_get("/api/stats", self.get_system_stats)      # للمراقبة الخارجية
        self.app.router.add_get("/api/queue/{chat_id}", self.get_chat_queue)
        
        # 4. روابط التحكم (Actions)
        self.app.router.add_post("/api/control", self.control_stream)
        self.app.router.add_post("/api/play", self.play_via_api)
        self.app.router.add_post("/api/auth", self.authenticate)

    # --- CORS Helpers ---
    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def cors_options(self, request):
        return Response(headers=self._cors_headers())

    # --- Server Lifecycle ---
    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()
        print(f"✅ Enterprise API Running on port {API_PORT}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # --- Endpoints ---

    async def serve_dashboard(self, request):
        """عرض ملف HTML الخاص بلوحة التحكم"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            if os.path.exists(html_path):
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return Response(text=content, content_type="text/html", headers=self._cors_headers())
            else:
                return Response(text="Dashboard file not found.", status=404)
        except Exception as e:
            return Response(text=f"Server Error: {str(e)}", status=500)

    async def get_dashboard_data(self, request):
        """تجهيز البيانات لملف dashboard.html"""
        uptime_sec = time.time() - START_TIME
        uptime_str = str(timedelta(seconds=int(uptime_sec)))
        
        chats_data = []
        active_chats = list(StreamController.active_calls)

        for chat_id in active_chats:
            chat_info = {
                "chat_id": chat_id,
                "title": "Loading...",
                "vidid": "",
                "stream_type": "audio",
                "duration": "00:00"
            }
            
            # جلب البيانات من الداتابيز
            check = db.get(chat_id)
            if check and len(check) > 0:
                current = check[0]
                chat_info["title"] = current.get("title", "Unknown Track")
                chat_info["vidid"] = current.get("vidid", "") # مهم للصور والفيديو
                chat_info["stream_type"] = current.get("streamtype", "audio")
                chat_info["duration"] = current.get("dur", "Live")
            
            chats_data.append(chat_info)

        response_data = {
            "version": "TitanOS Enterprise 2026",
            "count": len(active_chats),
            "uptime": uptime_str,
            "chats": chats_data
        }
        return json_response(response_data, headers=self._cors_headers())

    async def control_stream(self, request):
        """استقبال أوامر التحكم (Pause, Resume, Volume, etc.)"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            value = data.get("value")

            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Chat not active"}, status=404, headers=self._cors_headers())

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
            elif action == "skip":
                await StreamController.skip_stream(chat_id, "", False)
            elif action == "volume":
                if value is not None:
                    await StreamController.change_volume_call(chat_id, int(value))
            else:
                return json_response({"error": "Unknown Action"}, status=400, headers=self._cors_headers())
            
            return json_response({"status": "success", "action": action}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def get_system_stats(self, request):
        """بيانات النظام التفصيلية (للمطورين)"""
        cpu_p = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        
        return json_response({
            "cpu": cpu_p,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "pings": await StreamController.ping()
        }, headers=self._cors_headers())

    async def get_chat_queue(self, request):
        """جلب طابور الانتظار لمجموعة معينة"""
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
        except:
            return json_response({"error": "Invalid ID"}, status=400, headers=self._cors_headers())

        queue = db.get(chat_id)
        if not queue:
            return json_response({"queue": []}, headers=self._cors_headers())
        
        # تنظيف البيانات قبل إرسالها
        safe_queue = []
        for item in queue:
            safe_queue.append({
                "title": item.get("title"),
                "duration": item.get("dur"),
                "requester": item.get("by")
            })
            
        return json_response({"queue": safe_queue, "count": len(safe_queue)}, headers=self._cors_headers())

    async def play_via_api(self, request):
        """تشغيل أغنية عن طريق الـ API"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            
            if not query:
                return json_response({"error": "Query missing"}, status=400, headers=self._cors_headers())

            # البحث في يوتيوب
            details, track_id = await YouTube.track(query)
            vidid = details["vidid"]
            title = details["title"]
            
            # التنزيل
            file_path, direct = await YouTube.download(vidid, None, video=False, videoid=vidid)
            
            # الإضافة للطابور والتشغيل
            queue_item = {
                "chat_id": chat_id,
                "file": file_path if direct else f"vid_{vidid}",
                "vidid": vidid,
                "title": title,
                "dur": details["duration_min"],
                "by": "API User",
                "user_id": 0,
                "streamtype": "audio"
            }

            if chat_id in StreamController.active_calls:
                await StreamController.enqueue_track(chat_id, queue_item)
                return json_response({"status": "queued", "title": title}, headers=self._cors_headers())
            else:
                db[chat_id] = [queue_item]
                await StreamController.join_call(chat_id, chat_id, file_path, video=False)
                return json_response({"status": "playing", "title": title}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def authenticate(self, request):
        """نقطة تحقق بسيطة"""
        try:
            data = await request.json()
            if data.get("token") == BOT_TOKEN:
                return json_response({"auth": True}, headers=self._cors_headers())
            return json_response({"auth": False}, status=401, headers=self._cors_headers())
        except:
            return json_response({"error": "Bad Request"}, status=400, headers=self._cors_headers())

# تهيئة الكائن ليكون جاهزاً للاستدعاء في __main__.py
BotAPI = EnterpriseApi()
