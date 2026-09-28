"""Bounded labels; provider-reported tokens and word-based estimates are separate."""

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "insighthub_http_requests_total",
    "HTTP requests by route template",
    ["method", "endpoint", "status"],
)
rag_query_latency = Histogram(
    "insighthub_rag_query_latency_seconds",
    "RAG end-to-end latency",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
llm_call_latency = Histogram(
    "insighthub_llm_call_latency_seconds",
    "Generation latency including failures",
    buckets=(0.25, 0.5, 1, 2.5, 5, 10, 20, 60),
)
llm_tokens_total = Counter(
    "insighthub_llm_tokens_total",
    "Provider-reported LLM tokens, not billing totals",
    ["provider", "direction"],
)
embedding_tokens_total = Counter(
    "insighthub_embedding_tokens_total",
    "Provider-reported embedding tokens",
    ["provider", "input_type"],
)
embedding_estimated_tokens_total = Counter(
    "insighthub_embedding_estimated_tokens_total",
    "Word-based estimates only when provider usage is unavailable",
    ["provider", "input_type"],
)
documents_total = Gauge(
    "insighthub_documents_total",
    "Documents by status refreshed at metrics scrape",
    ["status"],
)
ingestion_errors_total = Counter(
    "insighthub_ingestion_errors_total",
    "Failed processing attempts",
)
guardrail_decisions_total = Counter(
    "insighthub_guardrail_decisions_total",
    "Bounded trust-boundary guardrail decisions",
    ["stage", "outcome", "reason"],
)


def record_embedding_usage(provider, input_type, tokens, texts):
    if tokens is not None:
        embedding_tokens_total.labels(provider, input_type).inc(tokens)
    else:
        embedding_estimated_tokens_total.labels(provider, input_type).inc(
            sum(len(text.split()) / 0.75 for text in texts)
        )
