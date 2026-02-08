# استخدام أحدث وأخف نسخة مستقرة
FROM python:3.12-slim

# ===============================
# Performance & Runtime Tweaks
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

# ===============================
# System Engines (Speed Core)
# ===============================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ffmpeg curl unzip build-essential python3-dev \
        libffi-dev libxml2-dev libxslt-dev zlib1g-dev gcc g++ \
        aria2 ca-certificates findutils && \
    \
    # Node.js (YouTube Cipher Engine 1)
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    \
    # Deno (YouTube Cipher Engine 2 – مهم جدًا 2026)
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# Python Core Upgrade
# ===============================
RUN pip install --upgrade pip setuptools wheel

# ===============================
# Local pytgcalls (Custom Build)
# ===============================
COPY pytgcalls /app/pytgcalls

# ===============================
# Python Libraries
# ===============================
COPY requirements.txt .

# استبعاد pytgcalls / py-tgcalls لمنع التعارض
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# ===============================
# 🔥 UVLOOP + Network Boost
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

# ===============================
# ⚙️ Auto-Compile ALL C++ Files
# ===============================
# هذا الكود سيبحث عن أي ملف ينتهي بـ .cpp في المشروع ويحوله لمكتبة .so
RUN find . -name "*.cpp" -type f | while read file; do \
        filename=$(basename "$file" .cpp); \
        dirname=$(dirname "$file"); \
        echo "🔨 Compiling C++ File: $file ..."; \
        g++ -shared -o "$dirname/$filename.so" -fPIC "$file"; \
    done && \
    echo "✅ All C++ modules compiled successfully."

# ===============================
# Launch 🚀
# ===============================
CMD ["python3", "run.py"]
