#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح أي ملفات قفل قديمة عشان السيرفر يفتح بنضافة
rm -rf /tmp/.X* /tmp/.x*

# 2. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد ملف KasmVNC 
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

# 5. هنا السر: هنعمل اليوزر admin بدل root عشان KasmVNC ميرفضوش
echo -e "123456\n123456\n" | kasmvncpasswd -u admin -w /root/.vnc/kasmpasswd
chmod 600 /root/.vnc/kasmpasswd

# 6. تشغيل بوت التليجرام (AnnieXBoda) في الخلفية
python3 run.py &

# 7. تشغيل KasmVNC في الواجهة 
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg
