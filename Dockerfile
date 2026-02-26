FROM python:3.13

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_BREAK_SYSTEM_PACKAGES=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/bin:${PATH}" \
    USER=root

WORKDIR /app

# تثبيت واجهة XFCE كاملة (عشان التيرمينال والمتصفح) مع خادم الصوت PulseAudio
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    build-essential cmake git curl wget unzip gnupg \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    xfce4 xfce4-goodies dbus-x11 x11-xserver-utils xfonts-base \
    pulseaudio xvfb x11-apps pciutils \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://deno.land/install.sh | sh

# تثبيت Sunshine (لنقل الشاشة بسرعة 60 فريم)
RUN wget https://github.com/LizardByte/Sunshine/releases/latest/download/sunshine-debian-bookworm-amd64.deb -O sunshine.deb && \
    apt-get install -y ./sunshine.deb || apt-get install -f -y && \
    rm sunshine.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# تثبيت كروم (نسخة التخفي لتشغيل الألعاب)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    mv /usr/bin/google-chrome-stable /usr/bin/google-chrome-stable-orig && \
    echo '#!/bin/bash\nexec /usr/bin/google-chrome-stable-orig --no-sandbox --disable-blink-features=AutomationControlled --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36" --use-gl=angle --use-angle=swiftshader --disable-dev-shm-usage --disable-gpu-sandbox --window-size=1280,720 "$@"' > /usr/bin/google-chrome-stable && \
    chmod +x /usr/bin/google-chrome-stable

RUN rm -f /usr/lib/python3.13/EXTERNALLY-MANAGED || true

# تثبيت مكتبات بوت التليجرام الخاص بك
RUN uv pip install --upgrade setuptools wheel
COPY pytgcalls /app/pytgcalls
COPY requirements.txt .
RUN grep -v -E -i '^(py-tgcalls|pytgcalls|deepai|numba|llvmlite|quimb)' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt
RUN uv pip install --no-cache uvloop g4f curl_cffi

RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf
RUN yt-dlp "ytsearch1:test" --dump-json > /dev/null 2>&1 || true

COPY . .
RUN chmod +x start.sh

EXPOSE 8080 47984 47989 48010 47998 48000 48002
CMD ["./start.sh"]
