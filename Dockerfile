# ============================================================
# 🚀 AnnieXBoda 2026 - Python 3.14.3 (System-Ready)
# Fixed: UV System Python & Virtual Environment Error
# ============================================================

FROM python:3.14-slim

# إعدادات المحرك لسرعة البرق وتجنب أخطاء UV
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_JIT=on \
    # الضربة القاضية لمشكلة الـ Virtual Environment
    UV_SYSTEM_PYTHON=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/usr/local/bin:/root/.deno/bin:${PATH}"

WORKDIR /app

# 🏗️ تثبيت الترسانة الأساسية
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg curl unzip ca-certificates findutils \
    aria2 build-essential libffi-dev libssl-dev && \
    \
    # 🟢 Node.js 21
    curl -fsSL https://deb.nodesource.com/setup_21.x | bash - && \
    apt-get install -y nodejs && \
    \
    # 🦕 Deno
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # ⚡ تثبيت UV في المسار العالمي مباشرة
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 🐍 تجهيز المكتبات
COPY requirements.txt .
COPY pytgcalls /app/pytgcalls

# 🛠️ تثبيت المكتبات (باضافة --system للأمان الزائد)
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt && \
    uv pip install --no-cache uvloop g4f curl_cffi

# نقل الكود بالكامل
COPY . .

# 🛡️ إعدادات الضغط العالي لـ 30 ألف مستخدم
RUN echo "* soft nofile 1048576" >> /etc/security/limits.conf && \
    echo "* hard nofile 1048576" >> /etc/security/limits.conf

# 🚀 انطلاق المحرك
CMD ["python3", "run.py"]
