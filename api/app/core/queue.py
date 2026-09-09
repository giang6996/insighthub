"""Queue abstractions for Day 1 async ingestion.

This module is intentionally small and separated from ingestion logic:
- Redis/ARQ holds job metadata only (no document bytes, no RAG logic).
- The worker reuses app.services.ingestion.process_document() unchanged.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.staging import parse_content_ref

INGESTION_JOB_NAME = "ingest_document"


def redis_url() -> str:
    return get_settings().redis_url


def ingestion_queue_name() -> str:
    return get_settings().ingestion_queue


def ingestion_job_id(document_id: int, *, content_ref: str) -> str:
    """Deterministic job id for idempotent enqueue.

    Includes the payload digest (embedded in content_ref) so different uploads
    for the same document id can be queued distinctly when needed.
    """
    ref_id, digest = parse_content_ref(content_ref)
    if ref_id != document_id:
        raise ValueError("content_ref does not match document_id")
    return f"ingest:{document_id}:{digest}"


def build_ingestion_job_payload(document_id: int, *, content_ref: str) -> tuple:
    """Small internal metadata only; never include document bytes."""
    ref_id, _ = parse_content_ref(content_ref)
    if ref_id != document_id:
        raise ValueError("content_ref does not match document_id")
    return (document_id, content_ref)


async def enqueue_ingestion_job(
    document_id: int, *, content_ref: str, job_id_override: str | None = None
) -> str | None:
    """Enqueue the ingestion job via ARQ.

    This helper is intentionally not wired into `POST /documents` yet.
    It imports ARQ lazily so the API can run without ARQ installed until the
    contract change to async ingestion is approved.
    """
    try:
        from arq.connections import RedisSettings, create_pool
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "ARQ is not installed in the API environment yet; install it when wiring async ingestion."
        ) from exc
    settings = get_settings()
    payload = build_ingestion_job_payload(document_id, content_ref=content_ref)
    job_id = job_id_override or ingestion_job_id(document_id, content_ref=content_ref)
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(
            INGESTION_JOB_NAME,
            *payload,
            _job_id=job_id,
            _queue_name=settings.ingestion_queue,
        )
        return job.job_id if job is not None else None
    finally:
        await redis.aclose()
