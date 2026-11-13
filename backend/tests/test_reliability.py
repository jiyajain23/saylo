"""Phase 3 regressions use temporary databases/files and mocked storage/inference."""
import asyncio
import base64
import sys
import tempfile
import unittest
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from models.schemas import Base, User, Session, TranscriptSegment, AnalysisJob, AnalysisResult
from services.auth import Principal
from services.jobs import enqueue, claim_job, complete_job, fail_job
from utils.audio import AudioBufferStore

OWNER = "11111111-1111-4111-8111-111111111111"


class AudioTests(unittest.TestCase):
    def test_fifteen_minutes_has_bounded_python_memory_and_exact_pcm(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AudioBufferStore(Path(directory), max_bytes=28_800_000)
            chunk = base64.b64encode(bytes(32000)).decode()
            tracemalloc.start()
            try:
                for _ in range(900): store.append("long", chunk)
                _, peak = tracemalloc.get_traced_memory()
            finally: tracemalloc.stop()
            path = store.seal("long")
            self.assertEqual(path.stat().st_size, 28_800_000)
            self.assertLess(peak, 1024 * 1024)
            store.clear("long")

    def test_sealed_abandoned_recording_is_cleaned(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            store = AudioBufferStore(Path(directory))
            store.append("abandoned", "AAA=")
            path = store.seal("abandoned")
            os.utime(path, (0, 0))
            store.cleanup()
            self.assertFalse(path.exists())
            self.assertEqual(store.size("abandoned"), 0)

    def test_worker_restart_cleans_only_expired_owned_pcm(self):
        import os
        from worker import cleanup_worker_files
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "saylo-worker-fixture"
            folder.mkdir()
            path = folder / "audio.pcm"
            path.write_bytes(b"00")
            other = folder / "unrelated.txt"
            other.write_text("keep")
            os.utime(path, (0, 0))
            cleanup_worker_files(directory)
            self.assertFalse(path.exists())
            self.assertTrue(other.exists())

    def test_pcm_is_streamed_exactly_and_capped_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AudioBufferStore(Path(directory), max_bytes=8)
            store.append("session", base64.b64encode(b"1234").decode())
            store.append("session", base64.b64encode(b"5678").decode())
            with self.assertRaises(ValueError):
                store.append("session", base64.b64encode(b"90").decode())
            path = store.seal("session")
            self.assertEqual(path.read_bytes(), b"12345678")
            self.assertEqual(store.size("session"), 8)
            store.clear("session")
            self.assertFalse(path.exists())

    def test_invalid_base64_and_odd_pcm_never_create_a_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AudioBufferStore(Path(directory))
            for data in ("invalid!", "AQ=="):
                with self.assertRaises(ValueError): store.append("session", data)
            self.assertIsNone(store.seal("session"))


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine("sqlite+aiosqlite:///" + (Path(self.temp.name) / "test.db").as_posix())
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
        async with self.factory() as db:
            db.add(User(id=OWNER))
            await db.flush()
            db.add(Session(id="fixture", userId=OWNER))
            await db.flush()
            db.add(TranscriptSegment(id="words", sessionId="fixture", speaker="user", text="real answer"))
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp.cleanup()

    async def enqueue(self):
        async with self.factory() as db: return await enqueue(db, "fixture", OWNER, None, 0)

    async def test_concurrent_end_creates_one_durable_job(self):
        await asyncio.gather(self.enqueue(), self.enqueue(), self.enqueue())
        async with self.factory() as db:
            self.assertEqual(len((await db.scalars(select(AnalysisJob))).all()), 1)
            self.assertEqual((await db.get(Session, "fixture")).status, "ANALYZING")

    async def test_new_worker_can_claim_after_gateway_restart(self):
        await self.enqueue()
        async with self.factory() as db:
            claim = await claim_job(db)
        self.assertEqual(claim.sessionId, "fixture")
        self.assertEqual(claim.attempts, 1)

    async def test_expired_lease_reclaims_and_old_worker_cannot_overwrite(self):
        await self.enqueue()
        async with self.factory() as db: first = await claim_job(db)
        async with self.factory() as db:
            job = await db.get(AnalysisJob, first.id)
            job.leaseExpiresAt = datetime.utcnow() - timedelta(seconds=1)
            await db.commit()
        async with self.factory() as db: second = await claim_job(db)
        self.assertNotEqual(first.leaseToken, second.leaseToken)
        async with self.factory() as db:
            self.assertFalse(await complete_job(db, first.id, first.leaseToken, {"confidence": .1}))
        async with self.factory() as db:
            self.assertTrue(await complete_job(db, second.id, second.leaseToken, {"confidence": .9, "voice": {"available": True}, "jobs": ["fixture"]}))
        async with self.factory() as db:
            result = await db.scalar(select(AnalysisResult))
            self.assertEqual(result.confidence, .9)
            self.assertEqual(result.voice, {"available": True})
            self.assertEqual(result.jobs, ["fixture"])

    async def test_terminal_failure_is_persisted_without_success_scores(self):
        await self.enqueue()
        async with self.factory() as db: claim = await claim_job(db)
        async with self.factory() as db:
            await fail_job(db, claim.id, claim.leaseToken, "audio_missing", retryable=False)
        async with self.factory() as db:
            self.assertEqual((await db.get(Session, "fixture")).status, "FAILED")
            self.assertEqual((await db.get(AnalysisJob, claim.id)).errorCode, "audio_missing")
            self.assertIsNone(await db.scalar(select(AnalysisResult)))

    async def test_one_live_session_and_daily_quota(self):
        from fastapi import HTTPException
        from services.limits import check_new_session
        async with self.factory() as db:
            with self.assertRaises(HTTPException) as error: await check_new_session(db, OWNER)
            self.assertEqual(error.exception.detail, "live_session_limit")
            await db.rollback()
        async with self.factory() as db:
            (await db.get(Session, "fixture")).status = "ENDED"
            await db.commit()
        with patch("services.limits.DAILY_SESSIONS", 1):
            async with self.factory() as db:
                with self.assertRaises(HTTPException) as error: await check_new_session(db, OWNER)
                self.assertEqual(error.exception.detail, "daily_session_limit")

    async def test_stale_queued_job_is_released_for_a_new_session(self):
        from services.limits import check_new_session, STALE_QUEUED_SECONDS
        async with self.factory() as db:
            job = await enqueue(db, "fixture", OWNER, None, 0)
            job.updatedAt = datetime.utcnow() - timedelta(seconds=STALE_QUEUED_SECONDS + 1)
            await db.commit()
        async with self.factory() as db:
            await check_new_session(db, OWNER)
            saved_job = await db.get(AnalysisJob, job.id)
            saved_session = await db.get(Session, "fixture")
            self.assertEqual(saved_job.status, "FAILED")
            self.assertEqual(saved_job.errorCode, "worker_unavailable")
            self.assertEqual(saved_session.status, "FAILED")

    async def test_simultaneous_session_creation_cannot_bypass_quota(self):
        from fastapi import HTTPException
        from api.sessions import create_session
        from models.schemas import CreateSessionRequest
        async with self.factory() as db:
            (await db.get(Session, "fixture")).status = "ENDED"
            await db.commit()
        async def create():
            async with self.factory() as db:
                try: return await create_session(CreateSessionRequest(), db, Principal(OWNER, 4102444800))
                except HTTPException as exc: return exc.status_code
        results = await asyncio.gather(create(), create(), create())
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count(429), 2)

    async def test_three_pending_jobs_still_have_one_active_claim(self):
        await self.enqueue()
        async with self.factory() as db:
            for number in (2, 3):
                owner = f"{number}" * 8 + "-1111-4111-8111-111111111111"
                db.add(User(id=owner))
                await db.flush()
                db.add(Session(id=f"other{number}", userId=owner))
                await db.flush()
                db.add(TranscriptSegment(id=f"words{number}", sessionId=f"other{number}", speaker="user", text="answer"))
                await db.flush()
                await enqueue(db, f"other{number}", owner, None, 0)
        async def claim():
            async with self.factory() as db: return await claim_job(db)
        claims = await asyncio.gather(claim(), claim(), claim())
        self.assertEqual(sum(result is not None for result in claims), 1)

    async def test_recording_lost_on_gateway_restart_cannot_be_scored_as_text_only(self):
        from fastapi import HTTPException
        async with self.factory() as db:
            (await db.get(Session, "fixture")).audioBytes = 2
            await db.commit()
        with self.assertRaises(HTTPException) as error: await self.enqueue()
        self.assertEqual(error.exception.detail, "recorded_audio_unavailable")

    async def test_retry_backoff_and_global_single_claim(self):
        await self.enqueue()
        async with self.factory() as db: claim = await claim_job(db)
        async with self.factory() as db: self.assertIsNone(await claim_job(db))
        async with self.factory() as db:
            await fail_job(db, claim.id, claim.leaseToken, "analysis_unavailable")
        async with self.factory() as db:
            self.assertIsNone(await claim_job(db))
            self.assertEqual((await db.get(AnalysisJob, claim.id)).status, "QUEUED")

    async def test_uploaded_object_recovers_after_gateway_dies_before_commit(self):
        from worker import maintenance
        async with self.factory() as db:
            job = await enqueue(db, "fixture", OWNER, f"{OWNER}/fixture.pcm", 2)
        with patch("worker.AsyncSessionLocal", self.factory), patch("worker.AudioStorage") as storage:
            storage.return_value.exists = AsyncMock(return_value=True)
            await maintenance()
        async with self.factory() as db:
            self.assertEqual((await db.get(AnalysisJob, job.id)).status, "QUEUED")

    async def test_expired_upload_fails_and_audio_is_deleted(self):
        from worker import maintenance
        async with self.factory() as db:
            job = await enqueue(db, "fixture", OWNER, f"{OWNER}/fixture.pcm", 2)
            job.expiresAt = datetime.utcnow() - timedelta(seconds=1)
            await db.commit()
        with patch("worker.AsyncSessionLocal", self.factory), patch("worker.AudioStorage") as storage:
            storage.return_value.exists = AsyncMock(return_value=False)
            storage.return_value.delete = AsyncMock()
            await maintenance()
            storage.return_value.delete.assert_awaited_once()
        async with self.factory() as db:
            saved = await db.get(AnalysisJob, job.id)
            self.assertEqual(saved.status, "FAILED")
            self.assertIsNotNone(saved.audioDeletedAt)

    async def test_worker_preserves_audio_contract_and_persists_results(self):
        import httpx
        from worker import process
        real_client = httpx.AsyncClient
        async with self.factory() as db:
            job = await enqueue(db, "fixture", OWNER, f"{OWNER}/fixture.pcm", 2)
            job.status = "QUEUED"
            await db.commit()
        async with self.factory() as db: job = await claim_job(db)
        captured = []
        def respond(request):
            import json
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"insights": {}, "voice": {"available": True}, "confidence": .8})
        async def download(key, path, size): path.write_bytes(b"\x01\x02")
        with patch("worker.AsyncSessionLocal", self.factory), patch("worker.AudioStorage") as storage, \
             patch("worker.httpx.AsyncClient", side_effect=lambda *args, **kwargs: real_client(transport=httpx.MockTransport(respond))), \
             patch.dict("os.environ", {"ANALYSIS_SERVICE_TOKEN": "test" * 10}):
            storage.return_value.download = download
            await process(job)
        analysis_payload = next(item for item in captured if "audio_b64" in item)
        self.assertEqual(analysis_payload["audio_b64"], "AQI=")
        self.assertEqual(analysis_payload["transcript"][0]["text"], "real answer")
        async with self.factory() as db:
            self.assertEqual((await db.get(Session, "fixture")).status, "READY")


class BodyLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_supabase_missing_object_head_400_is_absent(self):
        import httpx
        from services.storage import AudioStorage
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(400)))
        with patch.dict("os.environ", {"SUPABASE_SECRET_KEY": "fixture"}), \
             patch("services.storage.httpx.AsyncClient", return_value=client):
            self.assertFalse(await AudioStorage().exists("fixture/audio.pcm", 2))

    async def test_chunked_body_is_capped_before_route(self):
        from services.body_limit import BodyLimitMiddleware
        called = AsyncMock()
        app = BodyLimitMiddleware(called, max_bytes=4)
        received = AsyncMock(side_effect=[{"type": "http.request", "body": b"123", "more_body": True},
                                          {"type": "http.request", "body": b"45", "more_body": False}])
        sent = AsyncMock()
        await app({"type": "http"}, received, sent)
        self.assertEqual(sent.call_args_list[0].args[0]["status"], 413)
        called.assert_not_awaited()
