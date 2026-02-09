# ============================================================
# 🚀 AnnieXBoda 2026 - Ultimate "Amsterdam" Edition (Path Fixed)
# Optimized for Python 3.14.3, Speed & 16-Core Scaling
# ============================================================

FROM python:3.14-slim

# إعدادات المحرك لسرعة البرق
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_JIT=on \
    DENO_INSTALL="/root/.deno" \
    PATH="/usr/local/bin:/root/.deno/bin:${PATH}"

WORKDIR /app

# 🏗️ تثبيت الترسانة (FFmpeg + Node + Deno + UV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg curl unzip ca-certificates findutils \
    aria2 build-essential libffi-dev libssl-dev && \
    \
    # 🟢 Node.js 21 (YouTube Cipher Engine)
    curl -fsSL https://deb.nodesource.com/setup_21.x | bash - && \
    apt-get install -y nodejs && \
    \
    # 🦕 Deno (Fast YouTube Bypass)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # ⚡ تثبيت UV (الضربة القاضية لمشاكل المسارات)
    # إجبار المثبت على وضع الملفات في /usr/local/bin مباشرة
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 🐍 إدارة المكتبات باستخدام أسرع محرك في العالم
COPY requirements.txt .
COPY pytgcalls /app/pytgcalls

# تثبيت متطلبات السورس (بسرعة UV الخرافية)
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt && \
    # تحديث مكتبات الصوت لنسخ فبراير 2026
    uv pip install --no-cache ntgcalls>=2.1.0 py-tgcalls>=2.2.11 uvloop>=0.22.1 g4f curl_cffi

# نقل الكود بالكامل
COPY . .

# 🛡️ إعدادات الـ OS للتعامل مع 30 ألف مستخدم متزامن
RUN echo "* soft nofile 1048576" >> /etc/security/limits.conf && \
    echo "* hard nofile 1048576" >> /etc/security/limits.conf

# 🚀 انطلاق المحرك
CMD ["python3", "run.py"]
