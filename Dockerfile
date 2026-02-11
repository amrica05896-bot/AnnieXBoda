# استخدام أحدث صورة بايثون مستقرة لعام 2026
FROM python:3.13-slim

# ===============================
# Performance & Runtime Tweaks
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# Deno مهم جداً لمكتبات الميديا الحديثة في 2026
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

# ===============================
# System Engines (Speed Core)
# ===============================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ffmpeg curl unzip build-essential python3-dev \
        libffi-dev libxml2-dev libxslt-dev zlib1g-dev gcc \
        aria2 ca-certificates && \
    \
    # Node.js (Latest LTS for 2026)
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    \
    # Deno (YouTube Cipher Engine)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# Python Core Upgrade
# ===============================
RUN pip install --upgrade pip setuptools wheel

# ===============================
# Python Libraries
# ===============================
COPY requirements.txt .

# 1. تنظيف requirements من أي نسخ قديمة لـ pytgcalls
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# 2. 🔥 تثبيت النسخة الحديثة 2.2.11 إجبارياً
RUN pip install --no-cache-dir py-tgcalls==2.2.11

# ===============================
# 🔥 Network Boosters (2026 Standard)
# ===============================
RUN pip install --no-cache-dir \
    uvloop \
    g4f \
    curl_cffi

# ===============================
# yt-dlp Global Forced Config
# ===============================
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# ===============================
# Copy Bot Source
# ===============================
COPY . .

# 🔥 هام جداً: مسح المجلد المحلي القديم عشان نعتمد على 2.2.11 اللي نزلت
RUN rm -rf /app/pytgcalls

# ===============================
# Launch 🚀
# ===============================
CMD ["python3", "run.py"]
