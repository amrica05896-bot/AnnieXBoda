FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# ضفنا هنا USER=root عشان VNC بيحتاجها عشان يشتغل
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/local/bin:/usr/bin:${PATH}" \
    USER=root 

WORKDIR /app

# ضفنا حزم الواجهة الرسومية والمتصفح هنا
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    build-essential cmake git curl wget unzip \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    xfce4 xfce4-terminal tightvncserver websockify novnc firefox-esr \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://deno.land/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN uv pip install --upgrade setuptools wheel

COPY pytgcalls /app/pytgcalls

COPY requirements.txt .

RUN grep -v -E -i '^(py-tgcalls|pytgcalls|deepai|numba|llvmlite|quimb)' requirements.txt > filtered.txt && \
    uv pip install --no-cache -r filtered.txt

RUN uv pip install --no-cache \
    uvloop \
    g4f \
    curl_cffi

RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

RUN yt-dlp "ytsearch1:test" --dump-json > /dev/null 2>&1 || true

COPY . .

# دمجنا كل الأوامر في سطر واحد هنا (الباسورد 123456)
CMD ["sh", "-c", "mkdir -p ~/.vnc && echo '123456' | vncpasswd -f > ~/.vnc/passwd && chmod 600 ~/.vnc/passwd && vncserver :1 -geometry 1280x720 -depth 24 && websockify --web=/usr/share/novnc/ 8080 localhost:5901 & python3 run.py"]
