"""Structured JSONL audit output; request bodies and secrets are never recorded."""
from __future__ import annotations
import json, logging, os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
logger=logging.getLogger("chatops-bot.audit")
_SENSITIVE_KEYS={"secret","signing_secret","slack_signing_secret","bot_token","slack_bot_token","raw_body","token","kubeconfig"}
def audit_event(*, action, user, decision, **fields):
    fields={key:value for key,value in fields.items() if key.lower() not in _SENSITIVE_KEYS}
    record={"timestamp":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"event_id":fields.pop("event_id",uuid4().hex),"action":action,"user":user,"decision":decision,**fields}
    line=json.dumps(record,separators=(",",":"),sort_keys=True,ensure_ascii=False)
    logger.info("%s",line)
    path=os.environ.get("CHATOPS_AUDIT_PATH","").strip()
    if path:
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("a",encoding="utf-8") as handle: handle.write(line+"\n")
    return record
