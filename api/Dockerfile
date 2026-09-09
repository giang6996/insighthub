# InsightHub API - multi-stage Dockerfile
# Day 3: học viên có thể dùng AI tối ưu image này thêm (distroless, layer cache...)
FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
# Day 1 async ingestion infra: API needs ARQ client to enqueue jobs.
# Keep this separate from hashed requirements to minimize churn in the starter lockfile.
RUN pip install --no-cache-dir arq==0.26.3 redis==5.0.8

FROM base AS runtime
# Non-root user
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser appuser
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser tests ./tests
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/readyz', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
