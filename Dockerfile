# ============================================================
# 🚀 AnnieXBoda 2026 - Ultimate "Amsterdam" Edition
# Optimized for Python 3.14.3, Speed & 30k+ Heavy Traffic
# ============================================================

# 1. استخدام أحدث نسخة مستقرة من بايثون 14 (صدرت في 3 فبراير 2026)
FROM python:3.14-slim

# 2. إعدادات المحرك الخارقة
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # تفعيل الـ JIT Compiler الجديد في بايثون 14 لسرعة معالجة الرابط
    PYTHON_JIT=on \
    # إعدادات الـ UV لسرعة التحميل والتثبيت
    UV_PROJECT_ENVIRONMENT="/usr/local" \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:${PATH}"

WORKDIR /app

# 3. تثبيت "ترسانة" الأدوات (بأقل حجم للـ Image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg curl unzip ca-certificates findutils \
    # aria2 بتسرع تحميل الأغاني من يوتيوب مع yt-dlp جداً
    aria2 \
    # أدوات البناء الأساسية للمكتبات التقيلة
    build-essential libffi-dev libssl-dev && \
    \
    # 🟢 Node.js 21 (المحرك الأول لفك تشفير يوتيوب)
    curl -fsSL https://deb.nodesource.com/setup_21.x | bash - && \
    apt-get install -y nodejs && \
    \
    # 🦕 Deno (المحرك الثاني والأسرع في 2026 لفك الشفرات)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # ⚡ تثبيت UV (أسرع Package Manager في العالم)
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.cargo/bin/uv /usr/local/bin/ && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 4. إدارة المكتبات (The UV Way - أسرع 10 مرات من pip)
COPY requirements.txt .
COPY pytgcalls /app/pytgcalls

# تثبيت المكتبات مع تجاهل المتعارض وتحسين الـ Cache
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt && \
    # مكتبات الأداء العالي (نزل لها تحديثات في فبراير 2026)
    uv pip install --no-cache ntgcalls>=2.1.0 py-tgcalls>=2.2.11 uvloop>=0.22.1 g4f curl_cffi

# 5. نقل الكود وتجهيز النظام
COPY . .

# تحسين أداء نظام الملفات لـ 30 ألف مستخدم (زيادة الـ File Descriptors)
RUN echo "* soft nofile 1048576" >> /etc/security/limits.conf && \
    echo "* hard nofile 1048576" >> /etc/security/limits.conf

# 6. انطلاق "الوحش"
# استخدام python3 مباشرة للاستفادة من الـ JIT المفعل في ENV
CMD ["python3", "run.py"]
