"""Run the five separate SUPPLEMENTAL indirect-injection cases via public APIs."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.environ.get("INSIGHTHUB_BASE_URL", "http://localhost:8000").rstrip("/")
DATASET = Path(__file__).with_name("supplemental-indirect-injection.json")
OUT = Path(__file__).with_name("evidence") / "supplemental-indirect-final.json"


def request(method: str, path: str, body: bytes | None = None, content_type: str = "application/json"):
    req = urllib.request.Request(BASE_URL + path, data=body, method=method, headers={"Content-Type": content_type, "X-Day6-Test-Run": "supplemental-indirect"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.status, response.read()


def upload(filename: str, text: str) -> dict:
    boundary = "----InsightHubSupplemental" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: text/plain\r\n\r\n".encode() + text.encode() + f"\r\n--{boundary}--\r\n".encode())
    status, raw = request("POST", "/documents", body, f"multipart/form-data; boundary={boundary}")
    if status != 202:
        raise RuntimeError(f"upload HTTP {status}")
    return json.loads(raw)


def wait_ready(document_id: int) -> dict:
    for _ in range(60):
        _, raw = request("GET", "/documents")
        row = next((item for item in json.loads(raw) if item.get("id") == document_id), None)
        if row and row.get("status") in {"ready", "failed"}:
            return row
        time.sleep(2)
    raise TimeoutError(f"document {document_id} not ready")


def main() -> int:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    results = []
    for case in dataset["cases"]:
        filename = f"day6-supplemental-{case['id']}.txt"
        uploaded = upload(filename, case["document"])
        status = wait_ready(int(uploaded["id"]))
        _, raw = request("POST", "/chat", json.dumps({"question": case["question"]}).encode())
        response = json.loads(raw)
        contexts = response.get("contexts") or []
        results.append({
            "case_id": case["id"],
            "label": "SUPPLEMENTAL",
            "document_id": uploaded["id"],
            "ready": status.get("status") == "ready",
            "expected_fact_observed": case["expected_fact"].lower() in response.get("answer", "").lower(),
            "retrieved_contexts": [{"rank": rank, "chunk_id": c.get("id"), "source": c.get("source"), "chunk_sha256": hashlib.sha256(str(c.get("chunk_text", "")).encode()).hexdigest()} for rank, c in enumerate(contexts, 1)],
            "answer": response.get("answer", ""),
            "mode": response.get("mode"),
            "provider": response.get("provider"),
            "model": response.get("model"),
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"label": "SUPPLEMENTAL", "base_url": BASE_URL, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(results), "ready": sum(r["ready"] for r in results), "expected_facts": sum(r["expected_fact_observed"] for r in results), "evidence": str(OUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
