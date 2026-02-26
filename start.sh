#!/bin/bash
export USER=root

# 1. مسح أي كاش قديم
rm -rf /tmp/.X* /tmp/.x* /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل خادم الصوت كمسؤول (عشان يوتيوب والألعاب)
pulseaudio -D --exit-idle-time=-1 --system

# 3. إنشاء المستخدم kasmuser كما اقترحت بالضبط وإعطائه الصلاحيات
useradd -m -s /bin/bash kasmuser
echo "kasmuser:123456" | chpasswd
usermod -aG sudo,audio,video kasmuser

# 4. توليد شهادة SSL صامتة لتجنب أي كراش أمني
make-ssl-cert generate-default-snakeoil --force-overwrite
mkdir -p /home/kasmuser/.vnc
cp /etc/ssl/private/ssl-cert-snakeoil.key /home/kasmuser/.vnc/cert.key
cp /etc/ssl/certs/ssl-cert-snakeoil.pem /home/kasmuser/.vnc/cert.pem

# 5. إنشاء إعدادات KasmVNC وتوجيهها للشهادات
cat <<EOF > /home/kasmuser/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
    pem_certificate: /home/kasmuser/.vnc/cert.pem
    pem_key: /home/kasmuser/.vnc/cert.key
EOF

# 6. إعداد ملف واجهة XFCE
cat <<EOF > /home/kasmuser/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /home/kasmuser/.vnc/xstartup

# 7. السر الحقيقي: تمرير حرف 'n' في نهاية الباسورد لرفض سؤال (View-Only Password) الخفي!
su - kasmuser -c "mkdir -p ~/.vnc && echo -e '123456\n123456\nn\n' | kasmvncpasswd -u kasmuser -w"

# 8. ضبط ملكية الملفات للمستخدم kasmuser
chown -R kasmuser:kasmuser /home/kasmuser/.vnc

# 9. تشغيل بوت التليجرام الخاص بيك في الخلفية 
cd /app
python3 run.py &

# 10. تشغيل الواجهة بصلاحيات kasmuser
su - kasmuser -c "vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -fg"
