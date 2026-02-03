import asyncio
import os
import sys
import importlib

# 1. إعداد UVLOOP
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    print("✅ UVLOOP Active!")
except ImportError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# 2. حظر الـ Sync Wrapper (هذا هو الحل السحري)
# سنقوم بخداع المكتبة وإخبارها أن كل شيء 'Synced' بالفعل لتعطيل الـ coro_wrapper
def dummy_wrap(source):
    pass

try:
    # محاولة تعطيل الـ wrap قبل تحميل المكتبة
    import pytgcalls.sync
    pytgcalls.sync.wrap = dummy_wrap
    print("✅ Sync Wrapper Disabled Successfully!")
except:
    pass

# 3. إعداد المسارات واستدعاء البوت
sys.path.insert(0, os.getcwd())
from AnnieXMedia.__main__ import init

if __name__ == "__main__":
    print(f"🚀 Starting Annie Music Bot on: {type(loop).__name__}")
    try:
        loop.run_until_complete(init())
    except KeyboardInterrupt:
        pass
