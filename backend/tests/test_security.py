"""Real signed JWTs and two-tenant HTTP/WebSocket boundary regressions."""
import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException, WebSocketDisconnect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api import sessions
from api.websocket import websocket_endpoint
from db import get_db
from models.schemas import Base, Session, User, TranscriptSegment, AnalysisResult
from services.auth import Principal, JWTVerifier, current_user

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"
ISSUER = "https://example.supabase.co/auth/v1"


class TokenTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid="first", alg="ES256", use="sig")
        self.fetches = 0

        def reply(request):
            self.fetches += 1
            return httpx.Response(200, json={"keys": [self.jwk]})

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
        self.verifier = JWTVerifier("https://example.supabase.co", client=self.client)

    async def asyncTearDown(self):
        await self.client.aclose()

    def token(self, **changes):
        claims = {"sub": ALICE, "iss": ISSUER, "aud": "authenticated", "role": "authenticated",
                  "iat": int(time.time()), "exp": int(time.time()) + 120}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="ES256", headers={"kid": "first"})

    async def test_valid_signature_and_cached_jwks(self):
        for _ in range(3):
            principal = await self.verifier.verify(self.token())
            self.assertEqual(principal.id, ALICE)
        self.assertEqual(self.fetches, 1)

    async def test_invalid_claims_fail_closed(self):
        for claims in ({"exp": 1}, {"iss": "https://attacker.test"}, {"aud": "other"},
                       {"sub": "not-a-uuid"}, {"role": "service_role"}, {"iat": int(time.time()) + 300}):
            with self.subTest(claims=claims), self.assertRaises(HTTPException) as error:
                await self.verifier.verify(self.token(**claims))
            self.assertEqual(error.exception.status_code, 401)

    async def test_forged_signature_and_symmetric_algorithm_rejected(self):
        forged = jwt.encode({"sub": ALICE, "exp": int(time.time()) + 100},
                            ec.generate_private_key(ec.SECP256R1()), algorithm="ES256", headers={"kid": "first"})
        symmetric = jwt.encode({"sub": ALICE}, "x" * 32, algorithm="HS256", headers={"kid": "first"})
        for token in (forged, symmetric, "broken", "x" * 17000):
            with self.assertRaises(HTTPException):
                await self.verifier.verify(token)

    async def test_unknown_keys_do_not_cause_unbounded_refresh(self):
        await self.verifier.verify(self.token())
        for n in range(5):
            bad = jwt.encode({"sub": ALICE}, self.key, algorithm="ES256", headers={"kid": str(n)})
            with self.assertRaises(HTTPException):
                await self.verifier.verify(bad)
        self.assertEqual(self.fetches, 1)

    async def test_http_bearer_dependency_validates_signature_before_identity(self):
        from fastapi import Depends
        app = FastAPI()

        @app.get("/identity")
        async def identity(user=Depends(current_user)):
            return {"id": user.id}

        with patch("services.auth.verifier", return_value=self.verifier):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/identity", headers={"Authorization": f"Bearer {self.token()}"})
                self.assertEqual(response.json(), {"id": ALICE})
                for token in ("malformed", self.token(exp=1), self.token(aud="other")):
                    response = await client.get("/identity", headers={"Authorization": f"Bearer {token}"})
                    self.assertEqual(response.status_code, 401)

    async def test_expired_key_cache_fails_closed_when_auth_is_unavailable(self):
        await self.verifier.verify(self.token())
        self.verifier.fetched_at = float("-inf")
        self.verifier.attempted_at = float("-inf")
        await self.client.aclose()
        self.verifier.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
        try:
            with self.assertRaises(HTTPException) as error:
                await self.verifier.verify(self.token())
            self.assertEqual(error.exception.status_code, 503)
        finally:
            await self.verifier.client.aclose()


class OwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine("sqlite+aiosqlite:///" + (Path(self.directory.name) / "security.db").as_posix())
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.factory() as db:
            db.add_all([User(id=ALICE), User(id=BOB)])
            await db.flush()
            db.add_all([Session(id="alice", userId=ALICE), Session(id="bob", userId=BOB), Session(id="legacy")])
            await db.flush()
            db.add(TranscriptSegment(id="secret", sessionId="bob", speaker="user", text="private answer"))
            db.add(AnalysisResult(id="result", sessionId="bob", confidence=.9))
            await db.commit()
        self.app = FastAPI()
        self.app.include_router(sessions.router)

        async def database():
            async with self.factory() as db:
                yield db

        self.app.dependency_overrides[get_db] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()
        self.directory.cleanup()

    def login(self, user=ALICE):
        self.app.dependency_overrides[current_user] = lambda: Principal(user, time.time() + 120)

    async def test_missing_bearer_protects_all_rest_operations(self):
        for method, url, data in [("GET", "/sessions/", None), ("GET", "/sessions/progress", None),
                                  ("GET", "/sessions/alice", None), ("POST", "/sessions/", {}),
                                  ("POST", "/sessions/alice/end", {}),
                                  ("POST", "/sessions/alice/segments", {"speaker": "user", "text": "answer"})]:
            response = await self.client.request(method, url, json=data)
            self.assertEqual(response.status_code, 401, (url, response.text))

    async def test_history_progress_and_detail_are_owner_scoped(self):
        self.login()
        listing = (await self.client.get("/sessions/")).json()
        self.assertEqual([s["id"] for s in listing["sessions"]], ["alice"])
        progress = (await self.client.get("/sessions/progress")).json()
        self.assertEqual(progress["totalSessions"], 1)
        self.assertIsNone(progress["avgConfidence"])
        for session_id in ("bob", "legacy", "missing"):
            self.assertEqual((await self.client.get(f"/sessions/{session_id}")).status_code, 404)
        self.assertEqual((await self.client.get("/sessions/alice")).status_code, 200)

    async def test_wrong_owner_cannot_write_end_or_drain_other_socket(self):
        self.login()
        with patch.object(sessions.completion, "drain", AsyncMock()) as drain, \
             patch.object(sessions, "_run_analysis_task", AsyncMock()) as analysis:
            for session_id in ("bob", "legacy"):
                self.assertEqual((await self.client.post(f"/sessions/{session_id}/segments", json={"speaker": "user", "text": "injected"})).status_code, 404)
                self.assertEqual((await self.client.post(f"/sessions/{session_id}/end", json={})).status_code, 404)
            drain.assert_not_awaited()
            analysis.assert_not_called()

    async def test_create_derives_owner_and_response_contract_is_preserved(self):
        self.login()
        response = await self.client.post("/sessions/", json={"scenario": "PITCH", "userId": BOB})
        self.assertEqual(response.status_code, 201)
        result = response.json()["session"]
        self.assertEqual(result["scenario"], "PITCH")
        self.assertEqual(result["status"], "LIVE")
        async with self.factory() as db:
            self.assertEqual((await db.get(Session, result["id"])).userId, ALICE)

    async def socket(self, messages, origin="http://localhost:3000", principal=None):
        sent, closed = [], []

        class Socket:
            headers = {"origin": origin} if origin else {}
            async def accept(self): pass
            async def close(self, code=1000): closed.append(code)
            async def send_text(self, raw): sent.append(json.loads(raw))
            async def receive_text(self):
                if messages: return json.dumps(messages.pop(0))
                raise WebSocketDisconnect()

        with patch("api.websocket.AsyncSessionLocal", self.factory), \
             patch("api.websocket.verify_access_token", AsyncMock(return_value=principal or Principal(ALICE, time.time() + 120))) as verify, \
             patch("api.websocket.create_gemini_live_session", AsyncMock()) as upstream:
            await websocket_endpoint(Socket())
        return sent, closed, verify, upstream

    async def test_socket_rejects_missing_origin_and_media_before_hello(self):
        for origin in (None, "https://attacker.test"):
            _, closed, verify, upstream = await self.socket([], origin=origin)
            self.assertIn(1008, closed)
            verify.assert_not_awaited()
            upstream.assert_not_awaited()
        _, closed, _, upstream = await self.socket([{"type": "audio_chunk", "sessionId": "alice", "data": "AAA="}])
        self.assertIn(1008, closed)
        upstream.assert_not_awaited()

    async def test_socket_rejects_missing_token_wrong_owner_and_rebinding(self):
        for hello in ({"type": "hello", "sessionId": "alice"},
                      {"type": "hello", "sessionId": "bob", "accessToken": "valid"}):
            _, closed, _, upstream = await self.socket([hello])
            self.assertIn(1008, closed)
            upstream.assert_not_awaited()
        _, closed, verify, upstream = await self.socket([
            {"type": "hello", "sessionId": "alice", "accessToken": "valid"},
            {"type": "hello", "sessionId": "bob", "accessToken": "valid"}])
        self.assertIn(1008, closed)
        self.assertEqual(verify.await_count, 1)
        upstream.assert_not_awaited()

    async def test_expired_socket_identity_rejects_media(self):
        _, closed, _, upstream = await self.socket([
            {"type": "hello", "sessionId": "alice", "accessToken": "expired"}],
            principal=Principal(ALICE, time.time() - 1))
        self.assertIn(1008, closed)
        upstream.assert_not_awaited()
