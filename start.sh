#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح أي ملفات قديمة
rm -rf /tmp/.X* /tmp/.x* /root/.kasmpasswd

# 2. تشغيل خادم الصوت (مهم جداً عشان اليوتيوب)
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد KasmVNC
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 4. إعداد ملف الواجهة
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 5. تشغيل بوت التليجرام
python3 run.py &

# 6. تشغيل KasmVNC (السر كله هنا: -SecurityTypes None هتلغي الباسورد خالص)
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -SecurityTypes None -fg
