#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح أي ملفات قفل أو باسوردات قديمة عشان نبدأ على نضافة
rm -rf /tmp/.X* /tmp/.x* /root/.kasmpasswd /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد ملف KasmVNC (البورت 8080 وبدون SSL)
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 4. إعداد ملف xstartup 
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 5. السر هنا: هنعمل اليوزر admin ونسيب الأداة تحفظه في مسارها الافتراضي
echo -e "123456\n123456\n" | kasmvncpasswd -u admin -w

# 6. تشغيل بوت التليجرام (AnnieXBoda) في الخلفية
python3 run.py &

# 7. تشغيل KasmVNC في الواجهة
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg
