## Day 1 objective

Day 0 ingestion was synchronous: `POST /documents` read the upload, then ran extraction, chunking, embedding calls, and PostgreSQL writes inside the API request. The endpoint returned HTTP 201 only after ingestion completed, which meant large uploads could block request latency and tie up API workers.

Day 1 refactors the system to an accepted async architecture: FastAPI validates the upload, creates a `documents` row with `status='pending'`, stages the bytes into a shared content store, enqueues a small Redis/ARQ job (document id + immutable content reference), and returns HTTP 202 quickly. An independent `ingestion-worker` process consumes the queue and performs ingestion by calling the existing ingestion core, updating the document to `ready` or `failed` in PostgreSQL. The web and chat flows remain correct by using only `documents.status='ready'` during retrieval.

## Major architectural decisions

The refactor preserves `api/app/services/ingestion.py:process_document()` as the ingestion core. This function already defines the hard correctness requirements: row locking, idempotency for the same document id/bytes/pipeline, atomic chunk replacement inside a savepoint, and truthful terminal status updates (`ready`/`failed`) committed while holding the lock. Reusing it avoids rewriting the most failure-prone logic.

Redis is used for coordination only. The queue payload stays small (document id + content reference), and Redis is not treated as a blob store for 10 MB uploads. To transport document bytes safely across the process boundary, uploads are staged in a shared directory mounted into both the API and the worker. The staged payload is addressed by an immutable SHA-256 based `content_ref`, so a stale job cannot accidentally read a newer payload for the same document id.

The worker is intentionally minimal. It resolves staged bytes, looks up the filename, and calls the synchronous ingestion core via `asyncio.to_thread()` to avoid "event loop already running" issues and to keep the core unchanged. PostgreSQL remains the source of truth for document lifecycle, chunk storage, and embedding identity. No Day 1 database schema changes were introduced. Automatic retries were explicitly avoided by setting `max_tries = 1` to prevent unreviewed retry semantics from downgrading document-state correctness.

## Idempotency and stale-job safety

Three related concerns are kept distinct:

Queue deduplication prevents redundant jobs from being enqueued. This is implemented with deterministic job IDs so that enqueue can be idempotent at the queue layer.

Ingestion idempotency prevents duplicate chunks or corrupt state when a job is executed more than once. `process_document()` enforces idempotency by holding a document row lock, validating that the document id matches the expected filename/content digest/pipeline, and performing chunk replacement atomically within the existing transaction/savepoint.

Controlled retry is a policy decision about which failures should be retried and how that interacts with terminal state. Day 1 implements controlled retry explicitly (human-triggered), without automatic ARQ retries: `POST /documents/{document_id}/retry` is allowed only when the current status is `failed`. It reuses the existing immutable staged payload for that document and enqueues a new ingestion job, returning HTTP 202 with status `pending`. Invalid retries (missing document, already `pending`, already `ready`, missing staged payload) are rejected without mutating a valid state. If enqueue fails, the endpoint restores the prior failed state/error rather than leaving an orphan `pending`.

Duplicate execution was validated by testing that re-processing does not create duplicate chunks and that the final state remains consistent (`ready` with correct `chunk_count`), relying on the existing database uniqueness constraints and the ingestion transaction boundaries.

Stale jobs are expected under at-least-once delivery, especially if external state is cleared between runs. A `DocumentConflict` job must not downgrade a valid document state: a conflict can represent an old content reference, an old pipeline configuration, or a job targeting a reused id. The worker therefore treats such conflicts as stale and skips them rather than mutating the authoritative document row.

## Important AI proposal that was challenged

Early AI suggestions included "mark `DocumentConflict` / `DocumentNotFound` as failed so the UI unblocks". Human review rejected that approach because it is unsafe under at-least-once semantics: a stale conflict job could overwrite or downgrade a newer `ready` document, violating the database-as-source-of-truth rule. The revised approach is to log and skip stale conflict/not-found jobs while leaving the authoritative row untouched.

The same review posture applied to automatic retries. The AI proposal to increase retries was challenged because retries are not "free": they create additional concurrent executions and require explicit semantics for when a failure should be retried versus treated as terminal. For Day 1, the worker remained `max_tries = 1`, and retry was implemented as an explicit API action rather than an implicit worker-side retry policy.

## Testing lesson from async architecture

A key Day 1 lesson was that moving ingestion out-of-process changes what test harnesses can safely assume. The backend integration suite initially failed six tests repeatedly with documents stuck in `pending`. Worker logs showed `document_conflict` skips, which looked like an application bug at first glance.

Investigation showed the root cause was test isolation crossing a new process boundary. The integration tests created a random PostgreSQL schema and patched `db._pool` only inside the test/API process, while the external worker continued using its normal database schema. As a result, the API/test process and the worker were reading and writing different `documents` rows. Additionally, process-local settings patches (`configured()`, `real_config()`) and Python monkeypatching (`patch(...)`) cannot affect the independent worker container; they only apply in-process.

The fix was to align the harness with the architecture: real worker-integration tests were changed to use the worker's normal schema and isolate state by truncating tables, clearing Redis state, and cleaning staged payload files. Provider-specific tests that rely on monkeypatching provider transports were kept in-process by calling `process_document()` directly, because that is the only scope where the patches are valid. `RESTART IDENTITY` was avoided in async tests to reduce collisions where stale jobs for document id N could be misapplied to a new document id N after identity reset.

This was not merely "making tests green"; it was an enforcement of the real boundary: when ingestion moves to a separate process, tests must treat the worker as an independent actor with its own configuration and database connections.

## Final validated Day 1 state

The current validated state is the Day 1 async architecture working end-to-end:

Five Compose services are healthy (`web`, `api`, `redis`, `ingestion-worker`, `postgres`). Upload returns HTTP 202 with an initial `pending` status, and the worker transitions the document to `ready` or `failed` within bounded time. Chat works after `ready` and ignores `pending`/`failed` documents. Upload bytes are staged immutably via SHA-256 based `content_ref`. Duplicate processing does not create duplicate chunks due to the ingestion transaction boundaries and idempotency rules. The backend test suite passes (54 tests), Day 1 milestone tests pass (6 tests), and the smoke verifier passes. The worker emits verifier-readable standalone JSON `ingestion_completed` events (including `document_id`, `status`, and RFC3339 timestamps) that can be correlated to the upload performed by the verifier. The Day 1 controlled-retry feature is implemented and validated: a document in terminal `failed` can transition `failed -> pending -> ready|failed` via `POST /documents/{document_id}/retry`, reusing the original staged payload, without automatic ARQ retries and without duplicating chunks.

## Remaining work

Day 1 implementation is complete (async ingestion + worker + controlled retry). The remaining work is limited to: regenerating the final evidence manifest (`evidence/day1.json`) after the last documentation edits settle, running the Day 1 verifier to completion with fresh evidence, and creating the required Day 1 PR.
