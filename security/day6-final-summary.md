# InsightHub Day 6 final implementation and evidence summary

## Security

- Frozen dataset SHA-256: `876efc10f774a5837d8e3140ae9556bd0610d08841d8470b8728c01b13b2194c`.
- Promptfoo initial: 37/51 passed, 14 failed, 0 errors.
- Promptfoo final: 45/51 passed, 6 failed, 0 errors, 0 HIGH, 0 CRITICAL.
- Runtime guardrails remain active for direct input, retrieved context, output,
  PII, excessive agency, and prompt extraction.
- Supplemental indirect-injection evidence and benign RAG evidence are preserved.

Evidence: `security/baseline-initial.md`, `security/baseline-final.md`,
`security/evidence/promptfoo-initial.json`,
`security/evidence/promptfoo-final.json`,
`security/evidence/supplemental-indirect-final.json`.

## Governance and gateway

LiteLLM remains pinned to `ghcr.io/berriai/litellm:v1.90.2` with a separate
persistent PostgreSQL database. Workloads use separate virtual keys and model
allowlists:

| Workload | Allowed model aliases | Configured budget |
|---|---|---:|
| InsightHub | `insighthub-chat`, `insighthub-embedding` | $0.50 |
| ChatOps | `chatops-summary` | $0.25 |
| coding | `coding-review` | $0.50 |

InsightHub chat and embedding, ChatOps summary, and coding review all produced
real gateway traffic. A coding-key request for the InsightHub model was denied
with HTTP 403. Workload containers receive gateway virtual keys; the LiteLLM
master key is restricted to gateway administration/export.

## FinOps

LiteLLM `/spend/logs` is the authoritative source available in the pinned
runtime. It provides model, token counts, spend, duration, status, and
`user_api_key_alias`. The new internal exporter allowlists only the three
workload aliases and exposes no keys, prompts, responses, document IDs, or
user identifiers.

The existing Prometheus server now scrapes `litellm-finops-exporter:9108`.
The separate dashboard is `observability/grafana-day6-finops.json`.

Observed spend-log window:

| Workload | Requests | Successful | Input tokens | Output tokens | Spend | Cost/success |
|---|---:|---:|---:|---:|---:|---:|
| InsightHub | 8 | 5 | 204 | 34 | $0.00075462 | $0.000150924 |
| ChatOps | 1 | 1 | 64 | 16 | $0.00032 | $0.00032 |
| coding | 2 | 1 | 1,251 | 600 | $0.009702 | $0.009702 |

Success means a successful provider/gateway result for the workload’s bounded
operation: successful InsightHub provider records, successful ChatOps summary,
and a successfully written coding review proposal. These are current observed
costs only; no before/after savings claim is made.

The Prometheus exporter exposes spend, tokens, requests by outcome, configured
budget, budget utilization, cost per success, and duration. Budget-denied
series remain empty when LiteLLM does not retain a classified denial record;
the exporter does not fabricate one.

## Budget evidence

Sequential probe: configured budget `$0.001`; 16 requests returned 200, then
four returned 429; final recorded spend was `$0.001056`, an observed `$0.000056`
overshoot.

Concurrent probe: configured budget `$0.001`, concurrency 4, all four requests
returned 200 while the immediate `/key/info` spend result was `$0.0`. This is
retained as an accounting-delay result, not a proof of zero cost or a hard-cap
failure.

LiteLLM `max_budget` is a gateway control with accounting/update timing; this
lab does not claim it is an absolute synchronous hard cap under concurrency.

Evidence and runner: `security/litellm_budget_test.py`.

## AWS Budgets

Day 6 traffic was completed locally. No AWS budget was created and no AWS
budget evidence is claimed. LiteLLM remains the runtime control for this lab;
AWS Budgets would be a delayed financial alert if AWS were exercised.

## Threat model and OWASP mapping

`security/threat-model.md` documents 11 threats with assets, boundaries,
attack paths, controls, evidence, and residual risk. It covers direct and
indirect injection, RAG poisoning, PII, excessive agency, prompt extraction,
provider bypass, virtual-key leakage, denial-of-wallet, concurrent overshoot,
and malicious MCP output.

`security/owasp-mapping.md` maps implemented controls to the course’s OWASP-
oriented LLM/agent concepts and distinguishes evidence from limitations.

## Verification

- LiteLLM health: HTTP 200.
- Prometheus FinOps target: `up`.
- Prometheus real spend series: all three workload aliases present.
- ChatOps tests: 14 passed.
- Python compile checks: passed.
- Dashboard JSON validation: passed.
- Compose configuration validation: passed.
- `git diff --check`: passed.
- Backend suite: 38 tests passed, one integration setup error remained. The
  error is `psycopg_pool.PoolTimeout` in `IntegrationTests.setUpClass`; a direct
  connection and isolated pool readiness check succeed, so this remains a test
  orchestration/pool initialization issue rather than an assertion failure.

## Remaining limitations

1. LiteLLM’s pinned runtime did not expose a Prometheus `/metrics` endpoint;
   the exporter therefore uses authenticated `/spend/logs` polling.
2. Spend-log retention and concurrent accounting timing limit strict real-time
   budget conclusions.
3. The current evidence window is bounded and not a production FinOps trend.
4. No AWS usage or AWS Budgets artifact exists for this local-only exercise.
5. Existing Phase 2 Promptfoo residual failures remain documented; this closeout
   does not claim all adversarial cases pass.
