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

# ==============================================================
# دالة معالجة المولدات غير المتزامنة (Async Generators)
# ==============================================================
def async_to_sync_gen(agen, loop, is_main_thread):
    async def a_next(a):
        try:
            return await a.__anext__(), False
        except StopAsyncIteration:
            return None, True

    while True:
        if is_main_thread:
            item, done = loop.run_until_complete(a_next(agen))
        else:
            item, done = asyncio.run_coroutine_threadsafe(
                a_next(agen), loop
            ).result()
        if done:
            break
        yield item

# ==============================================================
# المحول الرئيسي (The Bridge)
# ==============================================================
def async_to_sync(obj, name):
    function = getattr(obj, name)

    @functools.wraps(function)
    def async_to_sync_wrap(*args, **kwargs):
        coroutine = function(*args, **kwargs)

        # 1. محاولة الحصول على اللوب الحالي
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 2. فحص حالة اللوب (وهنا الحل للمشكلة)
        if loop.is_running():
            # ✅ الحالة الذهبية: اللوب شغال (بفضل run.py)
            # إذن: لا تغلف الأمر، رجعه زي ما هو عشان الـ await يشتغل صح
            # هذا السطر هو اللي هيشيل الـ RuntimeWarning ويخلي البوت يرد
            return coroutine
        
        # 3. لو اللوب مش شغال (حالات نادرة أو تشغيل يدوي)
        if threading.current_thread() is threading.main_thread():
            # نحن في الـ Main Thread واللوب واقف -> شغله
            if inspect.iscoroutine(coroutine):
                return loop.run_until_complete(coroutine)

            if inspect.isasyncgen(coroutine):
                return async_to_sync_gen(coroutine, loop, True)
        else:
            # نحن في Thread فرعي -> استخدم threadsafe
            if inspect.iscoroutine(coroutine):
                return asyncio.run_coroutine_threadsafe(
                    coroutine, loop
                ).result()

            if inspect.isasyncgen(coroutine):
                return async_to_sync_gen(coroutine, loop, False)

    setattr(obj, name, async_to_sync_wrap)


def wrap(source):
    for name in dir(source):
        method = getattr(source, name)

        if not name.startswith('_'):
            if inspect.iscoroutinefunction(method) or \
                    inspect.isasyncgenfunction(method):
                async_to_sync(source, name)


# تغليف الكلاسات
wrap(Methods)
wrap(CustomApi)
wrap(MtProtoClient)
wrap(MediaDevices)

# تغليف الدوال المساعدة
async_to_sync(idle_module, 'idle')
idle = getattr(idle_module, 'idle')

async_to_sync(compose_module, 'compose')
compose = getattr(compose_module, 'compose')
