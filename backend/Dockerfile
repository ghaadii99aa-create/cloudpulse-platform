# Build from the repository root:  docker build -f backend/Dockerfile -t cloudpulse-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
COPY analytics /tmp/analytics
RUN pip install /tmp/analytics -r requirements.txt && rm -rf /tmp/analytics

COPY backend/app ./app

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin cloudpulse
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/healthz', timeout=4)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
