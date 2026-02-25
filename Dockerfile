# 1. الأساس: Ubuntu 26.04 (النسخة الكاملة اللي طلبتها)
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
    UV_BREAK_SYSTEM_PACKAGES=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/bin:${PATH}" \
    USER=root

WORKDIR /app

# ========================================================
# 🛠 SYSTEM DEPENDENCIES & WEB GUI
# ========================================================
# تسطيب أدوات أوبونتو الكاملة مع Python 3.13
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    build-essential cmake git curl wget unzip \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    python3.13 python3.13-dev python3.13-venv \
    xfce4 xfce4-goodies tightvncserver novnc websockify chromium-browser \
    onboard dbus-x11 x11-xserver-utils xfonts-base xfonts-75dpi xfonts-100dpi \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://deno.land/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ربط Python 3.13 ليكون الأساسي ومسح ملف الحماية عشان uv يشتغل
RUN ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python && \
    rm -f /usr/lib/python3.13/EXTERNALLY-MANAGED || true

# ========================================================
# 🖥️ VNC & GUI SETUP (إعداد الواجهة وكلمة السر)
# ========================================================
RUN mkdir -p ~/.vnc && \
    echo "123456" | vncpasswd -f > ~/.vnc/passwd && \
    chmod 600 ~/.vnc/passwd

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

RUN chmod +x start.sh

EXPOSE 8080

# ========================================================
# 🚀 LAUNCH
# ========================================================
CMD ["./start.sh"]
