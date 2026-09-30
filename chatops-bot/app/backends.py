"""Bounded backend adapters for the mandatory read intents."""
from __future__ import annotations
import json, os, subprocess, urllib.error, urllib.request
from datetime import datetime, timezone
class BackendUnavailable(RuntimeError): pass
def _get_json(url, timeout=2.0):
    req=urllib.request.Request(url,headers={"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            if response.status not in {200,503}: raise BackendUnavailable("UPSTREAM_HTTP_ERROR")
            return response.status,json.loads(response.read(65536))
    except (urllib.error.URLError,TimeoutError,json.JSONDecodeError,OSError) as exc: raise BackendUnavailable("UPSTREAM_UNAVAILABLE") from exc
class InsightHubBackend:
    def __init__(self,base_url=None): self.base_url=(base_url or os.environ.get("INSIGHTHUB_API_URL","http://127.0.0.1:8000")).rstrip("/")
    def health(self):
        live_status,live=_get_json(self.base_url+"/healthz"); ready_status,ready=_get_json(self.base_url+"/readyz")
        return {"live":live_status==200 and live.get("status")=="ok","ready":ready_status==200 and ready.get("status")=="ready","database_ready":bool(ready.get("db"))}
    def ready_documents_today(self,now=None):
        _,data=_get_json(self.base_url+"/documents")
        if not isinstance(data,list): raise BackendUnavailable("INVALID_DOCUMENT_RESPONSE")
        today=(now or datetime.now(timezone.utc)).date(); count=0
        for row in data:
            if not isinstance(row,dict) or row.get("status")!="ready": continue
            try: created=datetime.fromisoformat(str(row["created_at"]).replace("Z","+00:00"))
            except (KeyError,TypeError,ValueError) as exc: raise BackendUnavailable("INVALID_DOCUMENT_TIMESTAMP") from exc
            if created.astimezone(timezone.utc).date()==today: count+=1
        return count
class PrometheusMcpBackend:
    ALLOWED_QUERIES=frozenset({"requests_5m","errors_5m","documents"})
    def __init__(self,call_tool=None): self.call_tool=call_tool
    async def summary(self,query):
        if query not in self.ALLOWED_QUERIES or self.call_tool is None: raise BackendUnavailable("PROMETHEUS_MCP_UNAVAILABLE")
        return await self.call_tool("prometheus_summary",{"query":query})
class KubernetesReadOnlyBackend:
    """Fixed namespace-bounded adapter; no user-controlled kubectl arguments."""
    def __init__(self,namespace=None,runner=None): self.namespace=namespace or os.environ.get("INSIGHTHUB_NAMESPACE","insighthub"); self.runner=runner or subprocess.run
    def failing_pods(self):
        command=["kubectl","get","pods","-n",self.namespace,"-o","json"]
        try:
            result=self.runner(command,check=True,capture_output=True,text=True,timeout=3); payload=json.loads(result.stdout)
        except (OSError,subprocess.SubprocessError,json.JSONDecodeError) as exc: raise BackendUnavailable("KUBERNETES_UNAVAILABLE") from exc
        failing=[]
        for item in payload.get("items",[]):
            metadata=item.get("metadata",{}); status=item.get("status",{}); reasons=[]
            for container in status.get("containerStatuses",[]):
                waiting=(container.get("state",{}) or {}).get("waiting") or {}
                if waiting.get("reason"): reasons.append(waiting["reason"])
                if container.get("ready") is False and not waiting.get("reason"): reasons.append("NotReady")
            if status.get("phase")=="Failed" or reasons:
                statuses=status.get("containerStatuses",[])
                failing.append({"name":metadata.get("name","unknown"),"namespace":self.namespace,"phase":status.get("phase","Unknown"),"reasons":sorted(set(reasons)),"ready":sum(1 for c in statuses if c.get("ready")),"total":len(statuses)})
        return failing


class KubernetesMcpBackend:
    """Adapter for the official MCP client; never falls back to kubectl."""

    def __init__(self, call_tool):
        self.call_tool = call_tool

    @staticmethod
    def _pod_from_object(pod):
        metadata = pod.get("metadata")
        status = pod.get("status")
        if isinstance(metadata, dict) and isinstance(status, dict):
            statuses = status.get("containerStatuses") or []
            reasons = []
            for container in statuses:
                waiting = (container.get("state") or {}).get("waiting") or {}
                if waiting.get("reason"):
                    reasons.append(waiting["reason"])
                if container.get("ready") is False and not waiting.get("reason"):
                    reasons.append("NotReady")
            phase = status.get("phase", "Unknown")
            if phase == "Failed" or reasons:
                return {"name": metadata.get("name", "unknown"), "namespace": metadata.get("namespace", "insighthub"), "phase": phase, "reasons": sorted(set(reasons)), "ready": sum(1 for c in statuses if c.get("ready")), "total": len(statuses)}
            return None

        if isinstance(pod.get("name"), str) and isinstance(pod.get("ready"), str) and isinstance(pod.get("status"), str):
            try:
                ready_count, total_count = (int(value) for value in pod["ready"].split("/", 1))
            except (TypeError, ValueError):
                raise BackendUnavailable("KUBERNETES_MCP_SCHEMA") from None
            if pod["status"] not in {"Running", "Completed"} or ready_count != total_count:
                return {"name": pod["name"], "namespace": pod.get("namespace", "insighthub"), "phase": pod["status"], "reasons": [pod["status"]], "ready": pod["ready"]}
        return None

    @classmethod
    def _structured_pods(cls, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        found = []
        if isinstance(value, dict):
            pod = cls._pod_from_object(value)
            if pod:
                found.append(pod)
            for child in value.values():
                found.extend(cls._structured_pods(child))
        elif isinstance(value, list):
            for child in value:
                found.extend(cls._structured_pods(child))
        return found

    async def failing_pods(self):
        if self.call_tool is None:
            raise BackendUnavailable("KUBERNETES_MCP_UNAVAILABLE")
        result = await self.call_tool(
            "pods_list_in_namespace", {"namespace": "insighthub"}
        )
        if not isinstance(result, dict) or result.get("isError") is True:
            raise BackendUnavailable("KUBERNETES_MCP_UNAVAILABLE")
        structured = self._structured_pods((result or {}).get("structuredContent"))
        if structured:
            return structured
        text = ""
        for block in (result or {}).get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                return self._structured_pods(parsed)
        structured_text = self._structured_pods(text)
        if structured_text:
            return structured_text
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) <= 1:
            return []
        headers = lines[0].split()
        try:
            indexes = {name: headers.index(name) for name in ("NAME", "NAMESPACE", "READY", "STATUS")}
        except ValueError as exc:
            raise BackendUnavailable("KUBERNETES_MCP_SCHEMA") from exc
        failing = []
        for line in lines[1:]:
            columns = line.split()
            if len(columns) <= max(indexes.values()):
                continue
            status = columns[indexes["STATUS"]]
            ready = columns[indexes["READY"]]
            try:
                ready_count, total_count = (int(value) for value in ready.split("/", 1))
            except (TypeError, ValueError):
                raise BackendUnavailable("KUBERNETES_MCP_SCHEMA") from None
            if status not in {"Running", "Completed"} or ready_count != total_count:
                failing.append({"name": columns[indexes["NAME"]], "namespace": columns[indexes["NAMESPACE"]], "phase": status, "reasons": [status], "ready": ready})
        return failing
