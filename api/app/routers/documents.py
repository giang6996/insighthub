"""Day 1: upload becomes async (202) after enqueueing; ingestion runs in the worker."""

import logging
import uuid

from fastapi import APIRouter, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.db import get_conn
from app.core.errors import (
    DocumentNotFound,
    InvalidDocument,
    QueueUnavailable,
    RetryNotAllowed,
    StagedPayloadMissing,
)
from app.core.index import check_schema, ensure_index_identity
from app.core.queue import enqueue_ingestion_job
from app.core.staging import (
    content_ref_for_document,
    read_staged_bytes,
    resolve_staged_path,
    sha256_bytes,
    stage_document_bytes,
)
from app.services.ingestion import _pipeline_id

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_EXT = (".txt", ".md", ".pdf")
logger = logging.getLogger("insighthub.documents")


@router.post("", status_code=202)
async def upload_document(file: UploadFile):
    try:
        if not file.filename or not file.filename.lower().endswith(ALLOWED_EXT):
            raise HTTPException(400, "Chỉ chấp nhận: .txt, .md, .pdf")
        if len(file.filename) > 255 or "\x00" in file.filename:
            raise HTTPException(422, "Tên file không hợp lệ.")
        content = file.file.read(get_settings().max_upload_bytes + 1)
    finally:
        file.file.close()
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(413, "File vượt quá giới hạn upload.")
    if not content:
        raise InvalidDocument()

    settings = get_settings()
    # Fast rejection for schema/identity conflicts (no provider calls).
    with get_conn() as conn:
        check_schema(conn)
        ensure_index_identity(conn, claim=False)

    digest = sha256_bytes(content)
    pipeline_id = _pipeline_id()
    with get_conn() as conn:
        document_id = conn.execute(
            "INSERT INTO documents (filename, status, content_sha256, pipeline_id) "
            "VALUES (%s, 'pending', %s, %s) RETURNING id",
            (file.filename, digest, pipeline_id),
        ).fetchone()[0]

    content_ref: str | None = None
    try:
        content_ref = stage_document_bytes(
            settings.staging_dir,
            document_id=document_id,
            content=content,
            max_bytes=settings.max_upload_bytes,
        )
        try:
            job_id = await enqueue_ingestion_job(document_id, content_ref=content_ref)
        except Exception as exc:
            logger.warning("Enqueue failed: id=%s type=%s", document_id, type(exc).__name__)
            raise QueueUnavailable() from None
        if job_id is None:
            logger.warning("Enqueue returned null job_id: id=%s", document_id)
            raise QueueUnavailable()
        return {
            "id": document_id,
            "filename": file.filename,
            "status": "pending",
        }
    except InvalidDocument:
        # Keep DB status truthful even if staging fails unexpectedly.
        if content_ref is not None:
            try:
                resolve_staged_path(
                    settings.staging_dir,
                    document_id=document_id,
                    content_ref=content_ref,
                ).unlink(missing_ok=True)
            except Exception:
                pass
        with get_conn() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            conn.execute(
                "UPDATE documents SET status = 'failed', chunk_count = 0, "
                "embedding_identity_id = NULL, error_code = %s WHERE id = %s",
                (InvalidDocument.code, document_id),
            )
        raise
    except Exception:
        # Enqueue failures must not leave an orphan pending document.
        if content_ref is not None:
            try:
                resolve_staged_path(
                    settings.staging_dir,
                    document_id=document_id,
                    content_ref=content_ref,
                ).unlink(missing_ok=True)
            except Exception:
                pass
        with get_conn() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            conn.execute(
                "UPDATE documents SET status = 'failed', chunk_count = 0, "
                "embedding_identity_id = NULL, error_code = %s WHERE id = %s",
                (QueueUnavailable.code, document_id),
            )
        raise QueueUnavailable() from None


@router.get("")
def list_documents():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, status, chunk_count, created_at, "
            "embedding_identity_id, error_code FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [
        {
            "id": r[0],
            "filename": r[1],
            "status": r[2],
            "chunk_count": r[3],
            "created_at": r[4].isoformat(),
            "embedding_identity_id": r[5],
            "error_code": r[6],
        }
        for r in rows
    ]


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int):
    with get_conn() as conn:
        result = conn.execute(
            "DELETE FROM documents WHERE id = %s RETURNING id",
            (document_id,),
        ).fetchone()
    if result is None:
        raise HTTPException(404, "Không tìm thấy tài liệu.")


@router.post("/{document_id}/retry", status_code=202)
async def retry_document(document_id: int):
    settings = get_settings()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT filename, status, error_code, content_sha256 "
            "FROM documents WHERE id = %s FOR UPDATE",
            (document_id,),
        ).fetchone()
        if row is None:
            raise DocumentNotFound()
        filename, status, previous_error_code, content_sha256 = row
        if status != "failed":
            raise RetryNotAllowed()
        if content_sha256 is None:
            raise StagedPayloadMissing()
        content_ref = content_ref_for_document(document_id, sha256=content_sha256)
        try:
            read_staged_bytes(
                settings.staging_dir,
                document_id=document_id,
                content_ref=content_ref,
                max_bytes=settings.max_upload_bytes,
            )
        except InvalidDocument:
            raise StagedPayloadMissing() from None
        conn.execute(
            "UPDATE documents SET status = 'pending', chunk_count = 0, "
            "embedding_identity_id = NULL, error_code = NULL WHERE id = %s",
            (document_id,),
        )
    try:
        job_id = await enqueue_ingestion_job(
            document_id,
            content_ref=content_ref,
            job_id_override=f"ingest-retry:{document_id}:{content_sha256}:{uuid.uuid4().hex}",
        )
    except Exception as exc:
        logger.warning(
            "Retry enqueue failed: id=%s type=%s", document_id, type(exc).__name__
        )
        with get_conn() as conn:
            conn.execute(
                "UPDATE documents SET status = 'failed', chunk_count = 0, "
                "embedding_identity_id = NULL, error_code = %s "
                "WHERE id = %s AND status = 'pending'",
                (previous_error_code, document_id),
            )
        raise QueueUnavailable() from None
    if job_id is None:
        logger.warning("Retry enqueue returned null job_id: id=%s", document_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE documents SET status = 'failed', chunk_count = 0, "
                "embedding_identity_id = NULL, error_code = %s "
                "WHERE id = %s AND status = 'pending'",
                (previous_error_code, document_id),
            )
        raise QueueUnavailable()
    return {"id": document_id, "filename": filename, "status": "pending"}
