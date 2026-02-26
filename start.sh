#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. تنظيف السيرفر من أي ملفات كاش قديمة
rm -rf /tmp/.X* /tmp/.x* /root/.kasmpasswd /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل خادم الصوت (عشان يوتيوب)
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد KasmVNC لفتح بورت 8080 بدون SSL
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 4. إعداد ملف واجهة XFCE
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 5. السر هنا: إعداد يوزر اسمه kasm وباسورد 123456 في المسار اللي السيرفر بيدور فيه
echo -e "123456\n123456\n" | kasmvncpasswd -u kasm -w /root/.kasmpasswd
chmod 600 /root/.kasmpasswd

# 6. تشغيل بوت التليجرام
python3 run.py &

# 7. تشغيل KasmVNC (هيدخل يقرا ملف kasmpasswd ويشتغل فوراً بدون أسئلة)
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg
