"""Shared staged-upload helpers for async ingestion (Day 1).

This module intentionally contains no queue logic and no ingestion logic.
It provides a safe mapping between an internal content reference and a file
path under the configured staging directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import tempfile

from app.core.errors import InvalidDocument

_CONTENT_REF_RE = re.compile(
    r"^doc-(?P<document_id>[0-9]{1,20})-(?P<sha256>[0-9a-f]{64})\.bin$"
)


def sha256_bytes(content: bytes) -> str:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise TypeError("content must be bytes-like")
    return hashlib.sha256(bytes(content)).hexdigest()


def content_ref_for_document(document_id: int, *, sha256: str) -> str:
    if not isinstance(document_id, int) or document_id <= 0:
        raise ValueError("document_id must be a positive int")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("sha256 must be 64 lowercase hex chars")
    return f"doc-{document_id}-{sha256}.bin"


def parse_content_ref(content_ref: str) -> tuple[int, str]:
    if not isinstance(content_ref, str):
        raise ValueError("content_ref must be a string")
    match = _CONTENT_REF_RE.fullmatch(content_ref)
    if not match:
        raise ValueError("invalid content_ref format")
    return int(match.group("document_id")), match.group("sha256")


def resolve_staged_path(staging_dir: str, *, document_id: int, content_ref: str) -> Path:
    """Resolve a content ref to an on-disk path under staging_dir.

    Safety invariants:
    - content_ref is not a filesystem path and is validated against a strict pattern.
    - the resolved path must remain within staging_dir after normalization.
    - document_id must match the id encoded in content_ref.
    """
    ref_id, _ = parse_content_ref(content_ref)
    if ref_id != document_id:
        raise ValueError("content_ref does not match document_id")
    base = Path(staging_dir).resolve()
    candidate = (base / content_ref).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError("content_ref resolves outside staging_dir")
    return candidate


def read_staged_bytes(
    staging_dir: str, *, document_id: int, content_ref: str, max_bytes: int
) -> bytes:
    _, expected_digest = parse_content_ref(content_ref)
    path = resolve_staged_path(
        staging_dir, document_id=document_id, content_ref=content_ref
    )
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise InvalidDocument() from None
    if not data or len(data) > max_bytes:
        raise InvalidDocument()
    if sha256_bytes(data) != expected_digest:
        raise InvalidDocument()
    return data


def stage_document_bytes(
    staging_dir: str, *, document_id: int, content: bytes, max_bytes: int
) -> str:
    """Atomically stage document bytes and return an immutable content_ref.

    The content_ref includes the SHA-256 of the staged bytes so that a stale job
    cannot accidentally read a newer payload staged for the same document_id.
    """
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise TypeError("content must be bytes-like")
    data = bytes(content)
    if not data or len(data) > max_bytes:
        raise InvalidDocument()
    digest = sha256_bytes(data)
    content_ref = content_ref_for_document(document_id, sha256=digest)
    target = resolve_staged_path(
        staging_dir, document_id=document_id, content_ref=content_ref
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        # Immutable ref: the same ref implies the same bytes. Refuse to overwrite.
        if target.read_bytes() != data:
            raise InvalidDocument()
        return content_ref
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=str(target.parent),
        prefix=f".tmp-doc-{document_id}-",
        suffix=".bin",
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp.flush()
        tmp_name = tmp.name
    Path(tmp_name).replace(target)
    return content_ref
