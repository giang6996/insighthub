# Day 4 observability foundation

This directory contains only the Prometheus foundation. Grafana, rules,
Alertmanager, incidents, RCA and MLOps artifacts are intentionally deferred.

Local Compose provides Prometheus, blackbox-exporter, redis_exporter and
postgres_exporter. The API is scraped at `/metrics`; the web is probed at
`/api/health`; Redis exporter exposes the configured ARQ sorted-set queue size;
and PostgreSQL is scraped through postgres_exporter.

The Redis exporter uses `REDIS_EXPORTER_CHECK_SINGLE_KEYS`. Its
`redis_key_size` sample is relabeled to `insighthub_arq_queue_depth`. The
Compose and EKS manifests currently use the Day 1 default queue name,
`ingestion`; if `INGESTION_QUEUE` is changed, update the exporter key setting
and keep the single-key constraint.

The worker intentionally has no application metrics endpoint. In EKS, worker
and web resource/state telemetry comes from the pre-installed kube-state-metrics
and cAdvisor/node-exporter stack. The EKS manifests add exporter Services and
Prometheus Operator ServiceMonitor/Probe objects with bounded `app`, `component`,
`instance` and exporter key labels.

Prometheus retention is 15 days with a 2 GB local TSDB cap and a 512 MiB
container limit in Compose. The EKS Prometheus resource/retention policy is
owned by kube-prometheus-stack and is not duplicated here.
