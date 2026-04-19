FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/local/bin:/usr/bin:${PATH}"

WORKDIR /app

RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    build-essential cmake git curl wget unzip \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://deno.land/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN uv pip install --upgrade setuptools wheel

COPY pytgcalls /app/pytgcalls

COPY requirements.txt .

RUN grep -v -E -i '^(py-tgcalls|pytgcalls|deepai|numba|llvmlite|quimb)' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt

# 🚀 تم إزالة uvloop من هنا
RUN uv pip install --no-cache \
    g4f \
    curl_cffi

RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

RUN yt-dlp "ytsearch1:test" --dump-json > /dev/null 2>&1 || true

COPY . .

# 🚀 تم تعديل أمر التشغيل ليقوم بتشغيل الفولدر كـ Module
CMD ["python3", "-m", "AnnieXMedia"]
