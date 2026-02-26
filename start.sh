#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح الكاش
rm -rf /tmp/.X* /tmp/.x* /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد باسورد الـ VNC
mkdir -p /root/.vnc
echo "123456" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

# 4. إعداد ملف xstartup
cat <<EOF > /root/.vnc/xstartup
#!/bin/sh
xrdb $HOME/.Xclients
xsetroot -solid grey
export XKL_XMODMAP_DISABLE=1
/etc/X11/Xsession
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 5. تشغيل سيرفر VNC
tightvncserver :1 -geometry 1280x720 -depth 24

# 6. تشغيل noVNC (يربط بورت 8080 للعامة بالـ VNC الداخلي)
websockify --web /usr/share/novnc/ 0.0.0.0:8080 127.0.0.1:5901 &

# 7. تشغيل البوت
python3 run.py
