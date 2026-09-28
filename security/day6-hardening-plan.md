# Day 6 hardening plan

The frozen Phase 1 dataset and initial report remain immutable. This plan
addresses the observed trust-boundary risks without changing retrieval,
ingestion, embeddings, queue semantics, ChatOps, or provider routing.

| Observation | Control | Verification |
|---|---|---|
| Retrieved text is untrusted data | Structured context envelope and authoritative system policy | Prompt serialization and supplemental cases |
| Direct hidden-instruction requests | Pre-generation extraction refusal | No-provider-call test |
| Action/tool requests | Pre-generation excessive-agency refusal | No-provider-call test |
| Sensitive PII requests | Conservative refusal for high-risk fields | Unit test/manual review |
| Secret-like model output | Post-generation bounded redaction | Unit test |
| Provider failures | Existing sanitized ProviderError plus error metric | Provider regression tests |
| Operational visibility | Low-cardinality stage/outcome/reason counter | Metrics exposition |

The supplemental dataset is separate from `security/dataset.json` and is
labelled SUPPLEMENTAL. Fixture-mode output is harness diagnostics, not a
security finding.
