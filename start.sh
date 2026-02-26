#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 2. إنشاء ملف إعدادات KasmVNC (لتعطيل SSL وتحديد بورت 8080)
mkdir -p /root/.kasmvnc
cat <<EOF > /root/.kasmvnc/kasmvnc.yaml
network:
  protocol: ipv4
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 3. إعداد الباسورد (123456) وإضافة اليوزر تلقائياً بدون تدخل
echo -e "123456\n123456\n" | kasmvncpasswd -u root -w

# 4. تشغيل KasmVNC (الآن لن يظهر الـ Wizard لأن الباسورد موجود)
vncserver :1 -depth 24 -geometry 1280x720 &
sleep 3

# 5. تشغيل واجهة الكمبيوتر (XFCE)
startxfce4 &

# 6. تشغيل بوت التليجرام (Run)
python3 run.py
