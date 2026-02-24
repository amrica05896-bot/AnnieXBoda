#!/bin/bash

# 1. تنظيف ملفات الكاش القديمة
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1 /tmp/.X0-lock /tmp/.X11-unix/X0

# 2. تشغيل شاشة VNC داخلياً
vncserver :1 -geometry 1280x720 -depth 24

# 3. تشغيل الجسر (noVNC) وتوجيهه للشبكة الخارجية (التعديل هنا 🚀)
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 0.0.0.0:8080 &

# 4. تشغيل بوت الموزيك (AnnieXBoda)
python3 run.py
