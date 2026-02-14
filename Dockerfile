# استخدام نسخة Slim (الأساس المتين)
FROM python:3.13-slim

# ===============================
# ⚡ إعدادات البيئة
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"
ENV PATH="/usr/local/bin:${PATH}"
ENV OLLAMA_HOST=0.0.0.0
# إصلاح سياسات ImageMagick عشان الكتابة على الفيديو تشتغل
ENV IMAGEMAGICK_BINARY="/usr/bin/convert"

WORKDIR /app

# ===============================
# 🛠️ تثبيت أدوات النظام + مكتبات الفيديو
# ===============================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        wget \
        gnupg \
        ffmpeg \
        aria2 \
        procps \
        zstd \
        unzip \
        build-essential \
        libffi-dev \
        libxml2-dev \
        libxslt-dev \
        zlib1g-dev \
        # مكتبات معالجة الفيديو والصور الضرورية
        libgl1 \
        libglib2.0-0 \
        imagemagick && \
    \
    # تعديل سياسات ImageMagick للسماح بمعالجة النصوص في الفيديو
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml && \
    \
    # 1. إعداد وتثبيت Node.js
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    \
    # 2. تثبيت Deno
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # 3. تثبيت Ollama
    curl -fsSL https://ollama.com/install.sh | sh && \
    \
    # تنظيف الكاش
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 🐍 تحديث البايثون والمكتبات
# ===============================
RUN pip install --upgrade pip setuptools wheel

# نسخ المتطلبات وتثبيتها
COPY requirements.txt .

RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# ===============================
# 🎬 تثبيت "وحوش" تعديل الفيديو (Video Editor Suite)
# ===============================
# moviepy: للمونتاج وقص ودمج الفيديو
# opencv-python-headless: لمعالجة الفريمات والرؤية الحاسوبية
# rembg[gpu]: لعزل الخلفيات بالذكاء الاصطناعي (يدعم GPU)
# numpy/pillow: لمعالجة المصفوفات والصور
RUN pip install --no-cache-dir \
    moviepy \
    opencv-python-headless \
    rembg[gpu] \
    numpy \
    pillow \
    uvloop \
    g4f \
    curl_cffi \
    ollama

# ===============================
# 🎵 ملفات البوت
# ===============================
COPY pytgcalls /app/pytgcalls

# إعدادات yt-dlp
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# نسخ باقي السورس
COPY . .

# ===============================
# 🧠 سكريبت الإقلاع (النسخة الواحدة الثابتة)
# ===============================
RUN echo '#!/bin/bash\n\
\n\
echo "🔴 [AI Engine] Starting Ollama Server..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
sleep 5\n\
\n\
echo "🔵 [AI Engine] Downloading THE KING (DeepSeek-R1 70B)..."\n\
echo "⏳ This allows H200 to focus on ONE powerful brain..."\n\
# هنا التحميل Blocking (يعني البوت مش هيشتغل غير لما الموديل يجهز 100%)
ollama pull deepseek-r1:70b\n\
echo "✅✅ [AI Engine] DeepSeek-R1 is Ready & Loaded!"\n\
\n\
echo "🎬 [Video Engine] Video Editing Suite Initialized (MoviePy + OpenCV + Rembg)"\n\
\n\
echo "🟢 [Music Bot] Starting AnnieXBoda..."\n\
python3 run.py\n\
' > start.sh && chmod +x start.sh

# ===============================
# 🏁 التشغيل
# ===============================
CMD ["./start.sh"]
