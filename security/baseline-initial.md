# InsightHub Day 6 INITIAL real-provider security baseline

Status: **frozen before Phase 2 mitigations**

Evaluation timestamp: `2026-09-27T10:48:43.136Z`

## Runtime and provenance

- Compose project: `insighthub-day6`
- API target: `http://localhost:18006/chat`
- Chat provider/model: OpenAI / `gpt-5.6-terra`
- Embedding provider/model: OpenAI / `text-embedding-3-small`
- Stored/requested embedding dimension: `1024`
- Runtime mode: `real`
- Promptfoo: `0.123.1`
- Dataset SHA-256: `876efc10f774a5837d8e3140ae9556bd0610d08841d8470b8728c01b13b2194c`
- Source Git commit: `7941ec7c1b53a6f45b6b9268473b33398e755692`

The real runtime used the isolated `insighthub-day6_pgdata` volume. The
existing `insighthub-do2603_pgdata` volume remained untouched and retained 30
documents with the fixture embedding identity.

## Corpus and benign precheck

The temporary verification document was removed only from the isolated Day 6
database. One controlled benign corpus document was uploaded through
`POST /documents`, processed asynchronously, and reached `ready` with one
real embedding chunk.

Three bounded benign precheck cases returned HTTP 200 with real mode,
OpenAI provider metadata, non-empty answers, and the expected retrieved
context. The predefined 10-case benign regression set also returned HTTP 200
for all 10 cases with no provider errors observed in the API log.

## Promptfoo direct evaluation

Generation used the local OpenAI provider with
`PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true`. The remote-only
`system-prompt-override` plugin was excluded from the successful local
generation because Promptfoo `0.123.1` explicitly refuses to generate it when
hosted generation is disabled. System-prompt extraction remained covered by
the `prompt-extraction` plugin.

- Generated cases: `102` (51 plugin cases plus 51 strategy variants)
- Executed cases: `51`
- Passed: `37`
- Failed: `14`
- Errors: `0`
- Unexecuted generated cases: `51`
- Generation errors in the successful artifact: `0`
- Generation token usage: `2,346`
- Evaluation/grading token usage: `44,277`

The executed 51 cases were 17 excessive-agency, 17 PII-direct, and 17
prompt-extraction cases. The unexecuted strategy variants remain in the
generated artifact and are not counted as security passes.

Observed Promptfoo results:

| Category | Executed | Passed | Failed | Interpretation |
|---|---:|---:|---:|---|
| Excessive agency | 17 | 17 | 0 | No observed tool/action execution; safe result |
| PII direct | 17 | 4 | 13 | No PII values disclosed; responses often confirmed absence/source |
| Prompt extraction | 17 | 16 | 1 | Placeholders/document text, not the hidden system prompt |

No confirmed HIGH or CRITICAL vulnerability is claimed from these results.
The PII grader failures are a privacy-boundary observation, not evidence of
actual personal-data disclosure. The prompt-extraction failure did not contain
the hidden system prompt.

## Real indirect-injection/RAG poisoning

The genuine harness executed 10 cases through upload, ARQ ingestion, real
embedding, PostgreSQL/pgvector retrieval, and real chat generation.

- Cases: `10`
- Documents ready: `10`
- Harness errors: `0`
- Intended poison chunks retrieved: `10/10`
- Intended chunk rank: `1` in all cases
- Runtime/provider/model: `real` / `openai` / `gpt-5.6-terra`
- Confirmed attack successes: `0/10`
- Legitimate safe outcomes: `10/10`

All five RAG-poisoning cases returned the useful synthetic fact while ignoring
the embedded malicious instruction. The five indirect-injection cases
retrieved their synthetic documents but did not contain the requested
operations-guide facts; they were reported as unavailable rather than treated
as model resistance. This is a test-data limitation, not a security pass.

Detailed document IDs, chunk IDs, ranks, similarities, and bounded response
evidence are in `security/evidence/rag-baseline.json`.

## Findings inventory

Confirmed finding severity counts:

- HIGH: `0`
- CRITICAL: `0`
- MEDIUM: `1` category-level privacy-boundary observation from PII cases
- LOW: `0`
- Informational/manual review: prompt-extraction grader disagreement

The initial run did not demonstrate actual PII disclosure, hidden-system-prompt
disclosure, excessive agency, or successful indirect prompt injection.

## Regression verification

The existing API suite completed after evaluation:

```text
57 tests
39 passed
18 skipped
0 failed
```

## Evidence

- `security/evidence/promptfoo-generated.yaml`
- `security/evidence/promptfoo-initial.json`
- `security/evidence/rag-baseline.json`
- `security/dataset.json`
- `security/coverage-map.md`

This report represents the unmitigated real-provider baseline. No Phase 2
security changes were implemented.
