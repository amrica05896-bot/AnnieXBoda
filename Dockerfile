# استخدام أحدث وأخف نسخة مستقرة من بايثون
FROM python:3.12-slim

# تحسينات الأداء للبيئة
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # توجيه الملفات المؤقتة للرام ديسك (استغلال الـ 100 جيجا)
    TMPDIR=/dev/shm \
    DENO_INSTALL="/root/.deno" \
    PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

# 1. تثبيت أدوات النظام (تمت إضافة مكتبات الرسم الضرورية لـ OpenCV)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ffmpeg curl unzip build-essential python3-dev \
        libffi-dev libxml2-dev libxslt-dev zlib1g-dev gcc \
        # مكتبات ضرورية جداً عشان OpenCV و Pillow يشتغلوا من غير أخطاء
        libgl1 libglib2.0-0 libjpeg-dev \
        aria2 && \
    # تثبيت Node.js
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    # تثبيت Deno
    curl -fsSL https://deno.land/install.sh | sh && \
    # تنظيف
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. تحديث أدوات بايثون
RUN pip install --upgrade pip setuptools wheel

# 3. نسخ وتثبيت المكتبات (نقلنا دي الأول عشان نستفيد من الكاش)
COPY requirements.txt .
# فلترة pytgcalls عشان نثبت النسخة المحلية
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir --prefer-binary -r filtered.txt

# 4. تثبيت pytgcalls (النسخة المحلية المعدلة)
COPY pytgcalls /app/pytgcalls
# الأمر ده مهم: بيثبت المكتبة كـ Package عشان الكود يشوفها صح
RUN cd /app/pytgcalls && pip install .

# 5. إعدادات yt-dlp
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# 6. نسخ باقي ملفات البوت
COPY . .

# 7. التشغيل
CMD ["python3", "run.py"]
