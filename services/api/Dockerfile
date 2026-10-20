FROM python:3.11-slim

# git: cloning repos to index them
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 -r requirements.txt
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home --uid 10001 sherpa && mkdir -p /data && chown sherpa /data
USER sherpa
ENV DATA_DIR=/data PYTHONPATH=/srv PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
# migrations run on startup (init_db); --proxy-headers so client IPs/HTTPS survive the load balancer
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
