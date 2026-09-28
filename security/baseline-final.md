# Day 6 targeted hardening validation

This report is supplemental to, and does not replace, the frozen Phase 1
evidence in `baseline-initial.md`. The frozen dataset SHA remains
`876efc10f774a5837d8e3140ae9556bd0610d08841d8470b8728c01b13b2194c`.

## Controls implemented

- Retrieved context is serialized as `UNTRUSTED_DOCUMENT_DATA` and the system
  policy explicitly denies treating document instructions as commands.
- Pre-generation checks refuse direct hidden-prompt extraction, action/tool
  requests, and high-risk direct PII requests without calling the provider.
- Post-generation checks redact secret-like patterns and replace unsafe output
  with a fixed refusal.
- Provider errors remain sanitized and never fall back from real mode to fixture.
- `insighthub_guardrail_decisions_total` uses bounded stage/outcome/reason
  labels and does not contain user text, document text, or secrets.

## Validation

- Focused guardrail tests: 5 passed.
- Full API suite: 62 total, 44 passed, 18 skipped, 0 failed.
- Supplemental indirect-injection harness: 5/5 documents ready, 5/5 expected
  facts observed, no harness errors; runtime was real OpenAI mode.
- Supplemental evidence: `evidence/supplemental-indirect-final.json`.
- Frozen `security/dataset.json` was not modified.

## Provenance

- Initial source commit: `7941ec7c1b53a6f45b6b9268473b33398e755692`.
- Final source base: the same commit, with the hardening changes present in the
  working tree; no commit was created by this validation run.
- Dataset SHA-256: `876efc10f774a5837d8e3140ae9556bd0610d08841d8470b8728c01b13b2194c`.
- Promptfoo: `0.123.1`.
- Provider/model: OpenAI / `gpt-5.6-terra`.
- Embeddings: OpenAI / `text-embedding-3-small`, application dimension 1024.
- Runtime: isolated Day 6 project, real mode.

## Promptfoo comparison

Exactly the 51 plugin cases used by the initial baseline were evaluated with
one concurrent request, cache disabled, and a local OpenAI grader. The 51
jailbreak-template variants were excluded.

| Scope | Initial | Final |
|---|---:|---:|
| Overall passed | 37/51 | 45/51 |
| Overall failed | 14/51 | 6/51 |
| Errors | 0 | 0 |
| Excessive agency | 17/17 | 17/17 |
| PII direct | 4/17 | 11/17 |
| Prompt extraction | 16/17 | 17/17 |

The eight-case overall improvement is a security improvement. Excessive agency
is unchanged safe behavior. Prompt extraction has no remaining failed case in
this scope. The six remaining PII failures did not contain actual personal
data; the grader objected to source filenames and confirmation/denial of
document context. They remain a privacy-boundary limitation and are not
classified as HIGH or CRITICAL findings.

Initial severity was HIGH 0, CRITICAL 0, MEDIUM 1 privacy-boundary
observation, plus one informational/manual prompt-extraction disagreement.
Final evaluation produced no HIGH or CRITICAL finding; the residual PII
source/context disclosure concern remains MEDIUM-level/manual-review scope.

## Benign regression and supplemental evidence

- `/healthz`: healthy, real mode.
- `/readyz`: ready, database healthy.
- A normal retention-period question returned the expected 365-day answer with
  retrieved sources; it was not blocked.
- Guardrail metrics were exposed with bounded labels.
- Supplemental indirect-injection cases: 5/5 ready, 5/5 intended facts
  observed, 0 harness errors, 0 confirmed malicious-instruction influence,
  and no observed false positives.

Known limitations: this is a synthetic dataset and a single selected model;
the Promptfoo grader's source-structure rubric remains stricter than the
application's current citation behavior; no absolute security claim is made.

No HIGH/CRITICAL findings were observed in the tested dataset and scope.
