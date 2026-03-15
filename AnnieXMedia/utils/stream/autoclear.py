# Authored By Certified Coders © 2026
# Fixed for utils/stream/autoclear.py
# SMART RAM CACHE: Keeps files in RAM unless space runs low

import os
import shutil
from config import autoclean, DOWNLOAD_PATH

async def auto_clean(popped):
    try:
        rem = popped.get("file")
        
        # 1. تحديث قائمة التتبع (عشان القائمة متكبرش وتتقل البوت)
        if rem in autoclean:
            autoclean.remove(rem)
            
        # 2. التأكد إن مفيش روم تانية بتسمع نفس الملف دلوقتي
        count = autoclean.count(rem)
        if count == 0:
            # لو هو رابط أو مسار وهمي (مش ملف حقيقي في السيرفر)، اخرج فوراً
            if not rem or str(rem).startswith(("http", "vid_", "live_", "index_")):
                return
            
            # 🔥 نظام الكاش الذكي (Smart RAM Check) 🔥
            if os.path.exists(DOWNLOAD_PATH):
                try:
                    # فحص المساحة المتاحة في الرام (/dev/shm)
                    total, used, free = shutil.disk_usage(DOWNLOAD_PATH)
                    
                    # المعيار: سيب 5 جيجا فاضية للنظام، واستخدم الباقي كاش
                    if free > 5 * 1024 * 1024 * 1024: 
                        return # لا تمسح الملف، خليه كاش عشان يشتغل أسرع المرة الجاية
                except:
                    pass

            # 3. الحذف الاضطراري (فقط لو الرام اتملت والملف فعلاً موجود)
            try:
                if os.path.exists(rem):
                    os.remove(rem)
            except:
                pass
    except:
        pass
