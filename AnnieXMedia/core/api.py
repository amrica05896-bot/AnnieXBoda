import os
import asyncio
import json
import time
import psutil
from datetime import datetime
from aiohttp import web
from aiohttp.web import Response, json_response

from AnnieXMedia import app
from AnnieXMedia.core.call import StreamController
from AnnieXMedia.misc import db
from AnnieXMedia.utils.database import get_lang
from AnnieXMedia.utils.formatters import seconds_to_min
from AnnieXMedia import YouTube
from config import BOT_TOKEN

API_PORT = 8080
API_HOST = "0.0.0.0"
START_TIME = time.time()

class EnterpriseApi:
    def __init__(self):
        self.app = web.Application(client_max_size=1024**2*100)
        self.setup_routes()
        self.runner = None
        self.site = None

    def setup_routes(self):
        self.app.router.add_options("/{tail:.*}", self.cors_options)
        
        self.app.router.add_get("/", self.serve_dashboard)
        self.app.router.add_get("/api/stats", self.get_system_stats)
        self.app.router.add_get("/api/queue/{chat_id}", self.get_chat_queue)
        
        self.app.router.add_post("/api/control", self.control_stream)
        self.app.router.add_post("/api/play", self.play_via_api)
        self.app.router.add_post("/api/auth", self.authenticate)

    async def cors_options(self, request):
        return Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        })

    def _cors_headers(self):
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await self.site.start()

    async def stop(self):
        await self.runner.cleanup()

    async def authenticate(self, request):
        try:
            data = await request.json()
            token = data.get("token")
            if token == BOT_TOKEN:
                return json_response({"status": "authenticated", "access": "granted"}, headers=self._cors_headers())
            return json_response({"error": "Unauthorized"}, status=401, headers=self._cors_headers())
        except:
            return json_response({"error": "Bad Request"}, status=400, headers=self._cors_headers())

    async def serve_dashboard(self, request):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, "dashboard.html")
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(text=content, content_type="text/html", headers=self._cors_headers())
        except Exception as e:
            return Response(text=str(e), status=500)

    async def get_system_stats(self, request):
        cpu_p = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        net = psutil.net_io_counters()
        uptime_sec = time.time() - START_TIME
        
        chats_data = []
        for chat_id in list(StreamController.active_calls):
            chat_info = {}
            chat_info["chat_id"] = chat_id
            
            check = db.get(chat_id)
            if check:
                current = check[0]
                chat_info["title"] = current.get("title", "Unknown")
                chat_info["duration"] = current.get("dur", "00:00")
                chat_info["user"] = current.get("by", "Unknown")
                chat_info["stream_type"] = current.get("streamtype", "audio")
            else:
                chat_info["title"] = "Idle / Radio"
                chat_info["duration"] = "Live"
            
            try:
                chat_info["played_time"] = await StreamController.time(chat_id)
            except:
                chat_info["played_time"] = 0
            
            chats_data.append(chat_info)

        data = {
            "system": {
                "cpu": cpu_p,
                "ram_percent": ram.percent,
                "ram_used": f"{ram.used / (1024**3):.2f} GB",
                "ram_total": f"{ram.total / (1024**3):.2f} GB",
                "net_sent": f"{net.bytes_sent / (1024**2):.2f} MB",
                "net_recv": f"{net.bytes_recv / (1024**2):.2f} MB",
                "uptime": str(timedelta(seconds=int(uptime_sec))),
            },
            "bot": {
                "active_calls": len(StreamController.active_calls),
                "chats": chats_data,
                "ping": await StreamController.ping()
            }
        }
        return json_response(data, headers=self._cors_headers())

    async def get_chat_queue(self, request):
        chat_id = request.match_info.get("chat_id")
        try:
            chat_id = int(chat_id)
        except ValueError:
            return json_response({"error": "Invalid Chat ID"}, status=400, headers=self._cors_headers())

        if chat_id not in StreamController.active_calls:
            return json_response({"status": "inactive", "queue": []}, headers=self._cors_headers())

        queue_data = db.get(chat_id)
        if not queue_data:
            return json_response({"status": "empty", "queue": []}, headers=self._cors_headers())

        formatted_queue = []
        for index, item in enumerate(queue_data):
            formatted_queue.append({
                "position": index,
                "title": item.get("title"),
                "duration": item.get("dur"),
                "requester": item.get("by"),
                "stream_type": item.get("streamtype")
            })

        return json_response({"status": "active", "count": len(formatted_queue), "queue": formatted_queue}, headers=self._cors_headers())

    async def control_stream(self, request):
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
            elif action == "skip":
                await StreamController.skip_stream(chat_id, "", False) 
                queue = db.get(chat_id)
                if queue and len(queue) > 0:
                    queue.pop(0)
                    if not queue:
                        await StreamController.stop_stream(chat_id)
                    else:
                        await StreamController.play(StreamController.one, chat_id)
            elif action == "stop":
                await StreamController.stop_stream(chat_id)
            elif action == "volume":
                if value is not None:
                    await StreamController.change_volume_call(chat_id, int(value))
            elif action == "mute":
                await StreamController.mute_stream(chat_id)
            elif action == "unmute":
                await StreamController.unmute_stream(chat_id)
            elif action == "seek":
                if value:
                    queue = db.get(chat_id)
                    if queue:
                        file_path = queue[0]["file"]
                        duration = queue[0]["dur"]
                        streamtype = queue[0]["streamtype"]
                        await StreamController.seek_stream(chat_id, file_path, int(value), duration, streamtype)
            else:
                return json_response({"error": "Unknown action"}, status=400, headers=self._cors_headers())

            return json_response({"status": "success", "action": action}, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def play_via_api(self, request):
        try:
            data = await request.json()
            chat_id = int(data.get("chat_id"))
            query = data.get("query")
            video_mode = bool(data.get("video", False))

            if not query:
                return json_response({"error": "Missing query"}, status=400, headers=self._cors_headers())

            try:
                if "youtube.com" in query or "youtu.be" in query:
                    details, track_id = await YouTube.track(query)
                else:
                    details, track_id = await YouTube.track(query)
                
                if not details:
                     return json_response({"error": "No results found"}, status=404, headers=self._cors_headers())

            except Exception as e:
                return json_response({"error": f"Search failed: {e}"}, status=500, headers=self._cors_headers())

            vidid = details["vidid"]
            title = details["title"]
            duration = details["duration_min"]
            thumbnail = details["thumb"]
            
            try:
                file_path, direct = await YouTube.download(vidid, None, video=video_mode, videoid=vidid)
            except Exception as e:
                return json_response({"error": f"Download failed: {e}"}, status=500, headers=self._cors_headers())

            user_name = "API Request"
            user_id = 777000 
            
            stream_type = "video" if video_mode else "audio"
            
            queue_item = {
                "chat_id": chat_id,
                "file": file_path if direct else f"vid_{vidid}",
                "vidid": vidid,
                "title": title,
                "dur": duration,
                "by": user_name,
                "user_id": user_id,
                "streamtype": stream_type,
                "thumb": thumbnail
            }

            if chat_id in StreamController.active_calls:
                await StreamController.enqueue_track(chat_id, queue_item)
                return json_response({"status": "queued", "title": title}, headers=self._cors_headers())
            else:
                db[chat_id] = [queue_item]
                try:
                    await StreamController.join_call(chat_id, chat_id, file_path, video=video_mode)
                    return json_response({"status": "playing", "title": title}, headers=self._cors_headers())
                except Exception as e:
                    return json_response({"error": f"Failed to join call: {e}"}, status=500, headers=self._cors_headers())

        except Exception as e:
            return json_response({"error": str(e)}, status=500, headers=self._cors_headers())

BotAPI = EnterpriseApi()
