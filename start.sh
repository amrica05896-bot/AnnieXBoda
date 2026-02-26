#!/bin/bash
export USER=root
export DISPLAY=:1

# 1. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 2. تشغيل KasmVNC (بيعمل شاشة وهمية وبيشغل سيرفر الويب في نفس الوقت)
# هنستخدم بورت 8080 عشان Fly.io يفتحه مباشر من الرابط بتاعك
vncserver :1 -depth 24 -geometry 1280x720 -websocketPort 8080 -cert /etc/ssl/certs/ssl-cert-snakeoil.pem -key /etc/ssl/private/ssl-cert-snakeoil.key -Listen 0.0.0.0 &
sleep 3

# 3. تشغيل واجهة XFCE (عشان تشوف التيرمينال والمتصفح)
startxfce4 &

# 4. تشغيل بوت التليجرام
python3 run.py
