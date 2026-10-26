"""Gateway regressions run against isolated temporary SQLite databases."""
import asyncio
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from models.schemas import Base, Session, User, AnalysisResult, TranscriptSegment
from services.auth import Principal
from api import sessions
from services.gemini import GeminiLiveSession, _setup_message
from services import completion
from api.websocket import websocket_endpoint

TEST_USER = Principal("11111111-1111-4111-8111-111111111111", 4102444800)


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.factory() as db:
            db.add(User(id=TEST_USER.id))
            await db.flush()
            db.add(Session(id="fixture", userId=TEST_USER.id, updatedAt=datetime.utcnow()))
            db.add(TranscriptSegment(id="turn", sessionId="fixture", speaker="user", text="answer"))
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.directory.cleanup()

    async def test_concurrent_end_launches_once(self):
        async def finish():
            async with self.factory() as db:
                return await sessions.end_session("fixture", db, TEST_USER)
        task = AsyncMock()
        with patch.object(sessions, "_run_analysis_task", task), \
             patch.object(sessions.audio_buffer_store, "pop", return_value="audio") as pop:
            results = await asyncio.gather(finish(), finish(), finish())
            await asyncio.sleep(0)
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(task.call_count, 1)
        self.assertEqual(pop.call_count, 1)

    async def test_complete_analysis_survives_reload(self):
        payload = {"speech": {"score": .7}, "nlp": {"score": .8}, "alignment": {"score": .9},
                   "confidence": .8, "voice": {"available": True}, "emotion": {"available": True},
                   "vision": {"available": False}, "jobs": [{"role": "Engineer"}], "errors": ["fixture"],
                   "insights": {"strengths": ["clear"], "weaknesses": [], "suggestions": [],
                                "highlights": [], "coaching_note": "specific note", "generated_by": "fixture"},
                   "scoring_version": "2"}
        response = AsyncMock()
        response.status_code = 200
        response.json = lambda: payload
        client = AsyncMock()
        client.__aenter__.return_value.post.return_value = response
        with patch.dict("os.environ", {"ANALYSIS_SERVICE_TOKEN": "fixture-token-" * 4}), \
             patch("db.AsyncSessionLocal", self.factory), patch.object(sessions.httpx, "AsyncClient", return_value=client):
            await sessions._run_analysis_task("fixture", "INTERVIEW", {}, [], None, TEST_USER.id)
        async with self.factory() as db:
            detail = await sessions.get_session("fixture", db, TEST_USER)
        result = detail["session"]["analysis"]
        for key in ("voice", "emotion", "vision", "jobs", "errors", "insights", "scoring_version"):
            self.assertEqual(result[key], payload[key])
        self.assertEqual(result["speechMetrics"], payload["speech"])
        self.assertEqual(detail["session"]["status"], "READY")

    async def test_end_waits_for_active_socket_drain(self):
        entered = []
        async def drain():
            entered.append("drained")
            async with self.factory() as db:
                db.add(TranscriptSegment(id="late", sessionId="fixture", speaker="user", text="late persisted words"))
                await db.commit()
        completion.register("fixture", drain)
        try:
            with patch.object(sessions, "_run_analysis_task", AsyncMock()) as analysis:
                async with self.factory() as db:
                    await sessions.end_session("fixture", db, TEST_USER)
                await asyncio.sleep(0)
            self.assertEqual(entered, ["drained"])
            self.assertIn("late persisted words", [turn["text"] for turn in analysis.call_args.args[3]])
        finally:
            completion.unregister("fixture", drain)

    async def test_unconfirmed_turn_cannot_transition_to_analysis(self):
        from fastapi import HTTPException
        async def drain():
            raise TimeoutError()
        completion.register("fixture", drain)
        try:
            async with self.factory() as db:
                with self.assertRaises(HTTPException) as caught:
                    await sessions.end_session("fixture", db, TEST_USER)
                self.assertEqual(caught.exception.status_code, 409)
                self.assertEqual((await db.get(Session, "fixture")).status, "LIVE")
        finally:
            completion.unregister("fixture", drain)

    async def test_socket_persists_final_audio_before_ack_and_does_not_duplicate(self):
        from fastapi import WebSocketDisconnect
        received = [
            {"type": "hello", "sessionId": "fixture", "accessToken": "fixture-token"},
            {"type": "user_text", "sessionId": "fixture", "text": "start interview", "isControl": True},
            {"type": "audio_chunk", "sessionId": "fixture", "data": "AAA="},
            {"type": "audio_end", "sessionId": "fixture", "final": True, "requestId": "one"},
            {"type": "audio_end", "sessionId": "fixture", "final": True, "requestId": "two"}]
        sent = []
        class Socket:
            headers = {"origin": "http://localhost:3000"}
            async def accept(self):
                pass
            async def receive_text(self):
                if received:
                    return json.dumps(received.pop(0))
                raise WebSocketDisconnect()
            async def send_text(self, text):
                message = json.loads(text)
                if message.get("type") == "audio_ended":
                    async with self_factory() as db:
                        detail = await sessions.get_session("fixture", db, TEST_USER)
                    self_test.assertIn("um um last words", [s["text"] for s in detail["session"]["segments"]])
                sent.append(message)
        async def create(**callbacks):
            class Live:
                async def send_text(self, text):
                    callbacks["on_text"]("first question")
                    await callbacks["on_turn_complete"]()
                async def send_audio(self, *args):
                    callbacks["on_input_text"]("um um last words")
                    callbacks["on_input_timing"]({"start": 1., "end": 3.})
                async def finish_input(self):
                    await callbacks["on_turn_complete"]()
                async def close(self):
                    pass
            return Live()
        self_factory, self_test = self.factory, self
        with patch("api.websocket.AsyncSessionLocal", self.factory), \
             patch("api.websocket.verify_access_token", AsyncMock(return_value=TEST_USER)), \
             patch("api.websocket.create_gemini_live_session", side_effect=create), \
             patch("api.websocket.audio_buffer_store.append"):
            await websocket_endpoint(Socket())
        self.assertEqual(len([s for s in sent if s.get("type") == "audio_ended" and s.get("ok")]), 2)
        async with self.factory() as db:
            detail = await sessions.get_session("fixture", db, TEST_USER)
        segments = detail["session"]["segments"]
        self.assertEqual(len([s for s in segments if s["text"] == "um um last words"]), 1)
        self.assertNotIn("start interview", [s["text"] for s in segments])
        audio = next(s for s in segments if s["text"] == "um um last words")
        self.assertEqual((audio["audioStartSeconds"], audio["audioEndSeconds"]), (1., 3.))


class MigrationTests(unittest.TestCase):
    def test_legacy_sqlite_upgrade_is_additive_and_idempotent(self):
        from sqlalchemy import create_engine, text, inspect
        from migrations.phase1 import upgrade
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE "TranscriptSegment" (id TEXT PRIMARY KEY, text TEXT)'))
            conn.execute(text('CREATE TABLE "AnalysisResult" (id TEXT PRIMARY KEY, confidence FLOAT)'))
            conn.execute(text('INSERT INTO "AnalysisResult" VALUES (\'existing\', .8)'))
            upgrade(conn)
            upgrade(conn)
            self.assertEqual(conn.execute(text('SELECT confidence FROM "AnalysisResult"')).scalar(), .8)
            columns = {c["name"] for c in inspect(conn).get_columns("AnalysisResult")}
            self.assertIn("jobs", columns)
        engine.dispose()


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    def make_session(self, **callbacks):
        return GeminiLiveSession("INTERVIEW", None, lambda text: None, **callbacks)

    def test_setup_enables_both_transcriptions(self):
        setup = _setup_message("INTERVIEW", None, None, None)["setup"]
        self.assertIn("inputAudioTranscription", setup)
        self.assertIn("outputAudioTranscription", setup)

    async def test_audio_end_is_sent(self):
        session = self.make_session()
        session._ws = AsyncMock()
        session._setup_complete = True
        await session.end_audio()
        session._ws.send.assert_awaited_once_with(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))

    async def test_drain_waits_for_final_database_callback(self):
        from types import SimpleNamespace
        committed = asyncio.Event()
        async def complete():
            await asyncio.sleep(.01)
            committed.set()
        session = self.make_session(on_turn_complete=complete)
        session._ws = AsyncMock()
        session._setup_complete = True
        session._setup_ready.set()
        session._idle.clear()
        async def deliver():
            await asyncio.sleep(.01)
            await session._handle_response({"serverContent": {"inputTranscription": {"text": "last words"}}})
            await session._handle_response({"serverContent": {"turnComplete": True}})
        delivery = asyncio.create_task(deliver())
        await session.finish_input(timeout=1, quiet_seconds=.02)
        self.assertTrue(committed.is_set())
        await delivery

    async def test_drain_timeout_does_not_acknowledge_unfinished_turn(self):
        session = self.make_session()
        session._setup_complete = True
        session._setup_ready.set()
        session._ws = AsyncMock()
        session._idle.clear()
        with self.assertRaises(TimeoutError):
            await session.finish_input(timeout=.02, quiet_seconds=.01)

    async def test_late_input_transcription_is_flushed_before_ack(self):
        texts = []
        session = self.make_session(on_input_text=texts.append)
        session._setup_ready.set()
        session._setup_complete = True
        session._ws = AsyncMock()
        await session._handle_response({"serverContent": {"turnComplete": True}})
        await session._handle_response({"serverContent": {"inputTranscription": {"text": "late words"}}})
        await session.finish_input(timeout=1, quiet_seconds=.01)
        self.assertEqual(texts, ["late words"])

    async def test_drain_settles_after_final_transcript_without_terminal_event(self):
        """Gemini can finish ASR without a final turnComplete/waitingForInput."""
        texts = []
        committed = asyncio.Event()

        async def complete():
            committed.set()

        session = self.make_session(on_input_text=texts.append, on_turn_complete=complete)
        session._setup_ready.set()
        session._setup_complete = True
        session._ws = AsyncMock()
        session._idle.clear()

        async def deliver_transcript_only():
            await asyncio.sleep(.01)
            await session._handle_response({
                "serverContent": {"inputTranscription": {"text": "final answer"}}
            })

        delivery = asyncio.create_task(deliver_transcript_only())
        await session.finish_input(timeout=.25, quiet_seconds=.02, settle_seconds=.03)
        await delivery

        self.assertEqual(texts, ["final answer"])
        self.assertTrue(committed.is_set())

    async def test_old_turn_commit_does_not_mark_new_audio_idle(self):
        session = self.make_session()
        session._ws = AsyncMock()
        session._setup_complete = True
        async def commit():
            await session.send_audio("AAA=")
        session._on_turn_complete = commit
        await session._handle_response({"serverContent": {"turnComplete": True}})
        self.assertFalse(session._idle.is_set())

    def test_cleaning_preserves_repetition_for_filler_analysis(self):
        from api.websocket import _clean_transcript
        self.assertEqual(_clean_transcript("um um I I tried"), "um um I I tried")

    def test_live_pace_nudges_require_measured_user_duration(self):
        from api.websocket import _send_live_nudges_sync
        stats = {"start": 0, "words": 0}
        self.assertIsNone(_send_live_nudges_sync("short answer", stats))
        nudge = _send_live_nudges_sync("word " * 200, {"words": 0}, duration_seconds=60)
        self.assertIn("fast", nudge["message"])

    async def test_timing_offsets_are_optional_and_forwarded(self):
        timings = []
        session = self.make_session(on_input_timing=timings.append)
        await session._handle_response({"serverContent": {"inputTranscription": {
            "text": "words", "startOffset": "1.25s", "endOffset": "2.5s"}}})
        self.assertEqual(timings, [{"start": 1.25, "end": 2.5}])


if __name__ == "__main__":
    unittest.main()
