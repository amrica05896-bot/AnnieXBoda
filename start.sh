#!/bin/bash
export USER=root
export HOME=/root

# 1. تشغيل خادم الصوت كمسؤول عشان يوتيوب
pulseaudio -D --exit-idle-time=-1 --system

# 2. إنشاء اليوزر boda
useradd -m -s /bin/bash boda || true
usermod -aG audio,video boda

# 3. إنشاء الشهادة الوهمية جوه مجلد اليوزر نفسه عشان اللينكس ميمنعوش من قراءتها
mkdir -p /home/boda/.vnc
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /home/boda/.vnc/cert.key -out /home/boda/.vnc/cert.pem -subj "/CN=kasm" 2>/dev/null

# 4. إعداد KasmVNC وتوجيهه للشهادة الجديدة اللي في مجلده
cat <<EOF > /home/boda/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
    pem_certificate: /home/boda/.vnc/cert.pem
    pem_key: /home/boda/.vnc/cert.key
EOF

# 5. إعداد ملف الواجهة
cat <<EOF > /home/boda/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /home/boda/.vnc/xstartup

# 6. عمل الباسورد (123456)
su - boda -c "echo -e '123456\n123456\n' | kasmvncpasswd -u boda -w /home/boda/.kasmpasswd"

# 7. إعطاء اليوزر boda ملكية كل ملفاته عشان ميرفضش الاتصال نهائياً
chown -R boda:boda /home/boda/.vnc /home/boda/.kasmpasswd
chmod 600 /home/boda/.vnc/cert.key /home/boda/.kasmpasswd

# 8. تشغيل بوت التليجرام الخاص بيك كـ root في الخلفية 
cd /app
python3 run.py &

# 9. تشغيل KasmVNC باستخدام اليوزر boda 
su - boda -c "vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg"
