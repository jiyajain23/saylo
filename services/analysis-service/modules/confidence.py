from typing import Any, Dict, Optional
import math


def compute_confidence(
    speech: Dict[str, Any],
    nlp: Dict[str, Any],
    alignment: Dict[str, Any],
    vision: Dict[str, Any],
    voice: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Compute an overall confidence score from five analysis dimensions.
    Includes safe fallbacks for NaN or invalid numeric values.
    """
    def safe_float(v: Any, fallback: float) -> float:
        try:
            val = float(v)
            if math.isnan(val) or math.isinf(val):
                return fallback
            return val
        except (TypeError, ValueError):
            return fallback

    speech_score = safe_float(speech.get("score", 0.0), 0.0)
    nlp_score = safe_float(nlp.get("score", 0.0), 0.0)
    alignment_score = safe_float(alignment.get("score", 0.0), 0.0)
    vision_score = safe_float(vision.get("score", 0.7), 0.7)

    voice_available = voice is not None and voice.get("available", False)

    if voice_available and voice:
        voice_score = safe_float(voice.get("confidence_score", 0.68), 0.68)
        score = (
            0.20 * speech_score
            + 0.30 * nlp_score
            + 0.20 * alignment_score
            + 0.15 * vision_score
            + 0.15 * voice_score
        )
    else:
        # Redistribute voice weight to speech and nlp
        score = (
            0.25 * speech_score
            + 0.35 * nlp_score
            + 0.20 * alignment_score
            + 0.20 * vision_score
        )

    if math.isnan(score) or math.isinf(score):
        score = 0.7

    return round(max(0.0, min(score, 1.0)), 3)
