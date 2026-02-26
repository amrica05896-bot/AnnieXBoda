#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح أي ملفات كاش قديمة بتعمل تعارض وتمنع السيرفر يشتغل
rm -rf /tmp/.X* /tmp/.x*

# 2. تشغيل خادم الصوت
pulseaudio -D --exit-idle-time=-1 --system

# 3. إجبار KasmVNC إنه يفتح بورت 8080 للعامة (0.0.0.0) وبدون SSL
mkdir -p /etc/kasmvnc /root/.kasmvnc
cat <<EOF > /etc/kasmvnc/kasmvnc.yaml
network:
  protocol: ipv4
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
desktop:
  session: xfce4-session
EOF
cp /etc/kasmvnc/kasmvnc.yaml /root/.kasmvnc/kasmvnc.yaml

# 4. إعداد الباسورد (123456)
echo -e "123456\n123456\n" | kasmvncpasswd -u root -w

# 5. تشغيل بوت التليجرام في الخلفية
python3 run.py &

# 6. تشغيل KasmVNC في الواجهة (-fg) وده أهم أمر عشان السيرفر ميقفلش
vncserver :1 -depth 24 -geometry 1280x720 -fg
