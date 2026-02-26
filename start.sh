#!/bin/bash
export USER=root
export HOME=/root

# 1. حل مشكلة الكراش بتاعت الشهادة عشان السيرفر ميقفلش (مجربة ومضمونة)
make-ssl-cert generate-default-snakeoil --force-overwrite
chmod 644 /etc/ssl/private/ssl-cert-snakeoil.key

# 2. تشغيل الصوت (مهم عشان اليوتيوب والألعاب)
pulseaudio -D --exit-idle-time=-1 --system

# 3. إعداد KasmVNC لفتح البورت بدون SSL
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 4. إعداد واجهة XFCE
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 5. تشغيل بوت التليجرام بتاعك في الخلفية 
cd /app
python3 run.py &

# 6. الضربة القاضية: تشغيل KasmVNC مع إضافة الكود السري (-disableBasicAuth) لإلغاء الدوامة نهائياً!
vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -disableBasicAuth -SecurityTypes None -fg
