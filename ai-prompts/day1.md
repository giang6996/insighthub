# Day 1 — AI Prompt Log (Codex)

This file records the meaningful Codex prompts and the corresponding human review decisions used during the Day 1 async-ingestion refactor and verification work. It focuses on prompts that materially changed the engineering outcome (not every small follow-up question).

## Prompt 1 — Repository investigation / refactor planning (no code changes)

**Goal**
- Trace the synchronous ingestion path and where latency/blocking occurs.
- Identify the reusable ingestion core and its contracts (idempotency + atomicity).
- Propose an async refactor shape using Redis/ARQ + independent worker.
- Do not modify any files.

**Important constraints**
- Preserve `process_document()` as the ingestion core and do not weaken its semantics.
- No schema changes for Day 1.
- Keep privacy constraints (no logging content/bytes/secrets/raw provider payloads).

**Short summary of the prompt**
- Investigate the current ingestion flow, find the “core” function that should be reused by the worker, and outline how `POST /documents` should change to return quickly while ingestion runs elsewhere.

**What Codex proposed / discovered**
- Located `api/app/services/ingestion.py:process_document()` as the existing ingestion core.
- Confirmed `process_document()` already provides:
  - a row lock, so concurrent runs serialize per document id;
  - atomic chunk replacement (delete+insert within a savepoint);
  - truthful terminal state writes (`ready`/`failed`) before releasing the lock.
- Proposed Day 1 boundary: API validates + records `pending` + stages bytes + enqueues a small job; worker resolves staged bytes and calls `process_document()`.

**What was accepted**
- Reuse `process_document()` unchanged as the ingestion core.
- Keep Redis as coordination only; do not store document blobs in Redis.

**What was challenged / rejected**
- Rejected any suggestion to “just move logic into the worker” if it duplicates `process_document()` logic or weakens the transaction boundaries.

**Why this prompt improved the implementation**
- It prevented coding before understanding the existing contracts.
- It identified the correct stable seam (`process_document()`) to reuse rather than rewriting ingestion.

## Prompt 2 — Challenge the proposed design (review, failure semantics, transport options)

**Goal**
- Stress-test the design assumptions before cutover.
- Compare upload-content transport options.
- Review `DocumentConflict` / `DocumentNotFound` semantics under stale/duplicate jobs.
- Define Day 1 retry posture (no uncontrolled automatic retries).

**Important constraints**
- Stale jobs must not downgrade a valid terminal document (e.g., a newer `ready` state).
- Do not implement controlled retry yet; keep `max_tries = 1`.
- Do not log content, secrets, raw provider responses, or arbitrary filesystem paths.

**Short summary of the prompt**
- “Given at-least-once delivery, what should the worker do on `DocumentConflict`/`DocumentNotFound`? Should it mark documents as failed? Where should bytes live: Redis payload vs Redis blob store vs shared staging?”

**What Codex proposed / discovered**
- Compared three approaches:
  1. Put bytes in the job payload (rejected due to size and Redis misuse).
  2. Put bytes in Redis as a blob store (rejected; Redis remains coordination only).
  3. Stage bytes in a shared store and pass a small immutable reference (accepted).
- Highlighted that conflicts/not-found can happen with stale jobs if IDs or content references are reused.

**What was accepted**
- Shared staging with an immutable, SHA-256 based `content_ref` (small metadata only in Redis).
- A “skip” posture for stale jobs that prevents state downgrades.
- Dedup via deterministic job IDs is separate from `process_document()`’s idempotency.

**What was challenged / rejected**
- Rejected blindly marking `DocumentConflict` as `failed` because a stale conflict job can downgrade a valid `ready` document.
- Rejected mutating state for `DocumentNotFound` because the row may legitimately be deleted/replaced and a stale job must not recreate or corrupt state.
- Challenged automatic retries: `process_document()` already writes terminal `failed` for handled errors; adding retries without explicit document-state semantics was deferred.

**Why this prompt improved the implementation**
- It demonstrates human review rather than automatic acceptance.
- It forced explicit reasoning about stale jobs and state safety instead of “make it green”.

## Prompt 3 — Validate `AGENTS.md` (project context, 6 sections, ≤200 lines)

**Goal**
- Ensure the repository context file matches the required six sections:
  Architecture, Conventions, Commands, Constraints, Domain, References.
- Keep it ≤200 lines.

**Important constraints**
- The file must stay concise and specific to this repo (not generic).
- It must encode the Day 1 responsibility boundary: `web` UI, `api` validation+enqueue, `ingestion-worker` executes ingestion core.

**Short summary of the prompt**
- “Confirm the repository context file matches the required six sections, stays under 200 lines, and accurately describes the accepted Day 1 async boundary.”

**What Codex proposed / discovered**
- Verified the context described the Day 1 responsibility boundary (`web` upload/chat UI, `api` validate+enqueue, `ingestion-worker` runs ingestion core) and the key safety constraints (no schema change; stale-job safety; privacy/logging rules).
- Verified the file stayed within the ≤200-line limit.

**What was accepted**
- Keep `AGENTS.md` as the single concise Day 1 project context source of truth with six required sections.

**What was challenged / rejected**
- Rejected expanding the context into long narrative or adding extra architecture beyond Day 1 scope.

**Why this prompt improved the implementation**
- It kept subsequent code/test work aligned with explicit constraints and reduced scope creep.

## Implementation prompts (bounded implementation stages)

These were executed in small, reviewable stages and validated with tests/smoke:

**Goal**
- Introduce async ingestion while preserving retrieval/chat correctness.

**Bounded stages**
- Add Redis + ARQ worker + staging helpers alongside the synchronous ingestion core.
- Define an immutable SHA-based `content_ref` for staged payloads.
- Validate the worker’s staged-path handling (content ref validation, staging-dir containment).
- Cut over `POST /documents` from synchronous `201` to async `202` + `pending`, enqueue job, and return quickly.
- Add verifier-facing worker logging and Day 1 milestone tests.

**What Codex proposed / discovered**
- Kept the job payload small (document id + content ref).
- Worker calls synchronous ingestion via `asyncio.to_thread()` to avoid event-loop misuse.

**What was accepted**
- Async boundary with staged bytes + job metadata only in Redis.
- Worker remains independent and reuses `process_document()` unchanged.

**What was challenged / rejected**
- Rejected storing document bytes in Redis.
- Rejected uncontrolled automatic retries (kept `max_tries = 1`).

**Why these prompts improved the implementation**
- They ensured each refactor step had a validation hook (tests, smoke, logs) before moving on.

## Debugging prompt — Investigate repeated six integration-test failures (investigation-only)

**Goal**
- Run the failing backend integration suite once and classify the failures with evidence.
- Do not make speculative fixes; diagnose first.

**Important constraints**
- Respect the process boundary: test process ≠ worker process.
- Do not “fix” by weakening `process_document()` or deleting tests.

**Short summary of the prompt**
- “Run the integration suite, list the six failures, gather worker logs, and determine whether failures are app bugs vs async test-isolation vs stale queue/staging contamination vs process-local mocks not crossing into the worker.”

**What Codex discovered**
- The six failures were all “stuck pending” in the test process.
- Worker logs showed `document_conflict` skips for the corresponding jobs.
- Root causes:
  - integration tests used a random Postgres schema in-process while the external worker used the normal schema;
  - process-local `configured()`, `real_config()`, and `patch(...)` do not apply to the worker container;
  - therefore API/test and worker read/write different `documents` rows, producing conflicts and leaving test-side docs pending.
- The application itself was not demonstrated to be broken; the harness had to reflect the process boundary.

**What was accepted**
- Adjust test isolation to use the same DB schema as the worker for true worker-integration tests.
- Keep provider-specific monkeypatch tests in-process where they can actually control behavior.

**What was challenged / rejected**
- Rejected “just change expectations” without aligning the harness with the out-of-process architecture.

**Why this prompt improved the implementation**
- It prevented thrash and speculative code changes by forcing an evidence-based diagnosis that respected the new out-of-process reality.

## Prompt 4 â€” Implement explicit controlled retry (no automatic retries)

**Goal**
- Add a minimal, explicit controlled-retry feature for terminal failures.
- Reuse the existing Day 1 architecture (API â†’ Redis/ARQ â†’ ingestion-worker â†’ `process_document()`).
- Preserve stale-job safety and privacy constraints.

**Important constraints**
- Controlled retry is explicit (human-triggered) and must not become automatic ARQ retry/backoff.
- Allow retry only from `documents.status='failed'`.
- Reuse the existing immutable staged payload; do not store bytes in Redis; do not add a new storage system.
- Keep worker `max_tries = 1`; no retry counters/backoff/schedulers; no DB schema change.
- Enqueue failure must not corrupt state: restore the previous failed state/error if enqueue fails.

**Short summary of the prompt**
- â€œImplement `POST /documents/{id}/retry` so a failed document can be retried safely using the existing staged payload and queue, returning 202/pending, without weakening `process_document()` or introducing automatic retries.â€

**What Codex proposed / discovered**
- Confirmed staged payloads are immutable and retained after terminal failures, so retry can reuse the same payload reference derived from the stored content SHA.
- Implemented a retry endpoint that:
  - validates document existence and `status='failed'`;
  - validates the staged payload still exists for that document;
  - transitions `failed â†’ pending` and enqueues a new ingestion job;
  - restores the previous failed state/error if enqueue fails.
- Kept retry and idempotency semantics separate:
  - queue-layer deduplication for normal uploads (deterministic job IDs);
  - ingestion idempotency in `process_document()` (row lock + atomic replace);
  - controlled retry as an explicit policy path.

**What was accepted**
- Explicit `POST /documents/{id}/retry` from `failed` only, returning HTTP 202 with `pending`.
- Reuse immutable staged payload; no automatic retries; keep `max_tries = 1`.
- State safety: invalid retries (ready/pending/missing payload) are rejected without downgrading valid state; enqueue failure restores prior failed state/error.

**What was challenged / rejected**
- Rejected â€œjust increase worker triesâ€ (automatic retry) because it changes document-state semantics and was out of Day 1 scope.
- Rejected adding retry counters, backoff, or a DB schema change for attempt tracking.
- Rejected adding new infrastructure (mock servers, new storage backends) to satisfy retry testing.

**Why this prompt improved the implementation**
- It delivered the Day 1 small feature while keeping the process boundary and safety rules intact.
- It forced retry behavior to be explicit, bounded, and auditable instead of an implicit side effect of queue retries.

## Final decision record (Day 1) — Controlled retry

- Controlled retry is explicit (API-triggered), not automatic ARQ retry/backoff.
- `POST /documents/{id}/retry` is allowed only when the document is currently `failed`.
- The immutable staged payload is reused (no new bytes stored in Redis).
- Document lifecycle: `failed → pending → ready|failed`.
- If enqueue fails, restore the prior `failed` state and `error_code` (no orphan `pending`).
- Worker `max_tries = 1` remains; retry counters/backoff/new DB schema were deliberately avoided.
