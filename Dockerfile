# 1. الأساس: Ubuntu 26.04 (المستقبل)
FROM ubuntu:26.04

# ========================================================
# ⚡ UV PACKAGE MANAGER
# ========================================================
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# ========================================================
# 🚀 SYSTEM CONFIGURATION
# ========================================================
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/bin:${PATH}" \
    USER=root

WORKDIR /app

# ========================================================
# 🛠 SYSTEM DEPENDENCIES & WEB GUI
# ========================================================
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    software-properties-common build-essential cmake git curl wget unzip \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    # بايثون 3.13
    python3.13 python3.13-dev python3.13-venv \
    # أدوات الواجهة الرسومية والمتصفح وكيبورد الشاشة
    xfce4 xfce4-goodies tightvncserver novnc websockify chromium-browser \
    onboard dbus-x11 x11-xserver-utils \
    # Node.js
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    # Deno
    && curl -fsSL https://deno.land/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ربط Python 3.13
RUN ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python

RUN rm -f /usr/lib/python3.13/EXTERNALLY-MANAGED

# ========================================================
# 🖥️ VNC & GUI SETUP (إعداد الواجهة وكلمة السر)
# ========================================================
# كلمة السر للتحكم هي: 123456
RUN mkdir -p ~/.vnc && \
    echo "123456" | vncpasswd -f > ~/.vnc/passwd && \
    chmod 600 ~/.vnc/passwd

# إعداد ملف تشغيل واجهة XFCE
RUN echo "#!/bin/bash\n\
export USER=root\n\
startxfce4 &" > ~/.vnc/xstartup && \
    chmod +x ~/.vnc/xstartup

# ========================================================
# 📦 PYTHON PREP & LOCAL PYTGCALLS
# ========================================================
RUN uv pip install --upgrade setuptools wheel
COPY pytgcalls /app/pytgcalls
COPY requirements.txt .

RUN grep -v -E -i '^(py-tgcalls|pytgcalls|deepai|numba|llvmlite|quimb)' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt

RUN uv pip install --no-cache uvloop g4f curl_cffi

# ========================================================
# ⚙️ YOUTUBE ENGINE & CACHE WARMUP
# ========================================================
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf
RUN yt-dlp "ytsearch1:test" --dump-json > /dev/null 2>&1 || true

# ========================================================
# 📂 SOURCE CODE & LAUNCH SCRIPT
# ========================================================
COPY . .

# إنشاء المايسترو (start.sh) ديناميكياً لتشغيل كل شيء
RUN echo '#!/bin/bash\n\
# تنظيف ملفات الكاش للـ VNC لتجنب أخطاء إعادة التشغيل\n\
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1\n\
# 1. تشغيل شاشة VNC داخلياً\n\
vncserver :1 -geometry 1280x720 -depth 24\n\
# 2. تحويل الشاشة لموقع ويب على بورت 8080\n\
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 8080 &\n\
# 3. تشغيل بوت AnnieXBoda\n\
python3 run.py' > start.sh && \
    chmod +x start.sh

# فتح بورت 8080 لواجهة الويب
EXPOSE 8080

# ========================================================
# 🚀 LAUNCH
# ========================================================
CMD ["bash", "start.sh"]
