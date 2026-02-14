# استخدام نسخة بايثون الكاملة (مش slim) لحل مشاكل المكتبات
FROM python:3.13

# ===============================
# ⚡ Environment Setup
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"
# إضافة مسار Ollama
ENV PATH="/usr/local/bin:${PATH}"
ENV OLLAMA_HOST=0.0.0.0

WORKDIR /app

# ===============================
# 🛠️ System Engines & AI Dependencies
# ===============================
# هنا مش محتاجين نثبت zstd ولا gcc لأنهم موجودين، بس هنأكد عليهم
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg aria2 nodejs npm && \
    \
    # 2. Deno (YouTube Engine)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # 3. 🤖 تثبيت Ollama (بدون مشاكل zstd)
    curl -fsSL https://ollama.com/install.sh | sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 🐍 Python Upgrades & Libraries
# ===============================
RUN pip install --upgrade pip setuptools wheel

# نسخ ملفات المكتبات وتثبيتها
COPY requirements.txt .

# استبعاد pytgcalls لمنع التعارض ثم التثبيت
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# ===============================
# 🚀 Boosters & AI Libs
# ===============================
RUN pip install --no-cache-dir \
    uvloop \
    g4f \
    curl_cffi \
    ollama

# ===============================
# 🎵 Local Libraries & Configs
# ===============================
COPY pytgcalls /app/pytgcalls

# إعدادات yt-dlp
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# نسخ باقي ملفات السورس
COPY . .

# ===============================
# 🧠 سكريبت الإقلاع الذكي (Start Script)
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
# 🏁 Launch Command
# ===============================
CMD ["./start.sh"]
