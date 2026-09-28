"""Small, bounded Prometheus exporter for LiteLLM spend logs.

The exporter uses LiteLLM's authenticated spend-log API, exports only the
allowlisted workload aliases, and intentionally discards prompts, responses,
keys, IPs, and user identifiers.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://litellm:4000").rstrip("/")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
PORT = int(os.environ.get("FINOPS_PORT", "9108"))
WORKLOADS = {"insighthub", "chatops", "coding"}
BUDGETS = {
    "insighthub": float(os.environ.get("LITELLM_BUDGET_INSIGHTHUB", "0.50")),
    "chatops": float(os.environ.get("LITELLM_BUDGET_CHATOPS", "0.25")),
    "coding": float(os.environ.get("LITELLM_BUDGET_CODING", "0.50")),
}


def _alias(row: dict) -> str | None:
    metadata = row.get("metadata") or {}
    value = metadata.get("user_api_key_alias") if isinstance(metadata, dict) else None
    return value if value in WORKLOADS else None


def _outcome(row: dict) -> str:
    status = str(row.get("status") or "").lower()
    metadata = row.get("metadata") or {}
    error = metadata.get("error_information") if isinstance(metadata, dict) else None
    error_text = json.dumps(error, ensure_ascii=False).lower()
    if "budget" in error_text or "spend" in error_text:
        return "budget_denied"
    return "success" if status == "success" else "error"


def snapshot() -> str:
    empty = "insighthub_litellm_exporter_up 0\n"
    if not MASTER_KEY:
        return empty
    request = urllib.request.Request(
        BASE_URL + "/spend/logs",
        headers={"Authorization": f"Bearer {MASTER_KEY}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            rows = json.loads(response.read(8 * 1024 * 1024))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return empty

    grouped: dict[tuple[str, str, str], dict[str, float]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        workload = _alias(row)
        model = str(row.get("model") or "unknown")
        if workload is None or len(model) > 96 or any(c in model for c in "\n\r\\\""):
            continue
        outcome = _outcome(row)
        item = grouped.setdefault((workload, model, outcome), {"requests": 0, "input": 0, "output": 0, "spend": 0, "latency": 0})
        item["requests"] += 1
        item["input"] += float(row.get("prompt_tokens") or 0)
        item["output"] += float(row.get("completion_tokens") or 0)
        item["spend"] += float(row.get("spend") or 0)
        item["latency"] += float(row.get("request_duration_ms") or 0) / 1000

    lines = ["# HELP insighthub_litellm_exporter_up Exporter health.", "# TYPE insighthub_litellm_exporter_up gauge", "insighthub_litellm_exporter_up 1", "# HELP insighthub_litellm_budget_usd Configured virtual-key budget.", "# TYPE insighthub_litellm_budget_usd gauge"]
    lines.extend(f'insighthub_litellm_budget_usd{{workload="{workload}"}} {budget}' for workload, budget in sorted(BUDGETS.items()))
    for (workload, model, outcome), values in sorted(grouped.items()):
        labels = f'workload="{workload}",model="{model}",outcome="{outcome}"'
        lines += [
            f'insighthub_litellm_requests{{{labels}}} {values["requests"]}',
            f'insighthub_litellm_input_tokens{{{labels}}} {values["input"]}',
            f'insighthub_litellm_output_tokens{{{labels}}} {values["output"]}',
            f'insighthub_litellm_spend_usd{{{labels}}} {values["spend"]}',
            f'insighthub_litellm_latency_seconds{{{labels}}} {values["latency"]}',
        ]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = snapshot().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
