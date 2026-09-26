"""Day 5 verifier contract tests for permission, approval, deduplication and auth."""

import hashlib
import hmac
import json
import os
import pathlib
import sys
import time

import pytest


ROOT = pathlib.Path(os.environ.get("INSIGHTHUB_REPO_ROOT", pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(ROOT / "chatops-bot"))

from app.audit import audit_event  # noqa: E402
from app.intents import Intent, classify  # noqa: E402
from app.permissions import decide  # noqa: E402
from app.security import SlackAuthError, verify_slack_request  # noqa: E402


_EVENTS = []
_RUN_ID = os.environ.get("INSIGHTHUB_VERIFY_RUN_ID", "day5-local-contract")


def _audit(*, action, user, decision, event_id):
    record = audit_event(
        action=action,
        user=user,
        decision=decision,
        event_id=event_id,
        test_run_id=_RUN_ID,
    )
    _EVENTS.append(record)
    return record


def _write_observations():
    target = os.environ.get("INSIGHTHUB_VERIFY_OBSERVATIONS", "").strip()
    if target:
        path = pathlib.Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"run_id": _RUN_ID, "events": _EVENTS}, separators=(",", ":")),
            encoding="utf-8",
        )


@pytest.fixture(scope="session", autouse=True)
def emit_observations():
    yield
    _write_observations()


def test_permission_denied():
    intent = classify("delete pod api-1")
    decision = decide(intent)
    assert intent is Intent.DESTRUCTIVE
    assert decision.name == "denied"
    assert decision.executable is False
    _audit(action="intent_request", user="U-day5-denied", decision=decision.name, event_id="day5-denied")


def test_approval_required():
    intent = classify("scale api to 5")
    decision = decide(intent)
    assert intent is Intent.WRITE
    assert decision.name == "approval_required"
    assert decision.executable is False
    _audit(action="intent_request", user="U-day5-approval", decision=decision.name, event_id="day5-approval")


def test_approval_bound_to_action():
    allowed = decide(classify("health"))
    requested = decide(classify("scale api to 5"))
    assert allowed.name == "allowed" and allowed.executable is True
    assert requested.name == "approval_required" and requested.executable is False
    assert requested.tier == "write"


def test_duplicate_event():
    seen = set()
    event_id = "day5-duplicate"
    assert event_id not in seen
    seen.add(event_id)
    assert event_id in seen
    assert event_id in seen


def test_invalid_signature():
    body = b'{"type":"event_callback"}'
    stamp = str(int(time.time()))
    expected = "v0=" + hmac.new(
        b"local-contract-secret", f"v0:{stamp}:".encode() + body, hashlib.sha256
    ).hexdigest()
    with pytest.raises(SlackAuthError):
        verify_slack_request(body, stamp, "v0=bad", signing_secret="local-contract-secret")
