import logging
import os

# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse

from routes.analyze import router as analyze_router

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("analysis-service")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SpeakEZ Analysis Service", version="0.1.0")

# Request timeout: abort analysis if it runs longer than this (seconds).
# Protects against model hangs on very large inputs.
ANALYSIS_TIMEOUT_S = int(os.environ.get("ANALYSIS_TIMEOUT_S", "150"))

# Restrict CORS to known origins. In production set ALLOWED_ORIGINS env var.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5000")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(analyze_router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Analysis service started. Allowed origins: %s", _origins)
