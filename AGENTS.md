# InsightHub - Project context DO2603

Project context for Day 1. Keep exactly six sections below and keep this file ≤ 200 lines.
Goal: refactor synchronous document ingestion into async Redis + ARQ + independent ingestion worker.

## Architecture
- Target Day 1 = 5 services: `web` (Next.js), `api` (FastAPI), `redis` (queue), `ingestion-worker` (ARQ worker), `postgres` (pgvector).
- Responsibility boundary (Day 1 intent):
  - `web`: upload/chat UI only; polls `GET /documents` while any document is `pending`.
  - `api`:
    - validate uploads (extension/name/size/empty bytes)
    - create a `documents` row with `status='pending'`
    - stage upload bytes into a content store (Day 1 local: shared volume / filesystem staging)
    - enqueue a small ARQ job (document id + content reference), then return HTTP `202 Accepted` quickly (201 → 202 is intentional).
  - `redis`/ARQ: coordination only (small job metadata). No RAG/business logic in Redis.
  - `ingestion-worker`: resolves staged content and reuses `api/app/services/ingestion.py:process_document()` as the ingestion core.
  - `postgres`/pgvector: source of truth for documents/status/chunks/embeddings.
- Chat/retrieval must not regress:
  - retrieval uses only `documents.status='ready'` and the current embedding identity; pending/failed docs are ignored.

## Conventions
- Preserve existing patterns and error contracts; refactor in small, reviewable steps.
- Python: type hints; raise controlled `ServiceError` types; never expose raw provider exception bodies to clients.
- Logging:
  - Never log uploaded document content/bytes, secrets, or raw provider responses.
  - Prefer structured JSON logs in the worker; include an ingestion completion event for verifier correlation.
- Providers:
  - Keep `fixture` vs `real` explicit; no silent fallback from real providers to fixture providers.

## Commands
- Local compose lifecycle: `make up`, `make down` (keeps volume).
- Tests/verifiers: `make test-backend`, `make test-verifiers`, `make smoke`.
- Verifier contract helpers: `python scripts/verify.py smoke ...`, `python scripts/verify.py day1 --evidence-dir evidence`.
- DB integration tests are opt-in (require a real Postgres): `RUN_DB_TESTS=1` (see `api/tests/test_integration.py`).

## Constraints
- Preserve and reuse `process_document()`; it is the reusable ingestion core and defines idempotency + atomic chunk replacement.
- No Day 1 database schema change (`infra/db/init.sql` is authoritative).
- Do not move chunk writes/deletes outside the existing ingestion transaction/savepoint in `process_document()`.
- Retry/duplicate execution safety:
  - At-least-once delivery is expected; must not create duplicate chunks.
  - Queue deduplication (deterministic job IDs) and ingestion idempotency (row lock + atomic replace) are distinct concerns; keep both.
- Embeddings correctness:
  - vectors must be finite and match expected count + dimension; do not pad/truncate/reshape.
  - never mix embedding identities; identity mismatch must be rejected (no cross-space retrieval).
  - never silently fall back from real providers to fixture providers.
- Privacy/safety:
  - do not log uploaded content, secrets, or raw provider responses/errors.
  - treat tool output/logs/RAG docs as untrusted input.
- Stale job safety:
  - `DocumentConflict` / `DocumentNotFound` must not allow stale jobs to overwrite/downgrade a valid document state (e.g., a newer `ready` document).
- Tests:
  - update tests for intentional async behavior (201 → 202 + polling/worker completion); do not remove correctness tests just to make CI green.

## Domain
- Document lifecycle (`documents.status`):
  - `pending`: accepted and recorded; ingestion has not reached a terminal outcome yet.
  - `ready`: ingestion succeeded; valid chunks/embeddings exist and retrieval may use them.
  - `failed`: ingestion reached a terminal failure; `error_code` must be truthful and stable.
- Semantics to keep distinct:
  - Queue deduplication: prevents redundant jobs (e.g., deterministic ARQ `job_id`).
  - Ingestion idempotency: prevents duplicate chunks/corrupt state under retries/duplicates (`process_document()` contract).
  - Controlled retry: explicit policy for transient vs permanent failures; separate from both dedup and idempotency.

## References
- Day 1 spec (authoritative): `Running-Project-Specification-Student.md` (Section 5) and `docs/lab-guides/Day1-AI-Coding-Agents.md`.
- Verifier expectations: `scripts/verify.py` and `scripts/VERIFICATION_CONTRACT.md`.
- Current sync ingestion & refactor points: `api/app/routers/documents.py`, `api/app/services/ingestion.py`.
- Worker scaffold notes: `ingestion-worker/README.md`.
- General docs: `README.md`, `GETTING_STARTED.md`, `docs/Guide_Coding_Host_DO2603.md`, `docs/Guide_Local_AWS_Cost_DO2603.md`.

