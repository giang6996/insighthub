# InsightHub ingestion-worker (Day 1 infrastructure slice)
# Runs independently from the API and consumes ARQ jobs from Redis.
FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Reuse the API's locked dependency set, then add ARQ for queue processing.
COPY api/requirements.txt /tmp/api-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/api-requirements.txt
COPY ingestion-worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir -r /tmp/worker-requirements.txt

# Copy only the minimal code needed to execute ingestion.
COPY api/app ./app
COPY ingestion-worker/worker.py ./worker.py

# Non-root user
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser appuser \
    && mkdir -p /data/staging \
    && chown -R appuser:appuser /data/staging /app
USER appuser

ENV STAGING_DIR=/data/staging

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os; from redis import Redis; Redis.from_url(os.environ.get('REDIS_URL','redis://redis:6379/0')).ping()" || exit 1

CMD ["arq", "worker.WorkerSettings"]

