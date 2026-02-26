#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 2. إنشاء إعدادات KasmVNC (إجبار الاستماع على 0.0.0.0 لتوافق Fly.io)
mkdir -p /root/.kasmvnc
cat <<EOF > /root/.kasmvnc/kasmvnc.yaml
network:
  protocol: ipv4
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
desktop:
  session: xfce4-session
EOF

# 3. إعداد الباسورد (123456)
echo -e "123456\n123456\n" | kasmvncpasswd -u root -w

# 4. مسح أي ملفات قفل قديمة (عشان لو عملت ريستارت ميحصلش Error)
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1

# 5. تشغيل خادم KasmVNC (هيشغل الواجهة تلقائياً بدون تعارض)
vncserver :1 -depth 24 -geometry 1280x720
sleep 3

# 6. تشغيل بوت التليجرام الخاص بك
python3 run.py
