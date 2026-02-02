FROM python:3.12-slim

# إعدادات تقليل المساحة
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR=/dev/shm

WORKDIR /app

# تثبيت الأساسيات وتنظيف الكاش في نفس الخطوة
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git ffmpeg curl unzip build-essential python3-dev \
    libffi-dev libxml2-dev libxslt-dev zlib1g-dev gcc \
    libgl1 libglib2.0-0 libjpeg-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

# تثبيت المكتبات (بدون كاش نهائياً)
COPY requirements.txt .
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir --prefer-binary -r filtered.txt

# تثبيت pytgcalls المحلي
COPY pytgcalls /app/pytgcalls
RUN cd /app/pytgcalls && pip install .

# إعداد yt-dlp
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

COPY . .

CMD ["python3", "run.py"]
