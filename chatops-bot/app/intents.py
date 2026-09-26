"""Deterministic, bounded Day 5 intent classification."""
from enum import Enum
class Intent(str, Enum):
    HEALTH="health"; DOCUMENTS_TODAY="documents_today"; FAILING_PODS="failing_pods"; UNSUPPORTED="unsupported"; WRITE="write"; DESTRUCTIVE="destructive"
def classify(text):
    value=" ".join(text.lower().split())
    if any(x in value for x in ("delete", "destroy", "remove pod", "arbitrary shell", "kubectl ")): return Intent.DESTRUCTIVE
    if any(x in value for x in ("scale ", "restart ", "rollout restart", "set replicas")): return Intent.WRITE
    if any(x in value for x in ("health", "healthy", "ready", "status")): return Intent.HEALTH
    if any(x in value for x in ("ingest", "documents today", "docs today", "how many doc")): return Intent.DOCUMENTS_TODAY
    if any(x in value for x in ("pod", "pods", "crashloop", "failing")): return Intent.FAILING_PODS
    return Intent.UNSUPPORTED
