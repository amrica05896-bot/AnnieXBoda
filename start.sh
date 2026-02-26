#!/bin/bash
export USER=root
export HOME=/root

# 1. تنظيف السيرفر من أي كاش قديم
rm -rf /tmp/.X* /tmp/.x* /root/.vnc/*.log /root/.vnc/*.pid

# 2. تشغيل خادم الصوت (عشان اليوتيوب والألعاب)
pulseaudio -D --exit-idle-time=-1 --system

# 3. توليد شهادة SSL الوهمية عشان السيرفر ميقفلش
make-ssl-cert generate-default-snakeoil --force-overwrite
chmod 644 /etc/ssl/private/ssl-cert-snakeoil.key

# 4. إعداد KasmVNC لفتح البورت بدون SSL
mkdir -p /root/.vnc
cat <<EOF > /root/.vnc/kasmvnc.yaml
network:
  protocol: http
  interface: 0.0.0.0
  websocket_port: 8080
  ssl:
    require_ssl: false
EOF

# 5. إعداد واجهة XFCE
cat <<EOF > /root/.vnc/xstartup
#!/bin/bash
startxfce4 &
EOF
chmod +x /root/.vnc/xstartup

# 6. تشغيل بوت التليجرام الخاص بك (AnnieXBoda) في الخلفية
cd /app
python3 run.py &

# 7. الضربة القاضية: هنبعتله رقم "2" تلقائياً عشان نجاوب على سؤاله المستفز ونجبره يفتح بدون باسورد!
echo "2" | vncserver :1 -depth 24 -geometry 1280x720 -select-de xfce -SecurityTypes None -disableBasicAuth -fg
