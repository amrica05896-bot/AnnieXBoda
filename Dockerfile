# ============================================================
# 🚀 AnnieXBoda 2026 - Python 3.14.3 (Compatibility Fix)
# Fixed: Removed Legacy AI Dependencies (llvmlite/numba)
# ============================================================

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_JIT=on \
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
    # ⚡ تثبيت UV
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 🐍 تجهيز المكتبات
COPY requirements.txt .
COPY pytgcalls /app/pytgcalls

# 🛠️ الفلترة الذكية: شلنا المكتبات اللي بتسبب مشاكل مع بايثون 14
RUN grep -v -i '^py-tgcalls\|pytgcalls\|deepai\|numba\|llvmlite\|quimb' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt && \
    uv pip install --no-cache uvloop g4f curl_cffi

# نقل الكود
COPY . .

# 🛡️ إعدادات الضغط العالي
RUN echo "* soft nofile 1048576" >> /etc/security/limits.conf && \
    echo "* hard nofile 1048576" >> /etc/security/limits.conf

# 🚀 انطلاق المحرك
CMD ["python3", "run.py"]
