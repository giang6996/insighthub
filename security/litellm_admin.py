"""Provision and inspect Day 6 LiteLLM virtual keys without printing secrets."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:14000").rstrip("/")
OUT = Path(os.environ.get("LITELLM_WORKLOAD_ENV", "security/.env.day6.workload.local"))


def call(path: str, method: str = "GET", body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {os.environ['LITELLM_MASTER_KEY']}", "Content-Type": "application/json"}
    request = urllib.request.Request(BASE_URL + path, headers=headers, method=method, data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def provision(alias: str, models: list[str], budget: float) -> tuple[str, dict]:
    response = call("/key/generate", "POST", {"models": models, "key_alias": alias, "max_budget": budget, "metadata": {"workload": alias, "environment": "day6-local"}})
    key = response.get("key") or response.get("token")
    if not isinstance(key, str) or not key.startswith("sk-"):
        raise RuntimeError("LiteLLM did not return a virtual key")
    return key, {"alias": alias, "models": models, "max_budget": budget}


def main() -> int:
    keys = {
        "INSIGHTHUB_LITELLM_KEY": provision("insighthub", ["insighthub-chat", "insighthub-embedding"], 0.50),
        "CHATOPS_LITELLM_KEY": provision("chatops", ["chatops-summary"], 0.25),
        "CODING_LITELLM_KEY": provision("coding", ["coding-review"], 0.50),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(f"{name}={value[0]}" for name, value in keys.items()) + "\n", encoding="utf-8")
    print(json.dumps({"keys": [value[1] for value in keys.values()], "env_file": str(OUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
