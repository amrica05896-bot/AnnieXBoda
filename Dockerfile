# استخدام أحدث وأخف نسخة مستقرة من بايثون
FROM python:3.12-slim

# تحسينات الأداء للبيئة
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

# 1. تثبيت "محركات السرعة" وأدوات النظام
# - aria2: التحميل المتوازي (16 Cores).
# - nodejs & deno: فك تشفير وتوقيعات يوتيوب (JS Challenges).
# - ffmpeg: معالجة الصوت والفيديو.
# - build-essential & dev libs: لضمان بناء المكتبات السريعة (مثل orjson).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ffmpeg curl unzip build-essential python3-dev \
        libffi-dev libxml2-dev libxslt-dev zlib1g-dev gcc \
        aria2 && \
    # تثبيت Node.js (المحرك 1 لفك التشفير)
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    # تثبيت Deno (المحرك 2 لفك التشفير - مهم جداً حالياً لـ yt-dlp)
    curl -fsSL https://deno.land/install.sh | sh && \
    # تنظيف المخلفات لتقليل حجم الصورة
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. تحديث أدوات بايثون الأساسية
RUN pip install --upgrade pip setuptools wheel

# 3. نسخ مجلد pytgcalls (النسخة المحلية المعدلة إن وجدت)
COPY pytgcalls /app/pytgcalls

# 4. تثبيت المكتبات (مع استثناء pytgcalls لتجنب التعارض)
COPY requirements.txt .
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# 5. تثبيت مكتبات إضافية مهمة يدوياً لضمان التحديث
RUN pip install -U g4f curl_cffi orjson aiohttp[speedups] async-lru

# 6. 🔥 الضربة القاضية: إعدادات yt-dlp الإجبارية 🔥
# هذا السطر يجبر البوت على تحميل أدوات فك التشفير تلقائياً دون انتظار إذن
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# 7. نسخ باقي ملفات البوت
COPY . .

# 8. انطلاق الصاروخ 🚀
CMD ["python3", "run.py"]
