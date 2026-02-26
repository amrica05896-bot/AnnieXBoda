#!/bin/bash
export USER=root
export HOME=/root

# 1. تنظيف السيرفر من أي كاش قديم
rm -rf /tmp/.X* /tmp/.x* /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل خادم الصوت (عشان اليوتيوب اللي كان بيقطع)
pulseaudio -D --exit-idle-time=-1 --system

# 3. توليد شهادة SSL الوهمية عشان السيرفر ميقفلش
make-ssl-cert generate-default-snakeoil --force-overwrite
chmod 644 /etc/ssl/private/ssl-cert-snakeoil.key

# 4. إعداد KasmVNC
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 5. التعديل السحري: إضافة dbus-launch لمنع سطح المكتب من الانهيار (Crash)
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_CURRENT_DESKTOP="XFCE"
exec dbus-launch --exit-with-session startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 6. تشغيل بوت التليجرام الخاص بك في الخلفية
cd /app
python3 run.py &

# 7. تشغيل KasmVNC بدون الدوامة (بإرسال رقم 2 تلقائياً)
echo "2" | vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -SecurityTypes None -disableBasicAuth -fg
