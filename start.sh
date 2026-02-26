#!/bin/bash
export USER=root
export DISPLAY=:1

# 1. تشغيل خادم الصوت (PulseAudio)
pulseaudio -D --exit-idle-time=-1 --system

# 2. إنشاء مجلد الشهادات الوهمية (مهم جداً عشان kasmvnc ميطلبش تفاعل)
mkdir -p /etc/kasmvnc/certs
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout /etc/kasmvnc/certs/kasmvnc.key -out /etc/kasmvnc/certs/kasmvnc.pem -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# 3. إنشاء ملف إعدادات kasmvnc (عشان نحدد البورت والباسورد بصمت)
mkdir -p /etc/kasmvnc
cat <<EOF > /etc/kasmvnc/kasmvnc.yaml
network:
  websocket_port: 8080
  ssl:
    require_ssl: true
    pem_certificate: /etc/kasmvnc/certs/kasmvnc.pem
    pem_key: /etc/kasmvnc/certs/kasmvnc.key
desktop:
  session: xfce4-session
EOF

# 4. تشغيل kasmvncserver في الخلفية بصيغة صامتة
kasmvncserver :1 -depth 24 -geometry 1280x720 -DisconnectClients=0 &
sleep 5

# 5. تشغيل واجهة الكمبيوتر (XFCE)
startxfce4 &

# 6. تشغيل بوت التليجرام الخاص بك
python3 run.py
