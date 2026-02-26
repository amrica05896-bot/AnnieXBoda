#!/bin/bash
export USER=root
export HOME=/root

# 1. حل مشكلة الشهادة الوهمية اللي بتخلي السيرفر يقفل (الضربة القاضية للخطأ الأخير)
mkdir -p /etc/ssl/private /etc/ssl/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/ssl-cert-snakeoil.key -out /etc/ssl/certs/ssl-cert-snakeoil.pem -subj "/CN=kasm"
chmod 644 /etc/ssl/private/ssl-cert-snakeoil.key

# 2. تشغيل خادم الصوت كمسؤول
pulseaudio -D --exit-idle-time=-1 --system

# 3. إنشاء اليوزر boda
useradd -m -s /bin/bash boda || true
usermod -aG audio,video boda

# 4. إعداد KasmVNC لليوزر boda
mkdir -p /home/boda/.vnc
cat <<EOF > /home/boda/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 5. إعداد ملف الواجهة
cat <<EOF > /home/boda/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /home/boda/.vnc/xstartup
chown -R boda:boda /home/boda/.vnc

# 6. عمل الباسورد (123456)
su - boda -c "echo -e '123456\n123456\n' | kasmvncpasswd -u boda -w /home/boda/.kasmpasswd"

# 7. تشغيل بوت التليجرام الخاص بيك كـ root في الخلفية 
cd /app
python3 run.py &

# 8. تشغيل KasmVNC باستخدام اليوزر boda 
su - boda -c "vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg"
