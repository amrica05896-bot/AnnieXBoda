import asyncio
import os
import sys

# 1. تثبيت UVLOOP كأولوية قصوى
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    print("✅ UVLOOP Activated.")
except ImportError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# 2. تعطيل نظام المزامنة في pytgcalls إجبارياً قبل التحميل
def disable_sync_wrapper():
    try:
        import pytgcalls.sync
        # جعل دالة الـ wrap لا تفعل شيئاً
        pytgcalls.sync.wrap = lambda source: None
        print("✅ Pytgcalls Sync System Disabled.")
    except Exception as e:
        print(f"⚠️ Note: {e}")

disable_sync_wrapper()

# 3. تشغيل البوت
sys.path.insert(0, os.getcwd())
from AnnieXMedia.__main__ import init

if __name__ == "__main__":
    print(f"🚀 Bot Running on Loop: {type(loop).__name__}")
    try:
        loop.run_until_complete(init())
    except KeyboardInterrupt:
        pass
