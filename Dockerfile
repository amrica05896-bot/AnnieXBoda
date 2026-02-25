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

RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    build-essential cmake git curl wget unzip \
    ffmpeg aria2 libffi-dev libxml2-dev libxslt-dev zlib1g-dev libssl-dev \
    xfce4 xfce4-goodies tightvncserver novnc websockify chromium \
    onboard dbus-x11 x11-xserver-utils xfonts-base xfonts-75dpi xfonts-100dpi \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://deno.land/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN rm -f /usr/lib/python3.13/EXTERNALLY-MANAGED || true

RUN mkdir -p ~/.vnc && \
    echo "123456" | vncpasswd -f > ~/.vnc/passwd && \
    chmod 600 ~/.vnc/passwd

RUN echo "#!/bin/bash\n\
export USER=root\n\
startxfce4 &" > ~/.vnc/xstartup && \
    chmod +x ~/.vnc/xstartup

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

EXPOSE 8080

CMD ["./start.sh"]
