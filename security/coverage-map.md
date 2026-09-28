# Day 6 initial baseline coverage

Dataset: `security/dataset.json` (60 stable cases)

| Coverage | Case IDs | Count |
|---|---|---:|
| Direct prompt injection / instruction override | direct-001..010 | 10 |
| Jailbreak / system-prompt extraction | jailbreak-001..010 | 10 |
| PII exposure | pii-001..010 | 10 |
| Excessive agency | agency-001..010 | 10 |
| Indirect prompt injection | indirect-001..005 | 5 |
| RAG poisoning | rag-001..005 | 5 |
| Benign RAG regression | benign-001..010 | 10 |
| **Total** |  | **60** |

The ID ranges above intentionally use ten direct/jailbreak/PII/agency/benign cases
and five indirect/RAG cases. The dataset currently contains 60 cases; all cases
must execute before the baseline can be considered complete.

Promptfoo's direct HTTP target covers direct injection, jailbreak, PII, excessive
agency, and benign questions. The custom adapter covers indirect injection and
RAG poisoning through the real upload and retrieval path.
