#!/bin/bash
export USER=root
export HOME=/root

# 1. تشغيل خادم الصوت كمسؤول عشان يغذي اللينكس كله
pulseaudio -D --exit-idle-time=-1 --system

# 2. اللغز اتحل هنا: هنعمل يوزر عادي اسمه boda عشان KasmVNC يرضى يدخله من الويب
useradd -m -s /bin/bash boda
usermod -aG audio,video boda

# 3. إعداد KasmVNC لليوزر boda
mkdir -p /home/boda/.vnc
cat <<EOF > /home/boda/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 4. إعداد ملف الواجهة لليوزر boda
cat <<EOF > /home/boda/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /home/boda/.vnc/xstartup

# 5. عمل الباسورد (123456) لليوزر boda
su - boda -c "echo -e '123456\n123456\n' | kasmvncpasswd -u boda -w /home/boda/.kasmpasswd"
su - boda -c "chmod 600 /home/boda/.kasmpasswd"

# 6. إعطاء اليوزر boda ملكية ملفاته عشان ميرفضش الاتصال
chown -R boda:boda /home/boda/.vnc

# 7. تشغيل بوت التليجرام الخاص بيك كـ root في الخلفية 
cd /app
python3 run.py &

# 8. تشغيل KasmVNC باستخدام اليوزر boda (وبكده تخطينا حظر الـ root تماماً)
su - boda -c "vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg"
