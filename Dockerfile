# استخدام نسخة Slim Bookworm (خفيفة ومستقرة)
FROM python:3.13-slim-bookworm

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

WORKDIR /app

# ===============================
# 🛠️ تثبيت الأدوات الناقصة (System Deps)
# ===============================
# التعديل هنا: أضفنا unzip عشان Deno يشتغل، و zstd عشان Ollama
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
        zlib1g-dev && \
    \
    # 1. إعداد وتثبيت Node.js
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    \
    # 2. تثبيت Deno (الآن سيجد unzip وسينجح)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # 3. تثبيت Ollama (الآن سيجد zstd وسينجح)
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
# 🚀 مكتبات الذكاء الإضافية
# ===============================
RUN pip install --no-cache-dir \
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
# 🧠 سكريبت الإقلاع
# ===============================
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
