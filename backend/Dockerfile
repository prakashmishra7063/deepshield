FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# ffmpeg enables MP3/M4A/OGG/FLAC decoding; libgl not needed with opencv-headless.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 deepshield
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY evaluation ./evaluation
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh && mkdir -p /data/storage && chown -R deepshield /data

ENV DS_STORAGE_DIR=/data/storage PORT=8000
EXPOSE 8000
# Starts as root only to take ownership of a freshly mounted volume, then drops to the
# unprivileged "deepshield" user. Migrations run at application startup.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
