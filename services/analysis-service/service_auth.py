"""Only the FastAPI gateway may invoke the heavy analysis endpoint."""
import os
import secrets

from fastapi import Header, HTTPException


async def require_gateway(authorization: str | None = Header(default=None)):
    secret = os.environ.get("ANALYSIS_SERVICE_TOKEN", "")
    if len(secret) < 32:
        raise HTTPException(503, "service_authentication_not_configured")
    expected = f"Bearer {secret}".encode()
    if not authorization or not secrets.compare_digest(authorization.encode(), expected):
        raise HTTPException(401, "invalid_service_token")
