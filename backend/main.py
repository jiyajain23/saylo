"""
FastAPI application entry point.
Port of server.ts + app.ts.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 5000 --reload

"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.sessions import router as sessions_router
from api.websocket import websocket_endpoint
from utils.logger import logger
from services.origins import allowed_origins

# ── Rate limiter ───────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["300/15minutes"])

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SpeakEZ API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ───────────────────────────────────────────────────────────────────────

_allowed_origins = allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────

app.include_router(sessions_router)


@app.get("/health")
async def health():
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    logger.info("[api] incoming WebSocket client connected on /ws")
    await websocket_endpoint(ws)


# ── Global error handler ───────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("[app] unhandled error", {"errorType": type(exc).__name__})
    return JSONResponse(status_code=500, content={"error": "internal_server_error"})


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    from db import init_db
    await init_db()
    port = os.environ.get("PORT", "5000")
    logger.info(f"[api] SpeakEZ Python backend starting on :{port}")
    logger.info("[api] Allowed CORS origins", _allowed_origins)
