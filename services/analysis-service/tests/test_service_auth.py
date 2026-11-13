import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from service_auth import require_gateway


class ServiceAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_request_does_not_allow_concurrent_inference(self):
        import asyncio
        import threading
        from routes import analyze as route
        entered, release = threading.Event(), threading.Event()
        def inference(**kwargs):
            entered.set()
            release.wait(5)
            return {}
        request = route.AnalyzeRequest(transcript=[{"speaker": "user", "text": "answer"}])
        with patch.object(route, "run_analysis", side_effect=inference):
            first = asyncio.create_task(route.analyze(request))
            try:
                for _ in range(100):
                    if entered.is_set(): break
                    await asyncio.sleep(.01)
                self.assertTrue(entered.is_set())
                first.cancel()
                with self.assertRaises(asyncio.CancelledError): await first
                with self.assertRaises(HTTPException) as error: await route.analyze(request)
                self.assertEqual(error.exception.status_code, 503)
            finally:
                release.set()
                if route._inference: await asyncio.shield(route._inference)

    async def test_body_limit_authenticates_before_consuming_bytes(self):
        from unittest.mock import AsyncMock
        from request_limits import AnalysisRequestLimits
        app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
        with patch.dict(os.environ, {"ANALYSIS_SERVICE_TOKEN": "x" * 40}):
            await AnalysisRequestLimits(app)({"type": "http", "path": "/analyze"}, receive, send)
        receive.assert_not_awaited()
        self.assertEqual(send.call_args_list[0].args[0]["status"], 401)

    async def test_missing_configuration_is_closed(self):
        with patch.dict(os.environ, {"ANALYSIS_SERVICE_TOKEN": ""}):
            with self.assertRaises(HTTPException) as caught:
                await require_gateway(None)
            self.assertEqual(caught.exception.status_code, 503)

    async def test_only_matching_gateway_secret_is_accepted(self):
        secret = "fixture-only-" * 4
        with patch.dict(os.environ, {"ANALYSIS_SERVICE_TOKEN": secret}):
            for supplied in (None, "Bearer bad", secret):
                with self.assertRaises(HTTPException) as caught:
                    await require_gateway(supplied)
                self.assertEqual(caught.exception.status_code, 401)
            await require_gateway(f"Bearer {secret}")

    async def test_http_endpoint_auth_runs_before_any_model_inference(self):
        import httpx
        from fastapi import FastAPI
        from routes.analyze import router
        app = FastAPI()
        app.include_router(router)
        secret = "fixture-only-" * 4
        with patch.dict(os.environ, {"ANALYSIS_SERVICE_TOKEN": secret}), \
             patch("routes.analyze.run_analysis", return_value={"confidence": .8, "voice": {"available": True}}) as inference:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                payload = {"transcript": [{"speaker": "user", "text": "my answer"}]}
                self.assertEqual((await client.post("/analyze", json=payload)).status_code, 401)
                inference.assert_not_called()
                response = await client.post("/analyze", json=payload, headers={"Authorization": f"Bearer {secret}"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["voice"], {"available": True})
                self.assertEqual(inference.call_count, 1)
