"""Bound HTTP bodies, including requests without Content-Length."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=128 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect": return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                return await JSONResponse({"detail": "payload_too_large"}, status_code=413)(scope, receive, send)
            messages.append(message)
            if not message.get("more_body"): break
        async def bounded_receive():
            return messages.pop(0) if messages else await receive()
        await self.app(scope, bounded_receive, send)
