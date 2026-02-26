#!/bin/bash
export USER=root
export DISPLAY=:1

# 1. تشغيل خادم الصوت (PulseAudio)
pulseaudio -D --exit-idle-time=-1 --system

# 2. إنشاء ملف إعدادات KasmVNC ديناميكياً
cat <<EOF > /etc/kasmvnc/kasmvnc.yaml
network:
  websocket_port: 8080
  ssl:
    require_ssl: true
    pem_certificate: /etc/kasmvnc/certs/kasmvnc.pem
    pem_key: /etc/kasmvnc/certs/kasmvnc.key
desktop:
  session: xfce4-session
logging:
  level: warning
EOF

# 3. إعداد باسورد KasmVNC من المتغير البيئي (بدون تفاعل)
echo -e "${KASM_VNC_PASSWORD}\n${KASM_VNC_PASSWORD}\n" | kasmvncpasswd -u root -wo /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

# 4. تشغيل خادم KasmVNC (تجاوز الواجهة التفاعلية)
vncserver :1 -depth 24 -geometry 1280x720 -websocketPort 8080 -cert /etc/ssl/certs/ssl-cert-snakeoil.pem -key /etc/ssl/private/ssl-cert-snakeoil.key -Listen 0.0.0.0 -SecurityTypes VncAuth -PasswordFile /root/.vnc/passwd &
sleep 5

# 5. تشغيل واجهة الكمبيوتر (XFCE)
startxfce4 &

# 6. تشغيل بوت التليجرام الخاص بك
python3 run.py
