import json
import os
import time
from typing import Dict, List, Optional, Tuple
import uuid
import urllib.error
import urllib.request


API_URL = os.environ.get("INSIGHTHUB_API_URL", "http://localhost:8000").rstrip("/")


def _http(
    method: str,
    path: str,
    *,
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes]:
    url = API_URL + path
    req = urllib.request.Request(url, data=body, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            return resp.status, data
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _json(method: str, path: str, *, body: Optional[Dict] = None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json"}
    status, raw = _http(method, path, body=payload, headers=headers)
    return status, (json.loads(raw.decode("utf-8")) if raw else None)


def _multipart_upload(filename: str, content: bytes):
    boundary = "----insighthub-day1-" + uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n"
        f"\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + content + tail
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return _http("POST", "/documents", body=body, headers=headers)


def _find_doc(docs: List[Dict], doc_id: int) -> Optional[Dict]:
    for doc in docs:
        if doc.get("id") == doc_id:
            return doc
    return None


def _wait_for_terminal(doc_id: int, *, timeout_s: float = 30.0) -> Dict:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        status, docs = _json("GET", "/documents")
        assert status == 200
        last = _find_doc(docs, doc_id)
        assert last is not None
        if last.get("status") in {"ready", "failed"}:
            return last
        time.sleep(0.25)
    return last


def test_refactor_regression():
    status, _ = _http("GET", "/readyz")
    assert status == 200
    status, docs = _json("GET", "/documents")
    assert status == 200
    assert isinstance(docs, list)


def test_empty_input():
    status, _ = _multipart_upload("empty.txt", b"")
    assert status == 422


def test_duplicate_or_invalid():
    status, _ = _multipart_upload("not-allowed.exe", b"content")
    assert status == 400


def test_async_upload():
    filename = f"day1-async-{uuid.uuid4().hex}.txt"
    status, raw = _multipart_upload(filename, b"Async upload contract.")
    assert status == 202, raw.decode("utf-8", errors="replace")
    doc = json.loads(raw.decode("utf-8"))
    assert doc["status"] == "pending"
    terminal = _wait_for_terminal(doc["id"], timeout_s=30.0)
    assert terminal["status"] == "ready"
    assert int(terminal["chunk_count"]) > 0


def test_worker_ingests():
    filename = f"day1-worker-{uuid.uuid4().hex}.txt"
    needle = f"Worker should ingest this: {filename}".encode("utf-8")
    status, raw = _multipart_upload(filename, needle)
    assert status == 202, raw.decode("utf-8", errors="replace")
    doc = json.loads(raw.decode("utf-8"))
    terminal = _wait_for_terminal(doc["id"], timeout_s=30.0)
    assert terminal["status"] == "ready"
    status, chat = _json(
        "POST", "/chat", body={"question": needle.decode("utf-8", errors="strict")}
    )
    assert status == 200, json.dumps(chat)
    assert isinstance(chat.get("sources"), list) and filename in chat["sources"]
    assert isinstance(chat.get("contexts"), list) and chat["contexts"]


def test_retry_idempotent():
    filename = f"day1-retry-{uuid.uuid4().hex}.txt"
    payload = b" \n "
    # Controlled retry for the same logical document: a whitespace-only document
    # is accepted (non-empty bytes) but ingestion fails (invalid_document). Retry
    # should be allowed only from failed, return 202/pending, and remain truthful
    # (still failed) without creating chunks.
    status, raw = _multipart_upload(filename, payload)
    assert status == 202, raw.decode("utf-8", errors="replace")
    doc = json.loads(raw.decode("utf-8"))
    failed = _wait_for_terminal(int(doc["id"]), timeout_s=30.0)
    assert failed["status"] == "failed"
    assert int(failed["chunk_count"]) == 0

    status, raw = _http("POST", f"/documents/{doc['id']}/retry")
    assert status == 202, raw.decode("utf-8", errors="replace")
    retry_doc = json.loads(raw.decode("utf-8"))
    assert retry_doc["status"] == "pending"

    failed2 = _wait_for_terminal(int(doc["id"]), timeout_s=30.0)
    assert failed2["status"] == "failed"
    assert int(failed2["chunk_count"]) == 0

    # Retry is still controlled and does not corrupt state or create duplicate chunks.
    status, raw = _http("POST", f"/documents/{doc['id']}/retry")
    assert status == 202, raw.decode("utf-8", errors="replace")
    failed3 = _wait_for_terminal(int(doc["id"]), timeout_s=30.0)
    assert failed3["status"] == "failed"
    assert int(failed3["chunk_count"]) == 0

    status, chat = _json("POST", "/chat", body={"question": "Retry/idempotent scenario."})
    assert status == 200, json.dumps(chat)
    assert isinstance(chat.get("sources"), list) and chat["sources"]
