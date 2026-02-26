# 1. الأساس: Ubuntu 26.04 (المستقبل)
FROM ubuntu:26.04

# ========================================================
# ⚡ UV PACKAGE MANAGER
# ========================================================
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# ========================================================
# 🚀 SYSTEM CONFIGURATION
# ========================================================
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/bin:${PATH}"

WORKDIR /app

# ========================================================
# 🛠 SYSTEM DEPENDENCIES
# ========================================================
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    software-properties-common build-essential cmake git curl wget unzip \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    # بايثون 3.13 الرسمي
    python3.13 python3.13-dev python3.13-venv \
    # Node.js
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    # Deno
    && curl -fsSL https://deno.land/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ربط Python 3.13
RUN ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python

# ========================================================
# 💉 THE FIX: REMOVE EXTERNALLY-MANAGED FLAG
# ========================================================
RUN rm -f /usr/lib/python3.13/EXTERNALLY-MANAGED

# ========================================================
# 📦 PYTHON PREP
# ========================================================
RUN uv pip install --upgrade setuptools wheel

# ========================================================
# 🧬 LOCAL PYTGCALLS
# ========================================================
COPY pytgcalls /app/pytgcalls

# ========================================================
# ⚡ INSTALL DEPENDENCIES
# ========================================================
COPY requirements.txt .

# 1. فلترة المكتبات القديمة والمحلية
RUN grep -v -E -i '^(py-tgcalls|pytgcalls|deepai|numba|llvmlite|quimb)' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt

# 2. تثبيت المكتبات السريعة
RUN uv pip install --no-cache \
    uvloop \
    g4f \
    curl_cffi

# ========================================================
# ⚙️ YOUTUBE ENGINE & CACHE WARMUP (THE SPEED FIX)
# ========================================================
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# 🔥 السر هنا: بنشغل أمر وهمي لـ yt-dlp عشان يجبره يحمل الـ ejs من جيتهاب ويخزنه في كاش الدوكر للأبد!
# ده هيوفرلك من 2 لـ 4 ثواني مع كل طلب أغنية
RUN yt-dlp "ytsearch1:test" --dump-json > /dev/null 2>&1 || true

# ========================================================
# 📂 SOURCE CODE
# ========================================================
COPY . .

# ========================================================
# 🚀 LAUNCH
# ========================================================
CMD ["python3", "run.py"]
