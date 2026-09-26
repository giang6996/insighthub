"""Slack raw-body signature and replay protection."""
from __future__ import annotations
import hashlib, hmac, time
from dataclasses import dataclass

class SlackAuthError(ValueError):
    def __init__(self, code): super().__init__(code); self.code = code

@dataclass(frozen=True)
class VerifiedSlackBody:
    raw_body: bytes
    timestamp: int

def verify_slack_request(raw_body, timestamp_header, signature_header, *, signing_secret, now=None, replay_window=300):
    if not signing_secret or not timestamp_header or not signature_header: raise SlackAuthError("MISSING_AUTH_HEADERS")
    try: timestamp = int(timestamp_header)
    except (TypeError, ValueError): raise SlackAuthError("INVALID_TIMESTAMP") from None
    if abs(int(time.time() if now is None else now) - timestamp) > replay_window: raise SlackAuthError("STALE_REQUEST")
    if not signature_header.startswith("v0="): raise SlackAuthError("INVALID_SIGNATURE")
    base = b"v0:" + str(timestamp).encode() + b":" + raw_body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header): raise SlackAuthError("INVALID_SIGNATURE")
    return VerifiedSlackBody(raw_body, timestamp)
