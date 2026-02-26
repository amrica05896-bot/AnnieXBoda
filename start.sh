#!/bin/bash
export USER=root
export HOME=/root
export DISPLAY=:1

# 1. مسح أي ملفات كاش قديمة عشان نبدأ على نضافة
rm -rf /tmp/.X* /tmp/.x* /root/.kasmpasswd /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل خادم الصوت (عشان يوتيوب والألعاب)
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

# 5. اللغز اتحل هنا: إنشاء مستخدم admin حقيقي داخل نظام لينكس نفسه الأول
useradd -m -s /bin/bash admin
echo "admin:123456" | chpasswd

# 6. ربط مستخدم اللينكس admin بـ KasmVNC وإعطائه الصلاحيات
echo -e "123456\n123456\n" | kasmvncpasswd -u admin -wo /root/.kasmpasswd
chmod 600 /root/.kasmpasswd

# 7. تشغيل بوت التليجرام (AnnieXBoda)
python3 run.py &

# 8. تشغيل KasmVNC وإخباره بمكان ملف الباسورد اللي عملناه
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -PasswordFile /root/.kasmpasswd -fg
