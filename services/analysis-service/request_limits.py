"""Authenticate before buffering media; cap JSON even without Content-Length."""
from fastapi import HTTPException
from starlette.responses import JSONResponse
from service_auth import require_gateway


class AnalysisRequestLimits:
    def __init__(self, app, max_bytes=45 * 1024 * 1024):
        self.app, self.max_bytes = app, max_bytes
        self.receiving = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "").rstrip("/") != "/analyze":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            await require_gateway(headers.get(b"authorization", b"").decode("latin-1"))
        except HTTPException as exc:
            return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)
        # The thread remains busy even when its original HTTP request disconnects.
        from routes.analyze import _inference
        if _inference is not None and not _inference.done():
            return await JSONResponse({"detail": "analysis_busy"}, status_code=503)(scope, receive, send)
        if self.receiving:
            return await JSONResponse({"detail": "analysis_busy"}, status_code=503)(scope, receive, send)
        self.receiving = True
        try:
            await self.bounded_request(scope, receive, send)
        finally:
            self.receiving = False

    async def bounded_request(self, scope, receive, send):
        parts, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect": return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                return await JSONResponse({"detail": "payload_too_large"}, status_code=413)(scope, receive, send)
            parts.append(message)
            if not message.get("more_body"): break
        async def replay():
            return parts.pop(0) if parts else await receive()
        await self.app(scope, replay, send)
