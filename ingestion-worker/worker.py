"""InsightHub ingestion worker (Day 1 infrastructure slice).

Job payload must contain only internal metadata:
- document_id
- content_ref (validated token, not an arbitrary filesystem path)

The ingestion core remains app.services.ingestion.process_document().
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import sys
import time

from arq.connections import RedisSettings
from redis import Redis

from app.core.config import get_settings
from app.core.db import get_conn, initialize_database
from app.core.errors import DocumentConflict, DocumentNotFound, ServiceError
from app.core.staging import read_staged_bytes, resolve_staged_path
from app.services.ingestion import process_document

logger = logging.getLogger("insighthub.worker")


def _json_log(level: int, event: str, **fields) -> None:
    """Emit a verifier-parseable JSON log line.

    Day 1 verifier reads worker logs and expects standalone JSON per line, with:
    - event="ingestion_completed"
    - document_id matching the just-uploaded id
    - status="ready"
    - timestamp as RFC3339 with timezone
    """
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {"timestamp": timestamp, "event": event, **fields}
    line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    print(line, file=sys.stdout, flush=True)
    if level >= logging.WARNING:
        logger.log(level, line)


def _get_filename(document_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT filename FROM documents WHERE id = %s",
            (document_id,),
        ).fetchone()
    if row is None:
        raise DocumentNotFound()
    return row[0]


async def on_startup(ctx) -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    await asyncio.to_thread(initialize_database)
    await asyncio.to_thread(Redis.from_url(settings.redis_url).ping)
    _json_log(
        logging.INFO,
        "worker_started",
        queue=settings.ingestion_queue,
        staging_dir=settings.staging_dir,
    )


async def ingest_document(ctx, document_id: int, content_ref: str) -> dict:
    settings = get_settings()
    started = time.time()
    outcome = {
        "document_id": document_id,
        "status": "unknown",
        "chunk_count": None,
        "error_code": None,
        "elapsed_ms": None,
    }
    try:
        path = resolve_staged_path(
            settings.staging_dir, document_id=document_id, content_ref=content_ref
        )
        content = await asyncio.to_thread(
            read_staged_bytes,
            settings.staging_dir,
            document_id=document_id,
            content_ref=content_ref,
            max_bytes=settings.max_upload_bytes,
        )
        filename = await asyncio.to_thread(_get_filename, document_id)
        chunk_count = await asyncio.to_thread(
            process_document, document_id, filename, content
        )
        outcome.update(status="ready", chunk_count=chunk_count)
        return outcome
    except (DocumentNotFound, DocumentConflict) as exc:
        # Stale/invalid jobs must not overwrite or downgrade a valid newer document state.
        outcome.update(status="skipped", error_code=exc.code)
        return outcome
    except ServiceError as exc:
        # process_document already writes truthful terminal status for handled failures.
        outcome.update(status="failed", error_code=exc.code)
        raise
    finally:
        outcome["elapsed_ms"] = int((time.time() - started) * 1000)
        _json_log(
            logging.INFO,
            "ingestion_completed",
            document_id=outcome["document_id"],
            status=outcome["status"],
            chunk_count=outcome["chunk_count"],
            error_code=outcome["error_code"],
            elapsed_ms=outcome["elapsed_ms"],
        )


class WorkerSettings:
    functions = [ingest_document]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = get_settings().ingestion_queue
    on_startup = on_startup
    max_tries = 1
