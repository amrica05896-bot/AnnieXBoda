# Authored By Certified Coders © 2026
# System: TitanOS Enterprise Kernel (Ultimate Edition)
# Architecture: RESTful API + WebSocket Ready + Silent Logs
# Path: AnnieXMedia/core/api.py

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

# --- Platform Integration (Direct Access) ---
# نستخدم الكلاس مباشرةً لضمان عدم حدوث Circular Import
from AnnieXMedia.platforms.Youtube import YouTubeAPI
YouTube = YouTubeAPI()

# --- Server Configuration ---
API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

# --- Silence Aiohttp Logs ---
# هذا الكود يمنع ظهور رسائل الـ GET/POST المزعجة في التيرمينال
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

class TitanApi:
    def __init__(self):
        # السماح بطلبات ضخمة (100MB) لرفع الملفات مستقبلاً
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        """خريطة التوجيه (Routing Map)"""
        # 1. إعدادات CORS (للسماح للمتصفح بالاتصال)
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        # 2. استضافة الواجهة (Dashboard)
        self.app.router.add_get("/", self.serve_dashboard)
        
        # 3. بيانات الحالة (Telemetry & Status)
        self.app.router.add_get("/status_json", self.get_live_status)
        self.app.router.add_get("/api/stats", self.get_hardware_stats)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_queue)
        
        # 4. أوامر التحكم والتنفيذ (Command & Control)
        self.app.router.add_post("/api/control", self.execute_control)   # تحكم (Pause, Skip...)
        self.app.router.add_post("/api/play", self.remote_inject)       # تشغيل عن بعد
        self.app.router.add_post("/api/search", self.media_search)      # بحث يوتيوب
        self.app.router.add_post("/api/download", self.media_download)  # تحميل ملفات

    # --- Security & CORS Headers ---
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
        # 🔥 access_log=None هي السر لإخفاء الدوشة
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()
        print(f"🚀 TitanOS Kernel Active on Port {API_PORT} (Silent Mode)")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # ==========================
    # 📡 ENDPOINTS (نقاط النهاية)
    # ==========================

    async def serve_dashboard(self, request):
        """تقديم ملف الواجهة الرسومية (HTML)"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            if os.path.exists(html_path):
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return Response(text=content, content_type="text/html", headers=self._cors_headers())
            return Response(text="TitanOS Dashboard Core Missing.", status=404)
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
                "title": "Processing...",
                "vidid": "",
                "stream_type": "audio",
                "duration": "Live"
            }
            
            # استخراج البيانات من الذاكرة الحية (Redis/Mongo Cache)
            db_entry = db.get(chat_id)
            if db_entry and len(db_entry) > 0:
                current = db_entry[0]
                chat_obj["title"] = current.get("title", "Unknown Stream")
                chat_obj["vidid"] = current.get("vidid", "") # ضروري لزر Watch Live
                chat_obj["stream_type"] = current.get("streamtype", "audio")
                chat_obj["duration"] = current.get("dur", "00:00")
            
            chats_payload.append(chat_obj)

        return json_response({
            "status": "online",
            "version": "TitanOS v10.0 Ultimate",
            "uptime": str(timedelta(seconds=int(uptime_sec))),
            "count": len(active_chats),
            "chats": chats_payload
        }, headers=self._cors_headers())

    async def get_hardware_stats(self, request):
        """بيانات العتاد (لشريط المعالج والرام)"""
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
        """جلب قائمة الانتظار لجروب معين"""
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
        except:
            return json_response({"queue": []}, headers=self._cors_headers())

        queue_raw = db.get(chat_id, [])
        queue_clean = []
        
        # تنظيف البيانات قبل إرسالها للفرونت إند
        for item in queue_raw:
            queue_clean.append({
                "title": item.get("title", "Unknown"),
                "duration": item.get("dur", "00:00"),
                "requester": item.get("by", "System")
            })
            
        return json_response({"queue": queue_clean, "count": len(queue_clean)}, headers=self._cors_headers())

    # ==========================
    # 🎮 CONTROL & INJECTION (التحكم والحقن)
    # ==========================

    async def execute_control(self, request):
        """تنفيذ أوامر التحكم (Pause, Resume, Skip, etc.)"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            action = data.get("action")
            val = data.get("value")

            if chat_id not in StreamController.active_calls:
                return json_response({"error": "Target inactive"}, status=404, headers=self._cors_headers())

            # توجيه الأوامر للكنترولر
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
        """(Hacker Mode) حقن وتشغيل ميديا عن بعد"""
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Payload empty"}, status=400, headers=self._cors_headers())

            # 1. البحث والاستخراج (Search & Extract)
            try:
                # نستخدم track للحصول على التفاصيل والـ ID
                details, track_id = await YouTube.track(query)
                
                # إذا فشل track، نحاول بـ search العادي
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
                return json_response({"error": f"Search fail: {e}"}, status=500, headers=self._cors_headers())

            # 2. التنزيل (Download / Link Generation)
            try:
                # نمرر None مكان mystic لأننا هنا API وليس رسالة تيليجرام
                file_path, direct = await YouTube.download(
                    vidid, 
                    None, 
                    video=video_mode, 
                    videoid=vidid
                )
            except Exception as e:
                return json_response({"error": f"Download fail: {e}"}, status=500, headers=self._cors_headers())

            # 3. بناء كائن البيانات (Queue Item Object)
            user_ref = "TitanOS Remote"
            queue_item = {
                "chat_id": chat_id,
                "file": file_path if direct else f"vid_{vidid}",
                "vidid": vidid,
                "title": title,
                "dur": duration,
                "by": user_ref,
                "user_id": 777000, # ID وهمي للأدمن
                "streamtype": "video" if video_mode else "audio",
                "thumb": thumb
            }

            # 4. الحقن في النظام (Injection)
            if chat_id in StreamController.active_calls:
                # إذا كان الجروب شغال، نضيف للطابور
                await StreamController.enqueue_track(chat_id, queue_item)
                return json_response({"status": "queued", "title": title}, headers=self._cors_headers())
            else:
                # إذا كان الجروب فاضي، نشغل فوراً
                db[chat_id] = [queue_item]
                await StreamController.join_call(chat_id, chat_id, file_path, video=video_mode)
                return json_response({"status": "playing", "title": title}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": f"Kernel Panic: {str(e)}"}, status=500, headers=self._cors_headers())

    async def media_search(self, request):
        """البحث الحقيقي في يوتيوب (للمتصفح المدمج)"""
        try:
            data = await request.json()
            query = data.get("query")
            
            # استخدام دالة البحث الحقيقية من كلاس YouTube
            results = await YouTube.search(query, limit=12)
            
            # تنسيق النتائج للداشبورد
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
        """طلب تحميل (Placeholder للمستقبل)"""
        return json_response({"status": "queued", "msg": "Download request received."}, headers=self._cors_headers())

# تهيئة الكائن العام (Singleton)
BotAPI = TitanApi()
