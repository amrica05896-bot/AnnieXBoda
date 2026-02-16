# 1. استخدام "الدبابة" Ubuntu 24.04 (ليست Debian وليست Slim)
FROM ubuntu:24.04

# ========================================================
# ⚡ UV PACKAGE MANAGER (محرك السرعة)
# ========================================================
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# ========================================================
# 🚀 SYSTEM CONFIGURATION
# ========================================================
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    # مسارات المحركات
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/bin:${PATH}"

WORKDIR /app

# ========================================================
# 🛠 THE ULTIMATE TOOLCHAIN (C/C++ POWER)
# ========================================================
# هنا بننزل "العدة الكاملة" عشان مكتبات C تشتغل صح
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    unzip \
    ffmpeg \
    aria2 \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    zlib1g-dev \
    libssl-dev \
    # إضافة PPA عشان ننزل أحدث بايثون 3.13 على أوبونتو
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && \
    apt-get install -y python3.13 python3.13-dev python3.13-venv \
    # تثبيت Node.js 20 (Full)
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    # تثبيت Deno (أحدث نسخة)
    && curl -fsSL https://deno.land/install.sh | sh \
    # تنظيف
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ربط python3 بـ python3.13
RUN ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python

# ========================================================
# 📦 PYTHON PREP
# ========================================================
# نستخدم uv لتثبيت setuptools بسرعة البرق
RUN uv pip install --upgrade setuptools wheel

# ========================================================
# 🧬 LOCAL PYTGCALLS (Native C Compilation)
# ========================================================
COPY pytgcalls /app/pytgcalls

# ========================================================
# ⚡ INSTALL DEPENDENCIES
# ========================================================
COPY requirements.txt .

# 1. فلترة وتثبيت المكتبات العادية
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt

# 2. تثبيت المكتبات الثقيلة + بناء pytgcalls محلياً
# بما إننا على Ubuntu Full، عملية البناء (Compilation) هتكون مثالية
RUN uv pip install --no-cache \
    uvloop \
    g4f \
    curl_cffi \
    ./pytgcalls

# ========================================================
# ⚙️ YOUTUBE ENGINE
# ========================================================
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# ========================================================
# 📂 SOURCE CODE
# ========================================================
COPY . .

# ========================================================
# 🚀 LAUNCH
# ========================================================
CMD ["python3", "run.py"]
