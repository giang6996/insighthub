"""Run bounded sequential/concurrent virtual-key budget checks."""

from __future__ import annotations

import concurrent.futures
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid


BASE = os.environ.get("LITELLM_BASE_URL", "http://localhost:14000").rstrip("/")
MASTER = os.environ["LITELLM_MASTER_KEY"]


def request(path: str, body: dict | None = None, key: str = MASTER) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read(256 * 1024)
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def create(alias: str) -> str:
    status, data = request(
        "/key/generate",
        {"models": ["chatops-summary"], "key_alias": alias, "max_budget": 0.001},
    )
    if status != 200 or not isinstance(data.get("key"), str):
        raise RuntimeError("budget test key provisioning failed")
    return data["key"]


def completion(key: str) -> int:
    status, _ = request(
        "/v1/chat/completions",
        {
            "model": "chatops-summary",
            "messages": [{"role": "user", "content": "Reply OK."}],
            "max_completion_tokens": 8,
        },
        key=key,
    )
    return status


def info(key: str) -> dict:
    encoded = urllib.parse.quote(key)
    headers = {"Authorization": f"Bearer {MASTER}"}
    req = urllib.request.Request(BASE + f"/key/info?key={encoded}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read(256 * 1024))
    value = data.get("info", data)
    return {"spend": value.get("spend"), "max_budget": value.get("max_budget")}


def remove(key: str) -> None:
    request("/key/delete", {"keys": [key]})


def main() -> int:
    results = []
    for alias, concurrent_count in (("budget-seq-check", 0), ("budget-concurrent-check", 4)):
        key = create(f"{alias}-{uuid.uuid4().hex[:8]}")
        try:
            if concurrent_count:
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_count) as pool:
                    statuses = list(pool.map(completion, [key] * concurrent_count))
            else:
                statuses = [completion(key) for _ in range(20)]
            results.append({"alias": alias, "statuses": statuses, "info": info(key)})
        finally:
            remove(key)
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
