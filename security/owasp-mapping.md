# Day 6 OWASP-oriented control mapping

This concise mapping uses the course's LLM/agent threat concepts without
reproducing the source taxonomy. Evidence is version-bound to the repository.

| Concept | InsightHub control | Tested evidence | Remaining limitation |
|---|---|---|---|
| Prompt injection | User-input, context, and output guardrails; explicit untrusted-context prompt boundary. | `security/evidence/promptfoo-final.json` | Detection is heuristic and does not eliminate novel attacks. |
| Insecure output handling | Provider output is checked before returning; errors are typed and sanitized. | `api/app/services/llm.py`, API tests | Downstream consumers must keep treating output as untrusted. |
| Sensitive information disclosure | PII and prompt-extraction checks; no secrets in metrics/audit/exporter labels. | Promptfoo final evidence; `security/finops_exporter.py` | False negatives and provider-side retention are outside this control. |
| Supply-chain / RAG poisoning | Upload uses normal ingestion, ready/current embedding identity filtering, and indirect-injection tests. | `security/evidence/rag-baseline.json` | Source provenance and document authenticity are not established. |
| Excessive agency | Day 5 permission tiers, approval-required writes, denied destructive/unrestricted actions. | Day 5 tests/evidence; `chatops-bot/app/permissions.py` | New tools require separate review and policy coverage. |
| Tool/MCP misuse | Read-only Prometheus/Kubernetes clients, restricted kubeconfig/RBAC, bounded ChatOps summary. | Day 5 MCP tests; `chatops-bot/app/gateway.py` | Malicious tool data can still influence a summary. |
| Governance and attribution | LiteLLM virtual keys, model allowlists, bounded workload labels, spend-log exporter. | Gateway routing and `/spend/logs` evidence; FinOps dashboard JSON | Spend-log retention and concurrent accounting timing remain limitations. |
| Denial of wallet | Per-workload max budgets, budget-denied metric, cost dashboard, sequential/concurrent tests. | `security/litellm_budget_test.py` | LiteLLM budget is not a synchronous hard cap under concurrency. |

Implemented controls are defense-in-depth, not threat elimination claims.
