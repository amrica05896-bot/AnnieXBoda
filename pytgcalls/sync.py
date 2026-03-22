import asyncio
import functools
import inspect
import threading

from .custom_api import CustomApi
from .media_devices import MediaDevices
from .methods import Methods
from .methods.utilities import compose as compose_module
from .methods.utilities import idle as idle_module
from .mtproto import MtProtoClient


def get_main_loop():
    """
    دالة حديثة لجلب الـ Event Loop بأمان في بايثون 3.13+
    بدلاً من asyncio.get_event_loop() اللي تم التخلي عنها.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


def async_to_sync(obj, name):
    function = getattr(obj, name)

    def async_to_sync_gen(agen, loop, is_main_thread):
        """
        تم تحديثها باستخدام anext() المدمجة 
        بدلاً من بناء دالة a_next يدوية
        """
        while True:
            try:
                if is_main_thread:
                    # استخدام anext() القياسية بدلاً من await agen.__anext__()
                    item = loop.run_until_complete(anext(agen))
                else:
                    item = asyncio.run_coroutine_threadsafe(anext(agen), loop).result()
                yield item
            except StopAsyncIteration:
                break

    @functools.wraps(function)
    def async_to_sync_wrap(*args, **kwargs):
        coroutine = function(*args, **kwargs)
        
        # استدعاء اللوب ديناميكياً (Lazy Initialization)
        main_loop = get_main_loop()

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        is_main_thread = threading.current_thread() is threading.main_thread()

        # 1. لو إحنا بالفعل جوه Event Loop شغال
        if current_loop is not None and current_loop.is_running():
            if is_main_thread or current_loop is main_loop:
                return coroutine
            else:
                # استخدام isawaitable أفضل وأشمل من iscoroutine في بايثون الحديثة
                if inspect.isawaitable(coroutine):
                    async def coro_wrapper():
                        return await asyncio.wrap_future(
                            asyncio.run_coroutine_threadsafe(coroutine, main_loop)
                        )
                    return coro_wrapper()
                if inspect.isasyncgen(coroutine):
                    return coroutine 

        # 2. لو إحنا بره اللوب (Sync Context)
        if is_main_thread or not main_loop.is_running():
            target_loop = current_loop if current_loop else main_loop
            
            if inspect.isawaitable(coroutine):
                return target_loop.run_until_complete(coroutine)
            if inspect.isasyncgen(coroutine):
                return async_to_sync_gen(coroutine, target_loop, True)
        else:
            # 3. في Background Thread واللوب الأساسي شغال
            if inspect.isawaitable(coroutine):
                return asyncio.run_coroutine_threadsafe(coroutine, main_loop).result()
            if inspect.isasyncgen(coroutine):
                return async_to_sync_gen(coroutine, main_loop, False)

    setattr(obj, name, async_to_sync_wrap)


def wrap(source):
    for name in dir(source):
        method = getattr(source, name)
        if not name.startswith('_'):
            if inspect.iscoroutinefunction(method) or inspect.isasyncgenfunction(method):
                async_to_sync(source, name)


# Wrap all Client's relevant methods
wrap(Methods)
wrap(CustomApi)
wrap(MtProtoClient)
wrap(MediaDevices)

async_to_sync(idle_module, 'idle')
idle = getattr(idle_module, 'idle')

async_to_sync(compose_module, 'compose')
compose = getattr(compose_module, 'compose')
