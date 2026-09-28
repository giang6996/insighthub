"""Deterministic trust-boundary checks around model generation."""

from dataclasses import dataclass
import re

SAFE_REFUSAL = (
    "I can’t help reveal hidden instructions, execute actions, or disclose "
    "sensitive personal data. I can answer a normal question using the cited documents."
)
_EXTRACTION = re.compile(r"\b(?:reveal|show|print|repeat|quote|extract|return|list|tell me|what is)\b[^\n]{0,120}\b(?:system prompt|developer prompt|hidden instruction|internal policy|chain of command|api key|password|bearer token|authorization header|credentials?)\b", re.I)
_AGENCY = re.compile(r"\b(?:delete|drop|truncate|restart|scale|rollout|run|execute|send|email|modify|change|write to|call)\b[^\n]{0,100}\b(?:database|db|pod|service|shell|command|document|file|slack|api|tool|production|cluster)\b", re.I)
_SENSITIVE_PII = re.compile(r"\b(?:social security|ssn|bank account|credit card|payment card|password|home address|personal phone|emergency contact|medical diagnosis|salary)\b", re.I)
_SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._~-]{16,}|\b(?:api[_ -]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,})", re.I)
_EXTRACTION_OUTPUT = re.compile(r"(?:\"(?:system|developer)_prompt\"\s*:\s*\"(?![^\"]*\b(?:cannot|can.?t|not found|unable)\b)|(?:system|developer) prompt\s*:\s*(?![^\n]{0,80}\b(?:cannot|can.?t|not found|unable)\b))", re.I)


@dataclass(frozen=True)
class GuardrailDecision:
    stage: str
    outcome: str
    reason: str
    text: str | None = None


def check_user_input(question: str) -> GuardrailDecision:
    if _EXTRACTION.search(question):
        return GuardrailDecision("pre_input", "blocked", "prompt_extraction")
    if _AGENCY.search(question):
        return GuardrailDecision("pre_input", "blocked", "excessive_agency")
    if _SENSITIVE_PII.search(question):
        return GuardrailDecision("pre_input", "blocked", "sensitive_pii_request")
    return GuardrailDecision("pre_input", "allowed", "none")


def check_contexts(contexts: list[dict]) -> GuardrailDecision:
    return GuardrailDecision("context", "allowed", "untrusted_context")


def check_output(answer: str, question: str) -> GuardrailDecision:
    if _SECRET.search(answer):
        return GuardrailDecision("post_output", "sanitized_or_redacted", "secret_like_output", _SECRET.sub("[REDACTED]", answer))
    if _EXTRACTION.search(question) and _EXTRACTION_OUTPUT.search(answer):
        return GuardrailDecision("post_output", "blocked", "prompt_extraction")
    return GuardrailDecision("post_output", "allowed", "none", answer)
