"""ARQ worker entrypoint for asynchronous ChatOps jobs."""
from __future__ import annotations
import asyncio, json, os, time
import urllib.error
import urllib.request
try:
    from arq.connections import RedisSettings
except ImportError:  # unit-test environments may exercise the worker with doubles
    RedisSettings = None
from .audit import audit_event
from .backends import BackendUnavailable, InsightHubBackend, KubernetesMcpBackend, PrometheusMcpBackend
from .intents import Intent, classify
from .permissions import decide
from .gateway import GatewayUnavailable, summarize
async def send_slack_reply(channel, text, thread_ts):
    reply_path = os.environ.get("CHATOPS_REPLY_PATH", "").strip()
    if reply_path:
        fail_once_path = os.environ.get("CHATOPS_REPLY_FAIL_ONCE_PATH", "").strip()
        for attempt in range(3):
            try:
                if fail_once_path and not os.path.exists(fail_once_path):
                    with open(fail_once_path, "x", encoding="utf-8"):
                        pass
                    raise BackendUnavailable("SLACK_REPLY_TRANSIENT")
                with open(reply_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"channel": channel, "text": text, "thread_ts": thread_ts}) + "\n")
                return
            except BackendUnavailable:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (2 ** attempt))
            except OSError as exc:
                if attempt == 2:
                    raise BackendUnavailable("SLACK_REPLY_UNAVAILABLE") from exc
                await asyncio.sleep(0.1 * (2 ** attempt))
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        raise BackendUnavailable("SLACK_CLIENT_NOT_CONFIGURED")
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    request = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read(65536))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise BackendUnavailable("SLACK_REPLY_UNAVAILABLE") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise BackendUnavailable("SLACK_REPLY_REJECTED")

async def call_kubernetes_mcp(tool_name, arguments):
    if tool_name != "pods_list_in_namespace" or arguments != {"namespace": "insighthub"}:
        raise BackendUnavailable("KUBERNETES_MCP_REQUEST_REJECTED")
    kubeconfig = os.environ.get("KUBERNETES_MCP_KUBECONFIG")
    script = os.environ.get("KUBERNETES_MCP_CLIENT_SCRIPT", "/opt/mcp-client/client.mjs")
    if not kubeconfig:
        raise BackendUnavailable("KUBERNETES_MCP_UNAVAILABLE")
    try:
        process = await asyncio.create_subprocess_exec(
            os.environ.get("KUBERNETES_MCP_NODE", "node"), script,
            env={
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "KUBERNETES_MCP_KUBECONFIG": kubeconfig,
                "KUBERNETES_MCP_SERVER_COMMAND": os.environ.get(
                    "KUBERNETES_MCP_SERVER_COMMAND",
                    "/usr/local/lib/node_modules/kubernetes-mcp-server/node_modules/kubernetes-mcp-server-linux-amd64/bin/kubernetes-mcp-server-linux-amd64",
                ),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
    except (OSError, asyncio.TimeoutError) as exc:
        raise BackendUnavailable("KUBERNETES_MCP_UNAVAILABLE") from exc
    if process.returncode != 0:
        raise BackendUnavailable("KUBERNETES_MCP_UNAVAILABLE")
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackendUnavailable("KUBERNETES_MCP_SCHEMA") from exc
    if not isinstance(result, dict) or not isinstance(result.get("content"), list):
        raise BackendUnavailable("KUBERNETES_MCP_SCHEMA")
    return result

async def call_prometheus_mcp(tool_name, arguments):
    if tool_name != "prometheus_summary" or arguments != {"query": "requests_5m"}:
        raise BackendUnavailable("PROMETHEUS_MCP_REQUEST_REJECTED")
    script = os.environ.get("PROMETHEUS_MCP_CLIENT_SCRIPT", "/opt/mcp-client/prometheus.mjs")
    try:
        process = await asyncio.create_subprocess_exec(
            os.environ.get("KUBERNETES_MCP_NODE", "node"), script,
            env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
    except (OSError, asyncio.TimeoutError) as exc:
        raise BackendUnavailable("PROMETHEUS_MCP_UNAVAILABLE") from exc
    if process.returncode != 0:
        raise BackendUnavailable("PROMETHEUS_MCP_UNAVAILABLE")
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackendUnavailable("PROMETHEUS_MCP_SCHEMA") from exc
    if not isinstance(result, dict) or not isinstance(result.get("structuredContent"), dict):
        raise BackendUnavailable("PROMETHEUS_MCP_SCHEMA")
    return result
async def process_chatops_event(ctx,job):
    intent=classify(job["text"]); decision=decide(intent)
    common={"user":job["user_id"],"slack_event_id":job["event_id"],"correlation_id":job["correlation_id"],"intent":intent.value,"permission_tier":decision.tier}
    if not decision.executable:
        audit_event(action="intent_request",decision=decision.name,outcome="blocked",**common)
        await send_slack_reply(job["channel_id"], decision.response, job["thread_ts"])
        return {"status":"blocked","decision":decision.name}
    started=time.monotonic()
    try:
        if intent is Intent.HEALTH:
            result=InsightHubBackend().health()
            prometheus = ctx.get("prometheus_mcp") if isinstance(ctx, dict) else None
            prometheus = prometheus or call_prometheus_mcp
            prometheus_fields = {"prometheus_tool": "prometheus_summary", "prometheus_query": "requests_5m"}
            try:
                summary = await PrometheusMcpBackend(prometheus).summary("requests_5m")
                value = (summary.get("structuredContent") or {}).get("value")
                if value is None:
                    raise BackendUnavailable("PROMETHEUS_MCP_SCHEMA")
                response=f"InsightHub live={result['live']}, ready={result['ready']}, database_ready={result['database_ready']}; requests_5m={value}."
                prometheus_fields["prometheus_outcome"] = "success"
            except BackendUnavailable as exc:
                response=f"InsightHub live={result['live']}, ready={result['ready']}, database_ready={result['database_ready']}; Prometheus enrichment unavailable."
                prometheus_fields.update({"prometheus_outcome": "degraded", "prometheus_error_code": str(exc)})
            tool="insighthub_health"
        elif intent is Intent.DOCUMENTS_TODAY:
            count=InsightHubBackend().ready_documents_today(); response=f"{count} documents created today are currently ready."; tool="insighthub_list_documents"
        else:
            mcp = ctx.get("kubernetes_mcp") if isinstance(ctx, dict) else None
            mcp = mcp or call_kubernetes_mcp
            result=await KubernetesMcpBackend(mcp).failing_pods()
            response = "No failing pods found." if not result else "Failing pods: " + ", ".join(
                f"{pod['name']} (namespace={pod['namespace']}, phase={pod['phase']}, "
                f"reason={','.join(pod['reasons'])}, ready={pod['ready']})" for pod in result
            )
            tool="pods_list_in_namespace"
        audit_fields = prometheus_fields if intent is Intent.HEALTH else {}
        gateway_fields = {}
        try:
            response, gateway = summarize(intent=intent.value, result=response)
            gateway_fields = {"workload": "chatops", "gateway_outcome": "success", **gateway}
        except GatewayUnavailable as exc:
            gateway_fields = {"workload": "chatops", "gateway_outcome": "degraded", "gateway_error_code": str(exc)}
        audit_event(action="intent_request",decision="allowed",outcome="success",backend=tool,duration_ms=int((time.monotonic()-started)*1000),**audit_fields,**gateway_fields,**common)
        await send_slack_reply(job["channel_id"],response,job["thread_ts"])
        return {"status":"replied","intent":intent.value}
    except BackendUnavailable as exc:
        audit_event(action="intent_request",decision="allowed",outcome="failed",error_code=str(exc),**common); raise
class WorkerSettings:
    functions=[process_chatops_event]
    redis_settings=RedisSettings.from_dsn(os.environ.get("REDIS_URL","redis://redis:6379/0")) if RedisSettings else None
    queue_name=os.environ.get("CHATOPS_QUEUE","chatops")
    max_tries=3
