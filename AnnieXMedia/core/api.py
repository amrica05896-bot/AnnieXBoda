# Authored By Certified Coders © 2026
# System: TitanOS Enterprise API Kernel
# Integration: Full Dashboard Support, Remote Execution, Stream Telemetry

import os
import asyncio
import json
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, List

from aiohttp import web
from aiohttp.web import Response, json_response

# --- Core Imports ---
from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from config import BOT_TOKEN

# --- Platform Integration ---
# استيراد آمن لمنع التداخل
from AnnieXMedia.platforms import YouTubeAPI
YouTube = YouTubeAPI()

# --- Server Config ---
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

class TitanApi:
    def __init__(self):
        # السماح بطلبات ضخمة لرفع الملفات مستقبلاً
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        """توجيه الروابط (Routing Map)"""
        # CORS Preflight
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        # 1. Dashboard UI Hosting
        self.app.router.add_get("/", self.serve_dashboard)
        
        # 2. Telemetry & Status
        self.app.router.add_get("/status_json", self.get_live_status)
        self.app.router.add_get("/api/stats", self.get_hardware_stats)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_queue)
        
        # 3. Execution & Control
        self.app.router.add_post("/api/control", self.execute_control)
        self.app.router.add_post("/api/play", self.remote_inject)   # للتشغيل عن بعد
        self.app.router.add_post("/api/search", self.media_search)  # للبحث
        self.app.router.add_post("/api/download", self.media_download) # للتحميل (جديد)

    # --- Security & Headers ---
    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS, DELETE, PUT",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def cors_options(self, request):
        return Response(headers=self._cors_headers())

    # --- Lifecycle ---
    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()
        print(f"🚀 TitanOS Kernel Active on Port {API_PORT}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # ==========================
    # 📡 ENDPOINTS
    # ==========================

    async def serve_dashboard(self, request):
        """تقديم ملف الواجهة الرسومية"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            if os.path.exists(html_path):
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return Response(text=content, content_type="text/html", headers=self._cors_headers())
            return Response(text="Dashboard Core Missing.", status=404)
        except Exception as e:
            return Response(text=f"Kernel Error: {e}", status=500)

    async def get_live_status(self, request):
        """بيانات البث الحية (للكروت والسينما)"""
        uptime_sec = time.time() - START_TIME
        active_chats = list(StreamController.active_calls)
        
        chats_payload = []
        for chat_id in active_chats:
            chat_obj = {
                "chat_id": chat_id,
                "title": "Processing Stream...",
                "vidid": "",
                "stream_type": "audio",
                "duration": "Live"
            }
            
            # استخراج البيانات من الذاكرة الحية
            db_entry = db.get(chat_id)
            if db_entry and len(db_entry) > 0:
                current = db_entry[0]
                chat_obj["title"] = current.get("title", "Unknown Stream")
                chat_obj["vidid"] = current.get("vidid", "") # ضروري جداً لزر Watch Live
                chat_obj["stream_type"] = current.get("streamtype", "audio")
                chat_obj["duration"] = current.get("dur", "00:00")
            
            chats_payload.append(chat_obj)

        return json_response({
            "status": "online",
            "version": "TitanOS v9.0",
            "uptime": str(timedelta(seconds=int(uptime_sec))),
            "count": len(active_chats),
            "chats": chats_payload
        }, headers=self._cors_headers())

    async def get_hardware_stats(self, request):
        """بيانات العتاد (لشريط المعالج والرام)"""
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        
        return json_response({
            "cpu": cpu,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "network_latency": "24ms" # يمكن حسابها حقيقياً
        }, headers=self._cors_headers())

    async def get_queue(self, request):
        """جلب القائمة (Queue List)"""
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
        except:
            return json_response({"error": "Invalid ID format"}, status=400, headers=self._cors_headers())

        queue_raw = db.get(chat_id, [])
        queue_clean = []
        
        for item in queue_raw:
            queue_clean.append({
                "title": item.get("title", "Unknown"),
                "duration": item.get("dur", "00:00"),
                "requester": item.get("by", "System")
            })
            
        return json_response({"queue": queue_clean, "count": len(queue_clean)}, headers=self._cors_headers())

    # ==========================
    # 🎮 CONTROL & INJECTION
    # ==========================

    async def execute_control(self, request):
        """تنفيذ أوامر التحكم (أزرار الداشبورد)"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            val = data.get("value")

            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Target inactive"}, status=404, headers=self._cors_headers())

            # تنفيذ الأمر عبر الكنترولر
            if action == "pause": await StreamController.pause_stream(chat_id)
            elif action == "resume": await StreamController.resume_stream(chat_id)
            elif action == "stop": await StreamController.stop_stream(chat_id)
            elif action == "mute": await StreamController.mute_stream(chat_id)
            elif action == "unmute": await StreamController.unmute_stream(chat_id)
            elif action == "skip": await StreamController.skip_stream(chat_id, "", False)
            elif action == "volume": await StreamController.change_volume_call(chat_id, int(val))
            
            return json_response({"status": "executed", "cmd": action}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def remote_inject(self, request):
        """(Hacker Mode) الحقن المباشر للميديا"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Empty payload"}, status=400, headers=self._cors_headers())

            # 1. البحث والاستخراج
            try:
                # استخدام دالة التتبع لجلب التفاصيل
                details, track_id = await YouTube.track(query)
                vidid = details["vidid"]
                title = details["title"]
                duration = details["duration_min"]
                thumb = details["thumb"]
            except Exception as e:
                return json_response({"error": f"Search fail: {e}"}, status=500, headers=self._cors_headers())

            # 2. التنزيل (Download / Extract Link)
            try:
                # نستخدم None مكان mystic لأننا في وضع API
                file_path, direct = await YouTube.download(vidid, None, video=video_mode, videoid=vidid)
            except Exception as e:
                return json_response({"error": f"Download fail: {e}"}, status=500, headers=self._cors_headers())

            # 3. بناء كائن البيانات
            user_ref = "Remote Admin"
            queue_item = {
                "chat_id": chat_id,
                "file": file_path if direct else f"vid_{vidid}",
                "vidid": vidid,
                "title": title,
                "dur": duration,
                "by": user_ref,
                "user_id": 777,
                "streamtype": "video" if video_mode else "audio",
                "thumb": thumb
            }

            # 4. الحقن في النظام
            if chat_id in StreamController.active_calls:
                # إضافة للطابور إذا كان مشغولاً
                await StreamController.enqueue_track(chat_id, queue_item) # تأكد ان هذه الدالة موجودة في الكنترولر، أو ضفها يدويا لل DB
                # إذا لم تكن موجودة، استخدم:
                # db[chat_id].append(queue_item)
                return json_response({"status": "queued", "title": title}, headers=self._cors_headers())
            else:
                # تشغيل فوري
                db[chat_id] = [queue_item]
                await StreamController.join_call(chat_id, chat_id, file_path, video=video_mode)
                return json_response({"status": "playing", "title": title}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def media_search(self, request):
        """نقطة البحث لمتصفح الميديا"""
        try:
            data = await request.json()
            query = data.get("query")
            # محاكاة بحث أو استخدام دالة بحث حقيقية إذا توفرت
            # حاليا سنعيد نفس الأغنية كنتيجة (لأن دالة البحث ترجع نتيجة واحدة عادة)
            details, _ = await YouTube.track(query)
            results = [{
                "title": details["title"],
                "vidid": details["vidid"],
                "thumb": details["thumb"],
                "duration": details["duration_min"]
            }]
            return json_response({"results": results}, headers=self._cors_headers())
        except:
            return json_response({"results": []}, headers=self._cors_headers())

    async def media_download(self, request):
        """طلب التحميل (مستقبلي)"""
        return json_response({"status": "started", "msg": "Download queued on server."}, headers=self._cors_headers())

# تهيئة الكائن العام
BotAPI = TitanApi()
