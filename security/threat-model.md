# InsightHub Day 6 threat model

This is a residual-risk inventory for the local Day 6 runtime. Documents,
retrieved context, prompts, tool/MCP output, provider responses, and Slack
events remain untrusted data. Evidence paths refer to the frozen Phase 2 and
Phase 3 artifacts; a control is not described as eliminating a threat.

| ID | Asset | Trust boundary | Threat / attack path | Impact | Implemented mitigation | Residual risk | Evidence |
|---|---|---|---|---|---|---|---|
| T01 | System instructions and answer policy | User prompt -> LLM | Direct prompt injection asks the model to ignore policy or reveal hidden instructions. | Unsafe or misleading answer; instruction disclosure. | User-input guardrails and bounded system prompt. | Novel phrasing, multilingual attacks, or provider behavior may evade checks. | `security/evidence/promptfoo-final.json`, `api/app/services/guardrails.py` |
| T02 | Retrieved context | Uploaded document -> prompt context | Indirect injection embeds commands in a relevant document. | Model follows document text as authority. | Context is labeled untrusted and output/input guardrails remain active. | Retrieval and model semantic behavior can still produce unsafe text. | `security/evidence/supplemental-indirect-final.json`, `security/baseline-final.md` |
| T03 | Retrieval index | Upload -> ingestion -> chunks -> embeddings | RAG poisoning adds plausible but malicious content that ranks for a query. | Incorrect answer or instruction execution. | Ready/current-identity filtering, real upload path, and poisoned-fixture testing. | Content moderation and provenance verification are not complete controls. | `security/evidence/rag-baseline.json` |
| T04 | Personal and confidential data | Retrieved context -> provider/output | A user asks for emails, phone numbers, secrets, or cross-document identity data. | Privacy leakage and compliance exposure. | PII guardrail checks and bounded/sanitized responses. | False negatives and authorized-but-overbroad requests remain possible. | `security/evidence/promptfoo-final.json` |
| T05 | Tools and side effects | ChatOps request -> permission router -> backend/MCP | Excessive-agency request attempts deletion, scaling, shell, or hidden mutation. | Operational or destructive action. | Day 5 read/write/destructive tiers, approval requirement, read-only MCP RBAC, audit records. | A newly added backend or parser could introduce an unreviewed side effect. | `chatops-bot/app/permissions.py`, Day 5 evidence |
| T06 | Hidden prompts and secrets | User/document -> model response | Prompt extraction requests system text, provider keys, or internal context. | Policy and credential disclosure. | Prompt extraction guardrails and secret-safe error/audit handling. | A provider can still generate memorized or inferred sensitive text. | `security/evidence/promptfoo-final.json` |
| T07 | Provider route | Workload container -> LiteLLM -> upstream | A workload bypasses the gateway and calls the provider directly. | Loss of model restriction, attribution, budgets, and central evidence. | Workload endpoint is `http://litellm:4000/v1`; virtual-key model restrictions; bypass test denied with 403. | Host access or future Compose changes could reintroduce a direct route. | `docker-compose.day6-gateway.yml`, gateway verification record |
| T08 | Virtual keys | Gateway control plane -> workload env | A virtual key is logged, committed, or exposed to another workload. | Cross-workload access and spend attribution loss. | Separate keys, ignored local env files, bounded aliases, no key labels/metrics. | Runtime secret handling and operator mistakes remain risks. | `security/litellm_admin.py`, `.gitignore` |
| T09 | Spend budget | Workload -> LiteLLM | Repeated requests cause denial-of-wallet or exhaust a workload budget. | Unexpected spend or service denial. | Per-key `max_budget`, model restrictions, spend-log exporter, budget dashboard. | Accounting/update timing means max_budget is not an absolute synchronous hard cap. | `security/litellm_budget_test.py`, `observability/grafana-day6-finops.json` |
| T10 | Concurrent accounting | Concurrent workload requests -> gateway DB | Parallel requests are admitted before spend state is fully propagated. | Temporary budget overshoot. | Concurrent test retained and documented; budgets remain gateway-side controls. | Observed accounting delay/uncertainty is unresolved. | `security/litellm_budget_test.py`, `security/baseline-final.md` |
| T11 | Tool/MCP output | Prometheus/Kubernetes MCP -> ChatOps summary | Malicious or malformed tool output is summarized as trusted instruction. | Incorrect incident response or unsafe recommendation. | Deterministic intent/permission decision precedes optional bounded read-only summary; audit records gateway degradation. | Backend data integrity and novel output formats remain residual risks. | `chatops-bot/app/worker.py`, `chatops-bot/app/gateway.py` |

## Scope and assumptions

The evidence is local-first. AWS/EKS was not used to create Day 6 runtime
traffic, so no AWS budget or cloud-spend claim is made. The table describes
controls and residual risks; it is not a claim that the application is secure
against all variants of these attacks.
