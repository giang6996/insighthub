"""Fail-closed permission decisions for the Day 5 baseline."""
from dataclasses import dataclass
from .intents import Intent
@dataclass(frozen=True)
class Decision:
    name: str; tier: str; executable: bool; response: str
def decide(intent):
    if intent in {Intent.HEALTH, Intent.DOCUMENTS_TODAY, Intent.FAILING_PODS}: return Decision("allowed", "read", True, "")
    if intent is Intent.WRITE: return Decision("approval_required", "write", False, "This action requires approval before execution.")
    if intent is Intent.DESTRUCTIVE: return Decision("denied", "destructive", False, "This destructive or unrestricted action is not available.")
    return Decision("denied", "read", False, "I can answer health, ingestion-count, and failing-pod questions.")
