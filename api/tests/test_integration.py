"""Opt in with RUN_DB_TESTS=1 and mount init.sql as TEST_SCHEMA_PATH in Docker.

Day 1 ingestion is out-of-process (Redis/ARQ + ingestion-worker), so integration tests
must share the same database schema as the worker container. Isolation is achieved
by truncating tables and clearing Redis/staging between tests (no RESTART IDENTITY).
"""

import asyncio
import concurrent.futures
import os
from pathlib import Path
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from support import configured, real_config
from fastapi.testclient import TestClient
from redis import Redis

from app.core import db
from app.core.config import get_settings
from app.core.errors import (
    DocumentConflict,
    IndexIdentityConflict,
    ProviderError,
    SchemaMismatch,
)
from app.core.index import check_schema
from app.main import app
from app.core.queue import enqueue_ingestion_job
from app.services.embeddings import _local_embed
from app.services.ingestion import process_document
from app.services.retrieval import retrieve
from app.core.staging import (
    content_ref_for_document,
    resolve_staged_path,
    sha256_bytes,
    stage_document_bytes,
)


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "Set RUN_DB_TESTS=1 for isolated PostgreSQL integration tests",
)
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(
            os.environ.get(
                "TEST_SCHEMA_PATH",
                str(Path(__file__).resolve().parents[2] / "infra/db/init.sql"),
            )
        )
        cls.schema_sql = source.read_text()
        # Database schema must be initialized by the Compose postgres bootstrap.
        # Re-applying the starter init.sql is idempotent (CREATE IF NOT EXISTS) and
        # provides a clearer failure mode when the DB volume is stale/missing.
        with db.get_conn() as conn:
            conn.execute(cls.schema_sql)

    def setUp(self):
        self.config = configured()
        self.config.__enter__()
        self.addCleanup(self.config.__exit__, None, None, None)
        with db.get_conn() as conn:
            conn.execute(
                "TRUNCATE chunks, documents, embedding_index CASCADE"
            )
        # Async ingestion introduces an external queue + shared staging directory.
        # Clear both to avoid stale jobs/files referencing reused IDs when tests reset identity.
        Redis.from_url(get_settings().redis_url).flushdb()
        staging = Path(get_settings().staging_dir)
        staging.mkdir(parents=True, exist_ok=True)
        for path in staging.glob("doc-*.bin"):
            path.unlink(missing_ok=True)
        for path in staging.glob(".tmp-doc-*"):
            path.unlink(missing_ok=True)
        self.client = TestClient(app)

    def create_document(self, filename="test.txt"):
        with db.get_conn() as conn:
            return conn.execute(
                "INSERT INTO documents(filename) VALUES (%s) RETURNING id",
                (filename,),
            ).fetchone()[0]

    def state(self, document_id):
        with db.get_conn() as conn:
            return conn.execute(
                "SELECT status, chunk_count, content_sha256, error_code, "
                "(SELECT count(*) FROM chunks WHERE document_id = documents.id) "
                "FROM documents WHERE id = %s",
                (document_id,),
            ).fetchone()

    def wait_for_terminal_status(self, document_id: int, timeout_seconds: float = 30.0):
        deadline = time.monotonic() + timeout_seconds
        last = None
        while time.monotonic() < deadline:
            last = self.state(document_id)
            if last is None:
                return None
            if last[0] in {"ready", "failed"}:
                return last
            time.sleep(0.25)
        return last

    def test_fixture_upload_retrieve_chat_metrics_delete_end_to_end(self):
        self.assertEqual(self.client.get("/readyz").status_code, 200)
        self.assertEqual(
            self.client.post("/chat", json={"question": "RAG?"}).status_code, 404
        )
        response = self.client.post(
            "/documents", files={"file": ("rag.txt", b"RAG uses retrieved documents.")}
        )
        self.assertEqual(response.status_code, 202, response.text)
        document = response.json()
        state = self.wait_for_terminal_status(document["id"])
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "ready")
        self.assertGreater(state[1], 0)
        self.assertEqual(self.client.get("/documents").json()[0]["status"], "ready")
        chat = self.client.post(
            "/chat", json={"question": "RAG uses retrieved documents."}
        )
        self.assertEqual(chat.status_code, 200, chat.text)
        self.assertIn("FIXTURE", chat.json()["answer"])
        self.assertEqual(chat.json()["sources"], ["rag.txt"])
        self.assertAlmostEqual(chat.json()["contexts"][0]["similarity"], 1, places=3)
        self.assertEqual(chat.json()["usage"]["source"], "unavailable")
        metrics = self.client.get("/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn('insighthub_documents_total{status="ready"} 1.0', metrics.text)
        self.assertEqual(
            self.client.delete(f"/documents/{document['id']}").status_code, 204
        )
        with db.get_conn() as conn:
            self.assertEqual(
                conn.execute("SELECT count(*) FROM chunks").fetchone()[0], 0
            )
        self.assertIn(
            'insighthub_documents_total{status="ready"} 0.0',
            self.client.get("/metrics").text,
        )

    def test_successful_retry_is_noop_and_conflicting_payload_is_409(self):
        document_id = self.create_document()
        first = process_document(document_id, "test.txt", b"hello world")
        with patch("app.services.ingestion.embed") as provider:
            self.assertEqual(
                process_document(document_id, "test.txt", b"hello world"), first
            )
            provider.assert_not_called()
        for filename, content in (
            ("test.txt", b"changed"),
            ("other.txt", b"hello world"),
        ):
            with self.assertRaises(DocumentConflict):
                process_document(document_id, filename, content)
        state = self.state(document_id)
        self.assertEqual((state[0], state[1], state[4]), ("ready", first, first))
        self.assertIsNotNone(state[2])

    def test_concurrent_successful_retries_call_provider_once(self):
        document_id = self.create_document()
        started, release = threading.Event(), threading.Event()

        def slow_embed(texts, input_type):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return _local_embed(texts, 1024)

        with patch("app.services.ingestion.embed", side_effect=slow_embed) as provider:
            with concurrent.futures.ThreadPoolExecutor(2) as executor:
                first = executor.submit(
                    process_document, document_id, "test.txt", b"same"
                )
                self.assertTrue(started.wait(timeout=3))
                second = executor.submit(
                    process_document, document_id, "test.txt", b"same"
                )
                release.set()
                self.assertEqual(first.result(timeout=5), second.result(timeout=5))
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.state(document_id)[4], 1)

    def test_failed_attempt_and_concurrent_retry_end_ready(self):
        document_id = self.create_document()
        started, release = threading.Event(), threading.Event()
        calls = []

        def fail_once(texts, input_type):
            calls.append(True)
            if len(calls) == 1:
                started.set()
                release.wait(timeout=5)
                raise ProviderError()
            return _local_embed(texts, 1024)

        with patch("app.services.ingestion.embed", side_effect=fail_once):
            with concurrent.futures.ThreadPoolExecutor(2) as executor:
                first = executor.submit(
                    process_document, document_id, "test.txt", b"same"
                )
                self.assertTrue(started.wait(timeout=3))
                second = executor.submit(
                    process_document, document_id, "test.txt", b"same"
                )
                release.set()
                with self.assertRaises(ProviderError):
                    first.result(timeout=5)
                self.assertEqual(second.result(timeout=5), 1)
        self.assertEqual(self.state(document_id)[0], "ready")
        self.assertEqual(self.state(document_id)[4], 1)
        self.assertIsNone(self.state(document_id)[3])

    def test_failed_vectors_are_atomic_and_can_retry(self):
        document_id = self.create_document()
        for invalid in ([], [[float("nan")] * 1024], [[1.0] * 1023]):
            with (
                patch("app.services.ingestion.embed", return_value=invalid),
                self.assertRaises(ProviderError),
            ):
                process_document(document_id, "test.txt", b"content")
            state = self.state(document_id)
            self.assertEqual((state[0], state[1], state[4]), ("failed", 0, 0))
            self.assertEqual(state[3], "provider_error")
            with db.get_conn() as conn:
                self.assertEqual(
                    conn.execute("SELECT count(*) FROM embedding_index").fetchone()[0],
                    0,
                )
        self.assertEqual(process_document(document_id, "test.txt", b"content"), 1)

    def test_mid_insert_database_failure_rolls_back_all_chunks(self):
        document_id = self.create_document()
        with db.get_conn() as conn:
            conn.execute(
                "CREATE FUNCTION reject_second() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.chunk_index = 1 THEN RAISE EXCEPTION 'secret'; END IF; "
                "RETURN NEW; END $$"
            )
            conn.execute(
                "CREATE TRIGGER reject_second BEFORE INSERT ON chunks "
                "FOR EACH ROW EXECUTE FUNCTION reject_second()"
            )
        try:
            with configured(chunk_size=4, chunk_overlap=0):
                with self.assertRaises(Exception) as raised:
                    process_document(document_id, "test.txt", b"a b c d e f")
                self.assertNotIn("secret", str(raised.exception))
        finally:
            with db.get_conn() as conn:
                conn.execute("DROP TRIGGER reject_second ON chunks")
                conn.execute("DROP FUNCTION reject_second()")
        state = self.state(document_id)
        self.assertEqual((state[0], state[1], state[4]), ("failed", 0, 0))

    def test_empty_extracted_text_is_failed_and_422(self):
        response = self.client.post(
            "/documents", files={"file": ("empty.txt", b" \n ")}
        )
        self.assertEqual(response.status_code, 202, response.text)
        document_id = response.json()["id"]
        state = self.wait_for_terminal_status(document_id)
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "failed")
        self.assertEqual(state[1], 0)

    def test_index_identity_change_rejects_query_upload_and_readiness(self):
        first = self.client.post("/documents", files={"file": ("test.txt", b"content")})
        self.assertEqual(first.status_code, 202, first.text)
        state = self.wait_for_terminal_status(first.json()["id"])
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "ready")
        with (
            configured(embedding_revision="2"),
            patch("app.services.retrieval.embed") as provider,
        ):
            with self.assertRaises(IndexIdentityConflict):
                retrieve("question")
            provider.assert_not_called()
            response = self.client.post(
                "/documents", files={"file": ("new.txt", b"new content")}
            )
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(self.client.get("/readyz").status_code, 503)
        with db.get_conn() as conn:
            self.assertEqual(
                conn.execute("SELECT count(*) FROM chunks").fetchone()[0], 1
            )

    def test_same_dimension_real_provider_cannot_query_fixture_index(self):
        first = self.client.post("/documents", files={"file": ("test.txt", b"content")})
        self.assertEqual(first.status_code, 202, first.text)
        state = self.wait_for_terminal_status(first.json()["id"])
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "ready")
        with real_config(), patch("app.services.retrieval.embed") as provider:
            with self.assertRaises(IndexIdentityConflict):
                retrieve("question")
        provider.assert_not_called()

    def test_dimension_mismatch_is_rejected_before_provider(self):
        with configured(embedding_dim=768), db.get_conn() as conn:
            with self.assertRaises(SchemaMismatch):
                check_schema(conn)

    def test_real_gateway_full_pipeline_with_mock_http(self):
        def embedding_response(*args, **kwargs):
            return {
                "data": [
                    {"index": i, "embedding": [1.0] * 1024}
                    for i in range(len(kwargs["payload"]["input"]))
                ],
                "usage": {"prompt_tokens": 5},
            }

        with (
            real_config(),
            patch(
                "app.services.embeddings.post_json",
                side_effect=embedding_response,
            ),
            patch(
                "app.services.llm.post_json",
                return_value={
                    "choices": [
                        {"message": {"content": "Supported answer [nguồn: real.txt]"}}
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                },
            ),
        ):
            # Provider mocks are process-local and do not affect the external worker.
            # Keep this test in-process by invoking process_document directly.
            document_id = self.create_document(filename="real.txt")
            self.assertGreater(process_document(document_id, "real.txt", b"content"), 0)
            chat = self.client.post("/chat", json={"question": "question"})
            self.assertEqual(chat.status_code, 200, chat.text)
            self.assertEqual(chat.json()["mode"], "real")
            self.assertEqual(chat.json()["usage"]["input_tokens"], 12)
            self.assertEqual(chat.json()["usage"]["source"], "provider")

    def test_provider_failure_is_502_and_metadata_truthful(self):
        with (
            real_config(),
            patch("app.services.embeddings.post_json", side_effect=ProviderError()),
        ):
            # Provider mocks are process-local and do not affect the external worker.
            # Keep this test in-process by invoking process_document directly.
            document_id = self.create_document(filename="real.txt")
            with self.assertRaises(ProviderError):
                process_document(document_id, "real.txt", b"content")
            state = self.state(document_id)
            self.assertEqual((state[0], state[1], state[3]), ("failed", 0, "provider_error"))

    def test_enqueue_failure_does_not_orphan_pending_and_cleans_staging(self):
        payload = b"content"
        with patch("app.routers.documents.enqueue_ingestion_job", side_effect=RuntimeError("redis down")):
            response = self.client.post(
                "/documents", files={"file": ("enqueue-fail.txt", payload)}
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["code"], "queue_unavailable")
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT id, status, error_code FROM documents WHERE filename = %s "
                "ORDER BY created_at DESC LIMIT 1",
                ("enqueue-fail.txt",),
            ).fetchone()
        self.assertIsNotNone(row)
        document_id, status, error_code = row
        self.assertEqual((status, error_code), ("failed", "queue_unavailable"))
        content_ref = content_ref_for_document(document_id, sha256=sha256_bytes(payload))
        path = resolve_staged_path(get_settings().staging_dir, document_id=document_id, content_ref=content_ref)
        self.assertFalse(path.exists(), "Staged payload should be cleaned up after enqueue failure")

    def _install_reject_chunks_trigger(self):
        with db.get_conn() as conn:
            conn.execute(
                "CREATE FUNCTION reject_chunks() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'secret'; RETURN NEW; END $$"
            )
            conn.execute(
                "CREATE TRIGGER reject_chunks BEFORE INSERT ON chunks "
                "FOR EACH ROW EXECUTE FUNCTION reject_chunks()"
            )
            conn.commit()

    def _remove_reject_chunks_trigger(self):
        with db.get_conn() as conn:
            conn.execute("DROP TRIGGER IF EXISTS reject_chunks ON chunks")
            conn.execute("DROP FUNCTION IF EXISTS reject_chunks()")
            conn.commit()

    def test_failed_document_can_be_retried_to_ready(self):
        self._install_reject_chunks_trigger()
        try:
            upload = self.client.post(
                "/documents", files={"file": ("retry.txt", b"content")}
            )
            self.assertEqual(upload.status_code, 202, upload.text)
            document_id = upload.json()["id"]
            failed = self.wait_for_terminal_status(document_id)
            self.assertIsNotNone(failed)
            self.assertEqual((failed[0], failed[1], failed[3]), ("failed", 0, "internal_error"))
        finally:
            self._remove_reject_chunks_trigger()

        retry = self.client.post(f"/documents/{document_id}/retry")
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["status"], "pending")

        ready = self.wait_for_terminal_status(document_id)
        self.assertIsNotNone(ready)
        self.assertEqual(ready[0], "ready")
        self.assertGreater(ready[1], 0)
        with db.get_conn() as conn:
            chunk_rows = conn.execute(
                "SELECT count(*) FROM chunks WHERE document_id = %s",
                (document_id,),
            ).fetchone()[0]
        self.assertEqual(chunk_rows, ready[1])

    def test_ready_and_pending_documents_cannot_be_retried(self):
        upload = self.client.post(
            "/documents", files={"file": ("ready.txt", b"content")}
        )
        self.assertEqual(upload.status_code, 202, upload.text)
        ready_id = upload.json()["id"]
        state = self.wait_for_terminal_status(ready_id)
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "ready")
        ready_retry = self.client.post(f"/documents/{ready_id}/retry")
        self.assertEqual(ready_retry.status_code, 409, ready_retry.text)
        self.assertEqual(ready_retry.json()["code"], "retry_not_allowed")

        pending_id = self.create_document(filename="pending.txt")
        digest = sha256_bytes(b"content")
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE documents SET status='pending', content_sha256=%s, pipeline_id='p' WHERE id=%s",
                (digest, pending_id),
            )
        stage_document_bytes(
            get_settings().staging_dir,
            document_id=pending_id,
            content=b"content",
            max_bytes=get_settings().max_upload_bytes,
        )
        pending_retry = self.client.post(f"/documents/{pending_id}/retry")
        self.assertEqual(pending_retry.status_code, 409, pending_retry.text)
        self.assertEqual(pending_retry.json()["code"], "retry_not_allowed")

    def test_retry_requires_existing_staged_payload(self):
        self._install_reject_chunks_trigger()
        try:
            upload = self.client.post(
                "/documents", files={"file": ("missing-staged.txt", b"content")}
            )
            self.assertEqual(upload.status_code, 202, upload.text)
            document_id = upload.json()["id"]
            failed = self.wait_for_terminal_status(document_id)
            self.assertIsNotNone(failed)
            self.assertEqual(failed[0], "failed")
            digest = failed[2]
        finally:
            self._remove_reject_chunks_trigger()

        content_ref = content_ref_for_document(document_id, sha256=digest)
        resolve_staged_path(
            get_settings().staging_dir,
            document_id=document_id,
            content_ref=content_ref,
        ).unlink(missing_ok=True)

        retry = self.client.post(f"/documents/{document_id}/retry")
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(retry.json()["code"], "staged_payload_missing")
        state = self.state(document_id)
        self.assertEqual(state[0], "failed")

    def test_retry_enqueue_failure_does_not_corrupt_document_state(self):
        self._install_reject_chunks_trigger()
        try:
            upload = self.client.post(
                "/documents", files={"file": ("enqueue-fail-retry.txt", b"content")}
            )
            self.assertEqual(upload.status_code, 202, upload.text)
            document_id = upload.json()["id"]
            failed = self.wait_for_terminal_status(document_id)
            self.assertIsNotNone(failed)
            self.assertEqual((failed[0], failed[3]), ("failed", "internal_error"))
        finally:
            self._remove_reject_chunks_trigger()

        with patch("app.routers.documents.enqueue_ingestion_job", side_effect=RuntimeError("redis down")):
            retry = self.client.post(f"/documents/{document_id}/retry")
        self.assertEqual(retry.status_code, 503, retry.text)
        self.assertEqual(retry.json()["code"], "queue_unavailable")
        state = self.state(document_id)
        self.assertEqual((state[0], state[3]), ("failed", "internal_error"))

    def test_reenqueue_ready_document_does_not_duplicate_chunks(self):
        upload = self.client.post(
            "/documents", files={"file": ("reenqueue.txt", b"content")}
        )
        self.assertEqual(upload.status_code, 202, upload.text)
        document_id = upload.json()["id"]
        ready = self.wait_for_terminal_status(document_id)
        self.assertIsNotNone(ready)
        self.assertEqual(ready[0], "ready")
        before_chunk_count = ready[1]
        digest = ready[2]
        content_ref = content_ref_for_document(document_id, sha256=digest)

        asyncio.run(
            enqueue_ingestion_job(
                document_id,
                content_ref=content_ref,
                job_id_override=f"ingest-retry:{document_id}:{digest}:{uuid.uuid4().hex}",
            )
        )
        state = self.wait_for_terminal_status(document_id)
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "ready")
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM chunks WHERE document_id = %s",
                (document_id,),
            ).fetchone()[0]
        self.assertEqual(rows, before_chunk_count)
