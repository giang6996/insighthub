"""Slack HTTP Events ingress for the Day 5 ChatOps bot."""
from __future__ import annotations
import json, os, time
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .audit import audit_event
from .queue import ChatOpsQueue, QueueUnavailable
from .security import SlackAuthError, verify_slack_request

app = FastAPI(title="InsightHub ChatOps", version="0.3.0")
_queue = ChatOpsQueue()

@app.get("/healthz")
def health():
    return {"status": "ok", "ready": True, "transport": "slack_http"}

@app.post("/slack/events")
async def slack_events(request: Request):
    raw = await request.body()
    try:
        verified = verify_slack_request(raw, request.headers.get("X-Slack-Request-Timestamp"), request.headers.get("X-Slack-Signature"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET", ""), now=time.time())
    except SlackAuthError as exc:
        audit_event(action="slack_authenticate", user="unknown", decision="denied", outcome="rejected", error_code=exc.code)
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        payload = json.loads(verified.raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True, "ignored": True}
    event_id, user_id = str(payload.get("event_id") or "").strip(), str(event.get("user") or "").strip()
    text, team_id, channel_id = str(event.get("text") or "").strip(), str(payload.get("team_id") or "").strip(), str(event.get("channel") or "").strip()
    if not event_id or not user_id or not text or not team_id or not channel_id:
        return {"ok": True, "ignored": True}
    job = {"event_id": event_id, "team_id": team_id, "channel_id": channel_id, "user_id": user_id, "text": text[:2000], "thread_ts": str(event.get("thread_ts") or event.get("ts") or ""), "received_at": time.time(), "correlation_id": uuid4().hex}
    try:
        accepted = await _queue.enqueue(job)
    except QueueUnavailable:
        audit_event(action="enqueue_chatops_event", user=user_id, decision="allowed", outcome="failed", error_code="QUEUE_UNAVAILABLE", slack_event_id=event_id)
        return JSONResponse({"ok": False, "error": "temporarily_unavailable"}, status_code=503)
    return {"ok": True, **({"duplicate": True} if not accepted else {})}
