#!/bin/bash
export USER=root
export HOME=/root

# 1. تنظيف الكاش القديم
rm -rf /tmp/.X* /tmp/.x* /root/.vnc/*.log /root/.vnc/*.pid /root/.vnc/passwd

# 2. تشغيل خادم الصوت كمسؤول
pulseaudio -D --exit-idle-time=-1 --system

# 3. توليد شهادة SSL صامتة لتجنب أي كراش أمني
make-ssl-cert generate-default-snakeoil --force-overwrite

# 4. إنشاء إعدادات KasmVNC وتوجيهها للشهادات الافتراضية
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 5. إعداد ملف واجهة XFCE
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 6. السر الحقيقي: عمل الباسورد بطريقة مباشرة للمستخدم root وإجباره يتجاهل الويزارد
echo "123456" | kasmvncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd

# 7. تشغيل بوت التليجرام الخاص بك في الخلفية
cd /app
python3 run.py &

# 8. تشغيل الواجهة بصلاحيات root مع تحديد ملف الباسورد اللي عملناه وتخطي الحماية
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -PasswordFile /root/.vnc/passwd -disableBasicAuth -fg
