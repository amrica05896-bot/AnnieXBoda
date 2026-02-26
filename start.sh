#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1
export HOSTNAME=localhost

# 1. مسح الكاش القديم
rm -rf /tmp/.X* /tmp/.x* /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد الباسورد (123456)
mkdir -p /root/.vnc
echo "123456" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

# 4. إعداد ملف تشغيل واجهة XFCE
cat <<EOF > /root/.vnc/xstartup
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec startxfce4
EOF
chmod +x /root/.vnc/xstartup

# 5. تشغيل سيرفر TigerVNC
vncserver :1 -geometry 1280x720 -depth 24 -localhost no -SecurityTypes VncAuth -PasswordFile /root/.vnc/passwd

# 6. ننتظر 3 ثواني عشان السيرفر يفتح البورت براحته وميرفضش الاتصال
sleep 3

# 7. ربط VNC بمتصفح الويب (تم إضافة 0.0.0.0 عشان Fly.io تشوفه)
websockify --web /usr/share/novnc/ 0.0.0.0:8080 127.0.0.1:5901 &

# 8. تشغيل بوت التليجرام
python3 run.py
