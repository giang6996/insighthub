import hashlib, hmac, json, time
from datetime import datetime, timezone
import pytest
from app.backends import InsightHubBackend, KubernetesMcpBackend, KubernetesReadOnlyBackend
from app.audit import audit_event
from app.intents import Intent, classify
from app.permissions import decide
from app.security import SlackAuthError, verify_slack_request
def signed(body=b'{"type":"event_callback"}',secret="secret",stamp=None):
    stamp=int(time.time() if stamp is None else stamp); sig="v0="+hmac.new(secret.encode(),f"v0:{stamp}:".encode()+body,hashlib.sha256).hexdigest(); return body,str(stamp),sig
def test_valid_signature_and_replay_rejection():
    body,stamp,sig=signed(); assert verify_slack_request(body,stamp,sig,signing_secret="secret").raw_body==body
    with pytest.raises(SlackAuthError) as exc: verify_slack_request(body,str(int(time.time())-301),sig,signing_secret="secret")
    assert exc.value.code=="STALE_REQUEST"
def test_invalid_signature_rejected():
    body,stamp,_=signed()
    with pytest.raises(SlackAuthError): verify_slack_request(body,stamp,"v0=bad",signing_secret="secret")
@pytest.mark.parametrize(("text","expected"),[("is InsightHub healthy?",Intent.HEALTH),("how many docs today",Intent.DOCUMENTS_TODAY),("which pods are failing",Intent.FAILING_PODS)])
def test_required_intents(text,expected): assert classify(text) is expected
def test_permissions_fail_closed():
    assert decide(Intent.HEALTH).name=="allowed"; assert decide(Intent.WRITE).name=="approval_required"; assert decide(Intent.DESTRUCTIVE).name=="denied"; assert not decide(Intent.UNSUPPORTED).executable
def test_ready_documents_today_uses_created_at_and_status(monkeypatch):
    rows=[{"status":"ready","created_at":"2026-09-26T01:00:00+00:00"},{"status":"pending","created_at":"2026-09-26T02:00:00+00:00"},{"status":"ready","created_at":"2026-09-25T23:00:00+00:00"}]
    monkeypatch.setattr("app.backends._get_json",lambda url:(200,rows)); assert InsightHubBackend("http://api").ready_documents_today(datetime(2026,9,26,tzinfo=timezone.utc))==1
def test_kubernetes_adapter_is_namespace_bounded():
    calls=[]
    class Result: stdout=json.dumps({"items":[]})
    def runner(command,**kwargs): calls.append(command); return Result()
    assert KubernetesReadOnlyBackend(runner=runner).failing_pods()==[]; assert calls[0]==["kubectl","get","pods","-n","insighthub","-o","json"]

def test_kubernetes_mcp_adapter_uses_fixed_tool_and_namespace():
    import asyncio
    calls=[]
    async def call_tool(name, arguments):
        calls.append((name, arguments))
        return {"content":[{"type":"text","text":"NAMESPACE APIVERSION KIND NAME READY STATUS\ninsighthub v1 Pod bad 0/1 Error\n"}]}
    result=asyncio.run(KubernetesMcpBackend(call_tool).failing_pods())
    assert calls == [("pods_list_in_namespace", {"namespace":"insighthub"})]
    assert result[0]["name"] == "bad"

def test_kubernetes_mcp_adapter_reads_structured_pod_results():
    import asyncio
    async def call_tool(name, arguments):
        return {"structuredContent": {"items": [{
            "metadata": {"name": "crashed", "namespace": "insighthub"},
            "status": {"phase": "Running", "containerStatuses": [{
                "ready": False, "state": {"waiting": {"reason": "CrashLoopBackOff"}}
            }]}
        }]}}
    result=asyncio.run(KubernetesMcpBackend(call_tool).failing_pods())
    assert result == [{"name":"crashed", "namespace":"insighthub", "phase":"Running", "reasons":["CrashLoopBackOff"], "ready":0, "total":1}]

def test_kubernetes_mcp_adapter_reads_json_text_pod_results():
    import asyncio, json
    async def call_tool(name, arguments):
        return {"content": [{"type": "text", "text": json.dumps({"items": [{
            "metadata": {"name": "crashed", "namespace": "insighthub"},
            "status": {"phase": "Running", "containerStatuses": [{
                "ready": False, "state": {"waiting": {"reason": "CrashLoopBackOff"}}
            }]}
        }]})}]}
    result=asyncio.run(KubernetesMcpBackend(call_tool).failing_pods())
    assert result[0]["reasons"] == ["CrashLoopBackOff"]

def test_kubernetes_mcp_adapter_does_not_hide_mcp_errors_as_empty_pods():
    import asyncio
    from app.backends import BackendUnavailable
    async def call_tool(name, arguments):
        return {"isError": True, "content": [{"type": "text", "text": "connection refused"}]}
    with pytest.raises(BackendUnavailable) as exc:
        asyncio.run(KubernetesMcpBackend(call_tool).failing_pods())
    assert str(exc.value) == "KUBERNETES_MCP_UNAVAILABLE"

def test_audit_is_structured_and_does_not_include_secret(monkeypatch, tmp_path):
    path=tmp_path / "audit.jsonl"
    monkeypatch.setenv("CHATOPS_AUDIT_PATH", str(path))
    record=audit_event(action="intent_request", user="U1", decision="denied", secret="must-not-be-secret")
    assert {"timestamp", "event_id", "action", "user", "decision"} <= set(record)
    assert "SLACK_SIGNING_SECRET" not in path.read_text(encoding="utf-8")
    assert "must-not-be-secret" not in path.read_text(encoding="utf-8")

def test_worker_blocks_mutations_without_backend(monkeypatch):
    import asyncio
    from app.worker import process_chatops_event
    calls=[]
    replies=[]
    monkeypatch.setattr("app.worker.audit_event", lambda **fields: calls.append(fields))
    async def capture_reply(channel, text, thread_ts):
        replies.append((channel, text, thread_ts))
    monkeypatch.setattr("app.worker.send_slack_reply", capture_reply)
    result=asyncio.run(process_chatops_event(None, {"text":"delete pod api-1", "user_id":"U1", "event_id":"E1", "correlation_id":"C1", "channel_id":"C1", "thread_ts":""}))
    assert result == {"status": "blocked", "decision": "denied"}
    assert calls[0]["decision"] == "denied"
    assert replies == [("C1", "This destructive or unrestricted action is not available.", "")]

def test_authenticated_challenge_is_handled_before_queue(monkeypatch):
    import asyncio
    from app.main import slack_events
    body=json.dumps({"type":"url_verification","challenge":"c123"}).encode()
    _, stamp, sig=signed(body)
    class Request:
        headers={"X-Slack-Request-Timestamp":stamp,"X-Slack-Signature":sig}
        async def body(self): return body
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret")
    result=asyncio.run(slack_events(Request()))
    assert result == {"challenge":"c123"}

def test_authenticated_malformed_json_is_rejected(monkeypatch):
    import asyncio
    from app.main import slack_events
    body=b"not-json"; _, stamp, sig=signed(body)
    class Request:
        headers={"X-Slack-Request-Timestamp":stamp,"X-Slack-Signature":sig}
        async def body(self): return body
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret")
    result=asyncio.run(slack_events(Request()))
    assert result.status_code == 400

def test_queue_uses_chatops_dedup_and_small_job(monkeypatch):
    import asyncio, sys, types
    from app.queue import ChatOpsQueue
    class Pool:
        def __init__(self): self.keys=set(); self.jobs=[]
        async def set(self,key,value,ex,nx):
            if key in self.keys: return False
            self.keys.add(key); return True
        async def enqueue_job(self,*args,**kwargs): self.jobs.append((args,kwargs)); return object()
        async def delete(self,key): self.keys.discard(key)
        async def aclose(self): pass
    pool=Pool()
    async def create_pool(settings): return pool
    fake=types.ModuleType("arq.connections"); fake.RedisSettings=types.SimpleNamespace(from_dsn=lambda value:value); fake.create_pool=create_pool
    monkeypatch.setitem(sys.modules,"arq.connections",fake)
    job={"team_id":"T1","event_id":"E1","user_id":"U1","text":"health","channel_id":"C1"}
    queue=ChatOpsQueue(redis_url="redis://test", queue_name="chatops")
    assert asyncio.run(queue.enqueue(job)) is True
    assert asyncio.run(queue.enqueue(job)) is False
    assert pool.jobs[0][1]["_queue_name"] == "chatops"
    assert pool.jobs[0][0][1]["text"] == "health"
