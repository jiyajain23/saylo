"""Process-local model registry.

The analysis worker is intentionally one process on the free-tier deployment.
Keeping these caches here makes NLP, alignment, and job matching share the
same MiniLM object without changing any scoring formulas or fallback paths.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
MINILM_NAME = "all-MiniLM-L6-v2"
CROSS_ENCODER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def sentence_model():
    try:
        import sentence_transformers
        cls = getattr(sentence_transformers, "SentenceTransformer", None)
        if not callable(cls):
            from sentence_transformers.SentenceTransformer import SentenceTransformer as cls
        logger.info("[models] loading shared sentence model: %s", MINILM_NAME)
        return cls(MINILM_NAME)
    except Exception as exc:
        logger.warning("[models] MiniLM unavailable: %s", exc)
        return None


@lru_cache(maxsize=1)
def cross_encoder():
    try:
        from sentence_transformers import CrossEncoder
        logger.info("[models] loading cross encoder: %s", CROSS_ENCODER_NAME)
        return CrossEncoder(CROSS_ENCODER_NAME, max_length=512)
    except Exception as exc:
        logger.warning("[models] cross encoder unavailable: %s", exc)
        return None


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
    return {"minilm_cached": sentence_model.cache_info().currsize > 0,
            "cross_encoder_cached": cross_encoder.cache_info().currsize > 0,
            "star_configured": bool(star), "star_artifact_complete": complete}


def clear_caches() -> None:
    sentence_model.cache_clear()
    cross_encoder.cache_clear()
