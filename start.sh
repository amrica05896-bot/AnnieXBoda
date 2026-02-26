#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح أي ملفات قفل قديمة عشان السيرفر يفتح بنضافة
rm -rf /tmp/.X* /tmp/.x*

# 2. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد ملف KasmVNC في "المسار الصحيح" اللي السيرفر كان بيدور عليه
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: ipv4
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
desktop:
  session: xfce
EOF

# 4. إعداد ملف xstartup احتياطي عشان نأكد عليه
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 5. إعداد الباسورد (123456)
echo -e "123456\n123456\n" | kasmvncpasswd -u root -w

# 6. تشغيل بوت التليجرام (AnnieXBoda) في الخلفية
python3 run.py &

# 7. تشغيل KasmVNC مع إجباره المباشر على اختيار واجهة xfce
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg
