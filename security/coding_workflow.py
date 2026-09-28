"""Repository-owned, review-only coding workload routed through LiteLLM."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def load_context(root: Path, paths: list[str], limit: int = 12000) -> list[dict]:
    context = []
    remaining = limit
    for relative in paths:
        path = (root / relative).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            raise ValueError(f"context path is outside repository or not a file: {relative}")
        text = path.read_text(encoding="utf-8")
        clipped = text[:remaining]
        context.append({"path": relative, "text": clipped})
        remaining -= len(clipped)
        if remaining <= 0:
            break
    return context


def call_gateway(task: str, context: list[dict]) -> tuple[str, dict]:
    base = os.environ.get("LITELLM_BASE_URL", "http://localhost:14000/v1").rstrip("/")
    key = os.environ["CODING_LITELLM_KEY"]
    model = os.environ.get("CODING_LITELLM_MODEL", "coding-review")
    payload = {"model": model, "messages": [{"role": "system", "content": "You are a review-only coding assistant. Propose a patch or review; do not claim to have applied changes."}, {"role": "user", "content": json.dumps({"bounded_task": task[:2000], "repository_context": context}, ensure_ascii=False)}], "max_completion_tokens": 600}
    request = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read(512 * 1024))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("coding gateway request failed") from exc
    try:
        return data["choices"][0]["message"]["content"], {"gateway_call_id": data.get("id"), "model": data.get("model", model), "usage": data.get("usage") or {}, "cost": data.get("cost")}
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("coding gateway response invalid") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("paths", nargs="+", help="repository-relative context files")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="security/evidence/coding-proposal.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    context = load_context(root, args.paths)
    proposal, gateway = call_gateway(args.task, context)
    validation = subprocess.run(["git", "diff", "--check"], cwd=root, capture_output=True, text=True, timeout=30)
    artifact = {"workload": "coding", "observed_at": datetime.now(timezone.utc).isoformat(), "task": args.task[:2000], "context_paths": [item["path"] for item in context], "proposal": proposal[:12000], "gateway": gateway, "validation": {"command": "git diff --check", "returncode": validation.returncode, "passed": validation.returncode == 0}}
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"workload": "coding", "gateway_call_id": gateway.get("gateway_call_id"), "validation_passed": validation.returncode == 0, "output": str(output)}))
    return 0 if validation.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
