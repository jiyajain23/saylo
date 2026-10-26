import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from service_auth import require_gateway


class ServiceAuthTests(unittest.IsolatedAsyncioTestCase):
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
