#!/bin/bash

# 1. تنظيف ملفات الكاش القديمة عشان لو السيرفر عمل ريستارت الواجهة ما تعلقش
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1 /tmp/.X0-lock /tmp/.X11-unix/X0

# 💡 التريكة: تحويل صفحة الـ VNC لتكون هي الواجهة الرئيسية للموقع مباشرة!
cp /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# 2. تشغيل شاشة VNC داخلياً (ضفنا USER=root عشان يتأكد إنه واخد الصلاحيات)
USER=root vncserver :1 -geometry 1280x720 -depth 24

# 3. تشغيل الجسر (noVNC) باستخدام websockify وتوجيهه للشبكة الخارجية (0.0.0.0:8080)
# علامة & مهمة جداً عشان البوت يشتغل بعده في الخلفية
websockify --web=/usr/share/novnc/ 0.0.0.0:8080 localhost:5901 &

# 4. تشغيل بوت الميوزك (AnnieXBoda)
python3 run.py
