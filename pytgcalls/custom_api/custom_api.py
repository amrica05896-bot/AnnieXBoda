import asyncio
import json
from json import JSONDecodeError
from typing import Callable, Optional, Dict, Any

from aiohttp import web
from aiohttp.web_request import BaseRequest

from ..exceptions import TooManyCustomApiDecorators

class CustomApi:
    def __init__(
        self,
        port: int = 24859,
    ):
        self._handler: Optional[Callable] = None
        self._app: web.Application = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._port = port

    def on_update_custom_api(self) -> Callable:
        if self._handler is None:
            def decorator(func: Callable) -> Callable:
                if self is not None:
                    self._handler = func
                return func
            return decorator
        else:
            raise TooManyCustomApiDecorators()

    def _cors_headers(self) -> Dict[str, str]:
        """Headers required for Web Dashboard Access"""
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    async def start(self):
        async def on_update(request: BaseRequest):
            # 1. Handle Preflight Request (CORS)
            if request.method == "OPTIONS":
                return web.Response(headers=self._cors_headers())

            # 2. Health Check (Ping)
            if request.path == "/ping" or request.method == "GET":
                return web.json_response(
                    {'status': 'online', 'system': 'TitanOS'}, 
                    headers=self._cors_headers()
                )

            # 3. Parse JSON
            try:
                params = await request.json()
            except JSONDecodeError:
                return web.json_response({
                    'result': 'INVALID_JSON_FORMAT_REQUEST',
                }, headers=self._cors_headers())

            # 4. Execute Handler
            if self._handler is not None:
                try:
                    if asyncio.iscoroutinefunction(self._handler):
                        result = await self._handler(params)
                    else:
                        result = self._handler(params)
                    
                    if isinstance(result, (dict, list)):
                        return web.json_response(result, headers=self._cors_headers())
                    else:
                        return web.json_response({
                            'result': 'INVALID_RESPONSE_TYPE',
                        }, headers=self._cors_headers())
                except Exception as e:
                    return web.json_response({
                        'result': 'HANDLER_ERROR',
                        'details': str(e)
                    }, status=500, headers=self._cors_headers())
            else:
                return web.json_response({
                    'result': 'NO_CUSTOM_API_DECORATOR',
                }, headers=self._cors_headers())

        # تسجيل المسارات
        self._app.router.add_post('/', on_update)
        self._app.router.add_get('/', on_update)      # للصحة
        self._app.router.add_get('/ping', on_update)  # للصحة
        self._app.router.add_options('/', on_update)  # للمتصفح

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        
        # 🔥 التعديل القاتل: التغيير من localhost إلى 0.0.0.0
        site = web.TCPSite(self._runner, '0.0.0.0', self._port)
        await site.start()
