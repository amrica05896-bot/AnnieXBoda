#!/bin/bash

# 1. إعداد باسورد لشاشة الـ VNC (الباسورد هنا 123456 وتقدر تغيره)
mkdir -p ~/.vnc
echo "123456" | vncpasswd -f > ~/.vnc/passwd
chmod 600 ~/.vnc/passwd

# 2. تشغيل سيرفر الشاشة الوهمية بحجم 1280x720
vncserver :1 -geometry 1280x720 -depth 24

# 3. ربط الشاشة بـ noVNC عشان تفتحها من المتصفح على بورت 8080
websockify --web=/usr/share/novnc/ 8080 localhost:5901 &

# 4. تشغيل بوت الموسيقى بتاعك
python3 run.py
