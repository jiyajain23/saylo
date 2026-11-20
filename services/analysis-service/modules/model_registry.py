"""Process-local model registry.

The analysis worker is intentionally one process on the free-tier deployment.
Keeping these caches here makes NLP, alignment, and job matching share the
same MiniLM object without changing any scoring formulas or fallback paths.

Thread-safety note: lru_cache does not guard against concurrent first-calls, so
we use a threading.Lock + double-checked sentinel instead. This prevents the
~240 MB RSS spike that occurs when LangGraph fan-out nodes all call
sentence_model() concurrently before any cache is populated.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
MINILM_NAME = "all-MiniLM-L6-v2"
CROSS_ENCODER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


# ── RSS helper ────────────────────────────────────────────────────────────────

def _log_rss(label: str) -> None:
    """Log current process RSS in MB. Works on Linux (resource) and Windows (psutil)."""
    try:
        import resource
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        logger.info("%s | RSS=%.0f MB", label, rss_mb)
    except Exception:
        try:
            import psutil, os as _os
            rss_mb = psutil.Process(_os.getpid()).memory_info().rss / 1024 / 1024
            logger.info("%s | RSS=%.0f MB", label, rss_mb)
        except Exception:
            logger.info("%s | RSS=unavailable", label)


# ── sentence_model ─────────────────────────────────────────────────────────────

_sentence_model_lock = threading.Lock()
_sentence_model_instance = None
_sentence_model_loaded = False


def sentence_model():
    """Return the shared SentenceTransformer instance (thread-safe, loads once)."""
    global _sentence_model_instance, _sentence_model_loaded
    if _sentence_model_loaded:
        return _sentence_model_instance
    with _sentence_model_lock:
        if _sentence_model_loaded:          # double-checked locking
            return _sentence_model_instance
        try:
            try:
                import transformers
                if not hasattr(transformers, "is_torch_npu_available"):
                    transformers.is_torch_npu_available = lambda: False
            except Exception:
                pass
            import sentence_transformers
            cls = getattr(sentence_transformers, "SentenceTransformer", None)
            if not callable(cls):
                from sentence_transformers.SentenceTransformer import SentenceTransformer as cls
            logger.info("[models] loading shared sentence model: %s", MINILM_NAME)
            _sentence_model_instance = cls(MINILM_NAME)
        except Exception as exc:
            logger.warning("[models] MiniLM unavailable: %s", exc)
            _sentence_model_instance = None
        _sentence_model_loaded = True
        _log_rss("[models] sentence_model loaded")
        return _sentence_model_instance


# ── cross_encoder ──────────────────────────────────────────────────────────────

_cross_encoder_lock = threading.Lock()
_cross_encoder_instance = None
_cross_encoder_loaded = False


def cross_encoder():
    """Return the shared CrossEncoder instance (thread-safe, loads once)."""
    global _cross_encoder_instance, _cross_encoder_loaded
    if _cross_encoder_loaded:
        return _cross_encoder_instance
    with _cross_encoder_lock:
        if _cross_encoder_loaded:           # double-checked locking
            return _cross_encoder_instance
        try:
            from sentence_transformers import CrossEncoder
            logger.info("[models] loading cross encoder: %s", CROSS_ENCODER_NAME)
            _cross_encoder_instance = CrossEncoder(CROSS_ENCODER_NAME, max_length=512)
        except Exception as exc:
            logger.warning("[models] cross encoder unavailable: %s", exc)
            _cross_encoder_instance = None
        _cross_encoder_loaded = True
        _log_rss("[models] cross_encoder loaded")
        return _cross_encoder_instance


# ── Utilities ──────────────────────────────────────────────────────────────────

def artifact_status() -> dict:
    """Report configured artifact presence without loading or downloading it."""
    custom = os.environ.get("STAR_MODEL_PATH")
    root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [Path(custom).resolve()] if custom else []
    candidates += [root / "model" / "star_answer", root / "models" / "star_answer"]
    star = next((p for p in candidates if p.is_dir()), None)
    required = ("config.json", "tokenizer_config.json")
    complete = bool(star and all((star / name).exists() for name in required)
                    and any((star / name).exists() for name in ("model.safetensors", "pytorch_model.bin")))
    return {"minilm_cached": _sentence_model_loaded,
            "cross_encoder_cached": _cross_encoder_loaded,
            "star_configured": bool(star or custom), "star_artifact_complete": complete or bool(custom)}


def clear_caches() -> None:
    """Reset all model instances so they will be reloaded on next access."""
    global _sentence_model_instance, _sentence_model_loaded
    global _cross_encoder_instance, _cross_encoder_loaded
    with _sentence_model_lock:
        _sentence_model_instance = None
        _sentence_model_loaded = False
    with _cross_encoder_lock:
        _cross_encoder_instance = None
        _cross_encoder_loaded = False
    try:
        from modules.nlp import clear_star_cache
        clear_star_cache()
    except Exception:
        pass
