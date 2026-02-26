#!/bin/bash
export USER=root
export DISPLAY=:1

# 1. تشغيل خادم الصوت (PulseAudio)
pulseaudio -D --exit-idle-time=-1 --system

# 2. تشغيل KasmVNC مع تحديد مسار الباسورد وربطه بالبورت 8080 عشان يفتح من متصفحك مباشرة
vncserver :1 -depth 24 -geometry 1280x720 -websocketPort 8080 -cert /etc/ssl/certs/ssl-cert-snakeoil.pem -key /etc/ssl/private/ssl-cert-snakeoil.key -Listen 0.0.0.0 -passwd /root/.vnc/passwd &
sleep 3

# 3. تشغيل واجهة الكمبيوتر (XFCE)
startxfce4 &

# 4. تشغيل بوت التليجرام الخاص بك
python3 run.py
