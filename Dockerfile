# استخدام أحدث وأخف نسخة مستقرة من بايثون
FROM python:3.12-slim

# تحسينات الأداء للبيئة
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1. تثبيت "محركات السرعة" وأدوات النظام
# - aria2: عشان السرعة الجنونية (أهم حاجة كانت ناقصة).
# - nodejs: عشان فك تشفير يوتيوب الجديد.
# - ffmpeg: عشان معالجة الصوت والفيديو.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ffmpeg curl unzip build-essential python3-dev \
        libffi-dev libxml2-dev libxslt-dev zlib1g-dev gcc \
        aria2 && \
    # تثبيت Node.js (المحرك 1 لفك التشفير)
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    # تنظيف المخلفات لتقليل حجم الصورة
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. تحديث أدوات بايثون الأساسية
RUN pip install --upgrade pip setuptools wheel

# 3. نسخ مجلد pytgcalls (النسخة المحلية المعدلة)
COPY pytgcalls /app/pytgcalls

# 4. تثبيت المكتبات (مع استثناء pytgcalls لتجنب التعارض)
COPY requirements.txt .
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# 5. 🔥 الضربة القاضية: إعدادات yt-dlp الإجبارية 🔥
# هذا السطر يجبر البوت على تحميل أدوات فك التشفير تلقائياً دون انتظار إذن
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# تثبيت g4f و curl_cffi و uvloop (كما طلبت)
RUN pip install -U g4f curl_cffi uvloop

# 6. نسخ باقي ملفات البوت
COPY . .

# 7. انطلاق الصاروخ 🚀
CMD ["python3", "-m", "AnnieXMedia"]
