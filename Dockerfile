# استخدام نسخة Slim Bookworm (الأفضل توازناً بين الحجم والأداء)
FROM python:3.13-slim

# ===============================
# ⚡ إعدادات البيئة (تحسين الأداء)
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"
ENV PATH="/usr/local/bin:${PATH}"
ENV OLLAMA_HOST=0.0.0.0

WORKDIR /app

# ===============================
# 🛠️ تثبيت "العضلات" الناقصة (System Deps)
# ===============================
# هنا السر: بننزل zstd و gnupg و ffmpeg يدوياً عشان النسخة الـ slim تشتغل صح
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
        build-essential \
        libffi-dev \
        libxml2-dev \
        libxslt-dev \
        zlib1g-dev && \
    \
    # 1. إعداد وتثبيت Node.js (بشكل صحيح)
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    \
    # 2. تثبيت Deno
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # 3. تثبيت Ollama (دلوقتي هيلاقي zstd وهيشتغل زي الفل)
    curl -fsSL https://ollama.com/install.sh | sh && \
    \
    # تنظيف الكاش لتقليل مساحة الصورة
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 🐍 تحديث البايثون والمكتبات
# ===============================
RUN pip install --upgrade pip setuptools wheel

# نسخ المتطلبات وتثبيتها
COPY requirements.txt .

# استبعاد pytgcalls من المتطلبات لتثبيت النسخة المحلية لاحقاً
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# ===============================
# 🚀 مكتبات الذكاء والسرعة الإضافية
# ===============================
RUN pip install --no-cache-dir \
    uvloop \
    g4f \
    curl_cffi \
    ollama

# ===============================
# 🎵 نسخ ملفات البوت
# ===============================
# نسخ مكتبة المكالمات المحلية
COPY pytgcalls /app/pytgcalls

# إعدادات yt-dlp
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# نسخ باقي السورس كود
COPY . .

# ===============================
# 🧠 سكريبت الإقلاع (المايسترو)
# ===============================
# السكريبت ده بيضمن إن الـ AI يشتغل في الخلفية والبوت يشتغل في الواجهة
RUN echo '#!/bin/bash\n\
\n\
echo "🔴 [AI Engine] Starting Ollama Server..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
sleep 5\n\
\n\
echo "🟠 [AI Engine] Downloading Light Model (Llama 3.2)..."\n\
ollama pull llama3.2 > /dev/null 2>&1\n\
echo "✅ [AI Engine] Light Model Ready!"\n\
\n\
echo "🔵 [AI Engine] Downloading SUPER SMART Model (Llama 3.1:70b) in background..."\n\
(ollama pull llama3.1:70b && echo "✅✅ [AI Engine] THE BEAST (70B) IS READY!") &\n\
\n\
echo "🟢 [Music Bot] Starting AnnieXBoda..."\n\
python3 run.py\n\
' > start.sh && chmod +x start.sh

# ===============================
# 🏁 التشغيل
# ===============================
CMD ["./start.sh"]
