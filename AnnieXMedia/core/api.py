# ==============================================================================
# PROJECT: OBSIDIAN KERNEL API (v18.0)
# AUTHORED BY: CERTIFIED CODERS © 2026
# SYSTEM: UNIVERSAL BRIDGE & TELEMETRY GATEWAY
# COMPATIBILITY: FLET DASHBOARD | PYTGCALLS v3.0 | NATIVE STREAM ENGINE
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

# --- استيراد أساسيات السورس ---
from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from config import BOT_TOKEN

# --- استيراد منطق البحث والتشغيل ---
from AnnieXMedia.platforms import YouTube
from AnnieXMedia.utils.stream.stream import stream  # دالة الستريم التي ترسل الأزرار

# --- إعدادات الخادم ---
API_PORT = 8080
START_TIME = time.time()

# --- التخلص من ضجيج اللوجات ---
logging.getLogger("aiohttp.access").setLevel(logging.CRITICAL)
logging.getLogger("aiohttp.server").setLevel(logging.CRITICAL)

class ObsidianAPI:
    def __init__(self):
        # تطبيق ويب يسمح بطلبات ضخمة (للمستقبل)
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()

    def _cors(self) -> Dict[str, str]:
        """إعدادات الوصول العابر للمصادر لمنع حظر المتصفحات"""
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "3600",
        }

    def setup_routes(self):
        """خريطة التوجيه العالمية - تقبل أي Method لمنع خطأ 405"""
        self.app.router.add_route('*', '/status_json', self.handle_status)
        self.app.router.add_route('*', '/api/stats', self.handle_stats)
        self.app.router.add_route('*', '/api/queue/{chat_id}', self.handle_queue)
        self.app.router.add_route('*', '/api/control', self.handle_control)
        self.app.router.add_post('/api/play', self.handle_play) # Play يفضل دائماً POST
        self.app.router.add_route('*', '/api/search', self.handle_search)
        
        # معالج شامل لطلبات OPTIONS (Preflight Requests)
        self.app.router.add_route('OPTIONS', '/{tail:.*}', self.handle_options)

    async def handle_options(self, request):
        """الرد الفوري على طلبات المتصفح التمهيدية"""
        return Response(status=204, headers=self._cors())

    # ==========================
    # 📡 DATA ENDPOINTS
    # ==========================

    async def handle_status(self, request):
        if request.method == 'OPTIONS': return await self.handle_options(request)
        
        uptime = str(timedelta(seconds=int(time.time() - START_TIME)))
        active_ids = list(StreamController.active_calls)
        chats_data = []
        
        for cid in active_ids:
            # جلب البيانات من ذاكرة البوت الحية (db)
            data = db.get(cid)
            if data and len(data) > 0:
                current = data[0]
                chats_data.append({
                    "chat_id": cid,
                    "title": current.get("title", "Unknown Stream"),
                    "vidid": current.get("vidid", ""),
                    "stream_type": current.get("streamtype", "audio"),
                    "duration": current.get("dur", "00:00")
                })
        
        return json_response({
            "status": "online",
            "uptime": uptime,
            "count": len(active_ids),
            "chats": chats_data
        }, headers=self._cors())

    async def handle_stats(self, request):
        if request.method == 'OPTIONS': return await self.handle_options(request)
        
        # بيانات العتاد المباشرة
        return json_response({
            "cpu": psutil.cpu_percent(),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        }, headers=self._cors())

    async def handle_queue(self, request):
        if request.method == 'OPTIONS': return await self.handle_options(request)
        
        chat_id = request.match_info.get("chat_id")
        try:
            cid = int(chat_id)
            q_raw = db.get(cid, [])
            clean_q = [{"title": i.get("title"), "duration": i.get("dur")} for i in q_raw]
            return json_response({"queue": clean_q}, headers=self._cors())
        except:
            return json_response({"queue": []}, headers=self._cors())

    # ==========================
    # 🎮 EXECUTION ENGINE
    # ==========================

    async def handle_control(self, request):
        if request.method == 'OPTIONS': return await self.handle_options(request)
        
        try:
            data = await request.json()
            cid = int(data.get("chat_id"))
            act = data.get("action")
            
            if cid not in StreamController.active_calls:
                return json_response({"error": "Chat inactive"}, status=404, headers=self._cors())

            if act == "pause": await StreamController.pause_stream(cid)
            elif act == "resume": await StreamController.resume_stream(cid)
            elif act == "stop": await StreamController.stop_stream(cid)
            elif act == "skip":
                check = db.get(cid)
                if check:
                    check.pop(0) # إزالة الحالي
                    if not check:
                        await StreamController.stop_stream(cid)
                    else:
                        # تشغيل التالي عبر المتحكم الأساسي لضمان السلاسة
                        await StreamController.one.stop_stream(cid)

            return json_response({"status": "ok", "cmd": act}, headers=self._cors())
        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors())

    async def handle_play(self, request):
        """الحقن المباشر للميديا واستدعاء أزرار البوت"""
        if request.method == 'OPTIONS': return await self.handle_options(request)
        
        try:
            data = await request.json()
            cid = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            # 1. إرسال رسالة انتظار (ستتحول للأزرار)
            try:
                mystic = await app.send_message(cid, "🔍 **جاري معالجة طلب OBSIDIAN...**")
            except:
                return json_response({"error": "Bot cannot talk in chat"}, status=403, headers=self._cors())

            # 2. جلب معلومات التراك
            details, tid = await YouTube.track(query)
            if not tid:
                # محاولة بحث بديلة
                search_res = await YouTube.search(query, limit=1)
                if search_res:
                    tid = search_res[0]["vidid"]
                    details, _ = await YouTube.track(tid)
                else:
                    await mystic.delete()
                    return json_response({"error": "Media not found"}, status=404, headers=self._cors())

            # 3. إطلاق دالة الستريم كمهمة خلفية (Instant Response)
            # نمرر mystic هنا لكي تقوم دالة stream بتعديلها وإضافة الأزرار
            asyncio.create_task(stream(
                None,           # Callback Query (None)
                mystic,         # الرسالة التي سيتم تعديلها
                777000,         # ID وهمي للأدمن
                details,        # كائن التفاصيل
                cid,            # Chat ID
                "Obsidian Admin",# User Name
                cid,            # Original Chat ID
                video=video_mode,
                streamtype="youtube",
                forceplay=False
            ))

            return json_response({
                "status": "bridged",
                "title": details.get("title"),
                "vidid": tid
            }, headers=self._cors())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors())

    async def handle_search(self, request):
        if request.method == 'OPTIONS': return await self.handle_options(request)
        
        try:
            data = await request.json()
            query = data.get("query")
            results = await YouTube.search(query, limit=15)
            
            clean = []
            for r in results:
                v = r.get("vidid")
                clean.append({
                    "title": r.get("title"),
                    "vidid": v,
                    "thumb": f"https://i.ytimg.com/vi/{v}/mqdefault.jpg",
                    "duration": r.get("duration", "00:00")
                })
            return json_response({"results": clean}, headers=self._cors())
        except:
            return json_response({"results": []}, headers=self._cors())

    # ==========================
    # ⚙️ SERVER STARTUP
    # ==========================

    async def start(self):
        """بدء تشغيل النواة"""
        runner = web.AppRunner(self.app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", API_PORT)
        await site.start()
        print(f"💎 OBSIDIAN KERNEL ACTIVE: PORT {API_PORT}")

# تصدير الكائن للتشغيل
BotAPI = ObsidianAPI()
