# InsightHub ChatOps Bot - Dockerfile (Day 5)
#
# Học viên có thể tối ưu thêm bằng AI ở Day 3 hoặc Day 5.
# Production cần: non-root user, multi-stage để giảm size, healthcheck.

FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

FROM node:24.14.1-bookworm-slim AS mcp-runtime
WORKDIR /opt/mcp-client
COPY chatops-bot/mcp-client/package.json .
RUN npm install --omit=dev --no-fund --no-audit \
    && npm install --global --no-fund --no-audit kubernetes-mcp-server@0.0.66
COPY chatops-bot/mcp-client/client.mjs .
COPY chatops-bot/mcp-client/prometheus.mjs .
WORKDIR /opt/insighthub-mcp
COPY tools/mcp/package.json tools/mcp/package-lock.json ./
RUN npm ci --omit=dev --no-fund --no-audit
COPY tools/mcp/src ./src

FROM base AS deps
COPY chatops-bot/requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

FROM base AS runtime
RUN groupadd --system --gid 1001 botuser \
    && useradd --system --uid 1001 --gid botuser botuser

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --chown=botuser:botuser chatops-bot/app ./app
COPY --from=mcp-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=mcp-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=mcp-runtime /opt/mcp-client /opt/mcp-client
COPY --from=mcp-runtime /opt/insighthub-mcp /opt/insighthub-mcp

USER botuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
