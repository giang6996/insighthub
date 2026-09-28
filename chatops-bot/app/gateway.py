"""Bounded, read-only LiteLLM summary client for Day 6 ChatOps."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class GatewayUnavailable(Exception):
    pass


def summarize(*, intent: str, result: str) -> tuple[str, dict]:
    base_url = os.environ.get("LITELLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LITELLM_API_KEY", "").strip()
    model = os.environ.get("LITELLM_MODEL", "chatops-summary").strip()
    if not base_url or not key:
        raise GatewayUnavailable("LITELLM_NOT_CONFIGURED")
    bounded = result[:2000]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Summarize approved read-only incident data. Do not suggest or execute actions. Return at most two concise sentences."},
            {"role": "user", "content": json.dumps({"intent": intent, "approved_read_only_result": bounded}, ensure_ascii=False)},
        ],
        "max_completion_tokens": 120,
    }
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read(256 * 1024))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise GatewayUnavailable("LITELLM_REQUEST_FAILED") from exc
    try:
        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return str(answer)[:1200], {"gateway_call_id": data.get("id"), "model": data.get("model", model), "usage": usage, "cost": data.get("cost")}
    except (KeyError, IndexError, TypeError) as exc:
        raise GatewayUnavailable("LITELLM_INVALID_RESPONSE") from exc
