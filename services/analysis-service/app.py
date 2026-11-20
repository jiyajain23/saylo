import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from analysis-service, backend, or root
_service_dir = Path(__file__).resolve().parent
_root_dir = _service_dir.parent.parent
for env_candidate in [
    _service_dir / ".env",
    _root_dir / "backend" / ".env",
    _root_dir / ".env",
]:
    if env_candidate.exists():
        load_dotenv(env_candidate, override=False)

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
from request_limits import AnalysisRequestLimits
app.add_middleware(AnalysisRequestLimits)

# Request timeout: abort analysis if it runs longer than this (seconds).
# Protects against model hangs on very large inputs.
ANALYSIS_TIMEOUT_S = int(os.environ.get("ANALYSIS_TIMEOUT_S", "90"))

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


@app.get("/health")
async def health():
    from modules.model_registry import artifact_status
    return {"ok": True, "models": artifact_status()}


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Analysis service started. Allowed origins: %s", _origins)
    # Pre-warm heavy CPU models in background so first real request is fast
    import asyncio
    loop = asyncio.get_event_loop()
    async def _warmup():
        try:
            await loop.run_in_executor(None, _load_nlp_models)
            logger.info("[startup] NLP model warmup complete")
        except Exception as exc:
            logger.warning("[startup] model warmup failed (non-fatal): %s", exc)
    asyncio.create_task(_warmup())


def _load_nlp_models() -> None:
    """Warm shared models sequentially so cold-start peak RSS is measurable."""
    from modules.model_registry import _log_rss
    _log_rss("[warmup] baseline RSS before model loading")
    try:
        from modules.model_registry import sentence_model
        sentence_model()
        logger.info("[warmup] sentence-transformer loaded")
    except Exception as exc:
        logger.warning("[warmup] sentence-transformer model load failed: %s", exc)
    try:
        from modules.nlp import _get_star_model
        star_tok, star_mod = _get_star_model()
        if star_mod is not None:
            logger.info("[warmup] STAR classifier loaded (skipping cross-encoder fallback)")
        else:
            from modules.model_registry import cross_encoder
            cross_encoder()
            logger.info("[warmup] cross-encoder loaded")
    except Exception as exc:
        logger.warning("[warmup] NLP model load failed: %s", exc)
    try:
        from modules.emotion import _get_pipeline as _get_emotion_pipeline
        _get_emotion_pipeline()
        logger.info("[warmup] text-emotion pipeline loaded")
    except Exception as exc:
        logger.warning("[warmup] text-emotion model load failed: %s", exc)
    if os.environ.get("ENABLE_VOICE_TRANSFORMER", "false").lower() == "true":
        try:
            from modules.voice_emotion import _get_model_processor
            _get_model_processor()
            logger.info("[warmup] voice-emotion model loaded")
        except Exception as exc:
            logger.warning("[warmup] voice-emotion model load failed: %s", exc)
    else:
        logger.info("[warmup] voice transformer disabled (using lightweight Librosa DSP for voice)")
    from modules.model_registry import _log_rss as _log_rss2
    _log_rss2("[warmup] peak RSS after all models loaded")
