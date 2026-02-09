
# ==========================================
# 🚀 AnnieXBoda 2026 - Streamlined Version
# Optimized for Speed & Light Deployment
# ==========================================

FROM python:3.12-slim

# التحسينات الأساسية للمحرك (بايثون 3.13 الخام)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_JIT=on \
    PIP_NO_CACHE_DIR=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:${PATH}"

WORKDIR /app

# تثبيت الأدوات الأساسية فقط (FFmpeg هو العمود الفقري)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ffmpeg curl unzip ca-certificates findutils \
        # بنحتاج دول لبعض مكتبات بايثون اللي بتجمع نفسها
        build-essential libffi-dev libssl-dev && \
    \
    # 🟢 Node.js (عشان محرك تشفير يوتيوب)
    curl -fsSL https://deb.nodesource.com/setup_21.x | bash - && \
    apt-get install -y nodejs && \
    \
    # 🦕 Deno (أسرع حل لفك شفرات يوتيوب في 2026)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# تحديث أدوات بايثون
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# التعامل مع المكتبات المحلية
COPY pytgcalls /app/pytgcalls
COPY requirements.txt .

# تثبيت المكتبات (باستثناء المحلي)
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# تثبيت المحركات المساعدة
RUN pip install --no-cache-dir uvloop g4f curl_cffi

# نسخ الكود بالكامل
COPY . .

# زيادة حدود الملفات المفتوحة (عشان الـ 30 ألف مستخدم)
RUN echo "* soft nofile 1048576" >> /etc/security/limits.conf && \
    echo "* hard nofile 1048576" >> /etc/security/limits.conf

# تشغيل البوت
CMD ["python3", "run.py"]
