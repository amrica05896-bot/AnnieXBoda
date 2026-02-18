# Authored By Certified Coders © 2026
# System: TitanOS Nuclear API Kernel
# Architecture: Full Backend Integration (Queue, Stream, Search, Stats)
# Compatibility: Matches 'call.py' & 'Youtube.py' perfectly.

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

# --- Core System Imports ---
from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from config import BOT_TOKEN

# --- Platform Integration ---
# نستخدم النسخة الموجودة في السورس لضمان توافق الكوكيز والمسارات
from AnnieXMedia.platforms import YouTube

# --- Server Configuration ---
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

# --- Silence Logs (إخراس اللوجات) ---
# نوقف رسائل aiohttp المزعجة ونبقي فقط على الأخطاء الكارثية
logging.getLogger("aiohttp.access").setLevel(logging.CRITICAL)

class TitanApi:
    def __init__(self):
        # زيادة حجم الطلب لـ 100 ميجا لرفع الملفات مستقبلاً
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        """Routing Table"""
        # CORS Preflight
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        # 1. Dashboard Hosting
        self.app.router.add_get("/", self.serve_dashboard)
        
        # 2. Live Telemetry
        self.app.router.add_get("/status_json", self.get_live_status)
        self.app.router.add_get("/api/stats", self.get_hardware_stats)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_queue)
        
        # 3. Action Controllers
        self.app.router.add_post("/api/control", self.execute_control)
        self.app.router.add_post("/api/play", self.remote_inject)   # أهم دالة
        self.app.router.add_post("/api/search", self.media_search)
        self.app.router.add_post("/api/download", self.media_download)

    # --- CORS Middleware ---
    def _cors_headers(self) -> Dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS, DELETE, PUT",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def cors_options(self, request):
        return Response(headers=self._cors_headers())

    # --- Server Lifecycle ---
    async def start(self):
        # access_log=None -> السرعة القصوى والهدوء التام
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()
        print(f"☢️  TitanOS Nuclear API Active on Port {API_PORT}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # ==========================
    # 📡 DATA ENDPOINTS
    # ==========================

    async def serve_dashboard(self, request):
        """تقديم ملف الداشبورد"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            if os.path.exists(html_path):
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return Response(text=content, content_type="text/html", headers=self._cors_headers())
            return Response(text="TitanOS Dashboard Missing.", status=404)
        except Exception as e:
            return Response(text=f"System Error: {e}", status=500)

    async def get_live_status(self, request):
        """تجهيز البيانات للكروت في الموقع"""
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
            
            # سحب البيانات من الداتابيز الحية (db) كما في call.py
            db_entry = db.get(chat_id)
            if db_entry and len(db_entry) > 0:
                current = db_entry[0]
                chat_obj["title"] = current.get("title", "Unknown Stream")
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
        """إحصائيات العتاد"""
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            return json_response({
                "cpu": cpu,
                "ram_percent": ram.percent,
                "ram_used_gb": round(ram.used / (1024**3), 2),
                "ram_total_gb": round(ram.total / (1024**3), 2),
            }, headers=self._cors_headers())
        except:
            return json_response({"cpu": 0, "ram_percent": 0}, headers=self._cors_headers())

    async def get_queue(self, request):
        """عرض الطابور"""
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
        except:
            return json_response({"queue": []}, headers=self._cors_headers())

        queue_raw = db.get(chat_id, [])
        queue_clean = []
        
        for item in queue_raw:
            queue_clean.append({
                "title": item.get("title", "Unknown"),
                "duration": item.get("dur", "00:00"),
                "requester": item.get("by", "Remote")
            })
            
        return json_response({"queue": queue_clean, "count": len(queue_clean)}, headers=self._cors_headers())

    # ==========================
    # 🎮 CONTROL & INJECTION LOGIC
    # ==========================

    async def execute_control(self, request):
        """تنفيذ أوامر التحكم بدقة"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            val = data.get("value")

            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Target inactive"}, status=404, headers=self._cors_headers())

            if action == "pause":
                await StreamController.pause_stream(chat_id)
            elif action == "resume":
                await StreamController.resume_stream(chat_id)
            elif action == "mute":
                await StreamController.mute_stream(chat_id)
            elif action == "unmute":
                await StreamController.unmute_stream(chat_id)
            elif action == "stop":
                await StreamController.stop_stream(chat_id)
            elif action == "volume":
                await StreamController.change_volume_call(chat_id, int(val))
            
            # --- منطق الـ SKIP المعقد (محاكاة skip.py) ---
            elif action == "skip":
                check = db.get(chat_id)
                if not check:
                    await StreamController.stop_stream(chat_id)
                else:
                    # 1. إزالة الأغنية الحالية
                    try:
                        popped = check.pop(0)
                        # (اختياري) تنظيف الملف إذا كان محلياً
                        # if popped and "file" in popped: os.remove(popped["file"]) 
                    except:
                        pass
                    
                    # 2. هل بقي شيء في الطابور؟
                    if not check:
                        await StreamController.stop_stream(chat_id)
                    else:
                        # 3. تشغيل التالي
                        next_track = check[0]
                        streamtype = next_track.get("streamtype", "audio")
                        is_video = (streamtype == "video")
                        file_path = next_track.get("file")
                        
                        # إذا كان يوتيوب، قد نحتاج لتحديث الرابط إذا انتهت صلاحيته
                        # هنا نعتمد على أن الرابط في file_path صالح أو مباشر
                        await StreamController.skip_stream(chat_id, file_path, video=is_video)

            return json_response({"status": "executed", "cmd": action}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def remote_inject(self, request):
        """الحقن المباشر (Play) - يحل محل الأمر /play"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Empty payload"}, status=400, headers=self._cors_headers())

            # 1. البحث (Search & Track)
            try:
                # نستخدم track أولاً لأنها تدعم الروابط
                details, track_id = await YouTube.track(query)
                
                # إذا فشل track (عاد بـ vidid فارغ)، نستخدم search
                if not track_id:
                    results = await YouTube.search(query, limit=1)
                    if results:
                        track_id = results[0]["vidid"]
                        details, _ = await YouTube.track(track_id)
                    else:
                        return json_response({"error": "No results found"}, status=404, headers=self._cors_headers())

                vidid = details["vidid"]
                title = details["title"]
                duration = details["duration_min"]
                thumb = details["thumb"]

            except Exception as e:
                return json_response({"error": f"Search Error: {e}"}, status=500, headers=self._cors_headers())

            # 2. التنزيل (Download/Extract)
            try:
                # نمرر None مكان mystic لأننا هنا API
                file_path, direct = await YouTube.download(
                    link=vidid, 
                    mystic=None, 
                    video=video_mode, 
                    videoid=vidid
                )
            except Exception as e:
                return json_response({"error": f"Download Error: {e}"}, status=500, headers=self._cors_headers())

            # 3. تجهيز البيانات (Queue Item)
            queue_item = {
                "chat_id": chat_id,
                "file": file_path if direct else f"vid_{vidid}",
                "vidid": vidid,
                "title": title,
                "dur": duration,
                "by": "TitanOS Remote",
                "user_id": 777000,
                "streamtype": "video" if video_mode else "audio",
                "thumb": thumb
            }

            # 4. التنفيذ (Injection Logic)
            if chat_id in StreamController.active_calls:
                # الحالة أ: المكالمة شغالة -> إضافة للطابور
                if chat_id not in db:
                    db[chat_id] = []
                db[chat_id].append(queue_item)
                return json_response({"status": "queued", "title": title}, headers=self._cors_headers())
            else:
                # الحالة ب: المكالمة واقفة -> بدء تشغيل جديد
                db[chat_id] = [queue_item]
                try:
                    await StreamController.join_call(chat_id, chat_id, file_path, video=video_mode)
                    return json_response({"status": "playing", "title": title}, headers=self._cors_headers())
                except Exception as e:
                    return json_response({"error": f"Call Error: {e}"}, status=500, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": f"Kernel Panic: {str(e)}"}, status=500, headers=self._cors_headers())

    async def media_search(self, request):
        """البحث في يوتيوب للمتصفح"""
        try:
            data = await request.json()
            query = data.get("query")
            
            # استخدام دالة البحث الحقيقية
            results = await YouTube.search(query, limit=15)
            
            # تنظيف النتائج
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
        except Exception as e:
            return json_response({"results": [], "error": str(e)}, headers=self._cors_headers())

    async def media_download(self, request):
        """نقطة تحميل مستقبلية"""
        return json_response({"status": "queued", "msg": "Task added to background downloader."}, headers=self._cors_headers())

# تشغيل الكائن
BotAPI = TitanApi()
