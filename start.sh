يكون كمبيوتر اول مخش الموقع 
#!/bin/bash

# 1. تنظيف ملفات الكاش القديمة عشان لو السيرفر عمل ريستارت الواجهة ما تعلقش
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1 /tmp/.X0-lock /tmp/.X11-unix/X0

# 2. تشغيل شاشة VNC داخلياً
vncserver :1 -geometry 1280x720 -depth 24

# 3. تشغيل الجسر (noVNC) باستخدام websockify وتوجيهه للشبكة الخارجية (0.0.0.0:8080)
# علامة & مهمة جداً عشان البوت يشتغل بعده
websockify --web=/usr/share/novnc/ 0.0.0.0:8080 localhost:5901 &

# 4. تشغيل بوت الموزيك (AnnieXBoda)
python3 run.py
