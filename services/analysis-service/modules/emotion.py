"""
Text emotion detection using j-hartmann/emotion-english-distilroberta-base.
Detects: anger, disgust, fear, joy, neutral, sadness, surprise.

Maps to interview-relevant signals:
  fear/sadness → low confidence, nervousness
  anger        → aggressive tone (bad for interviews)
  joy          → enthusiasm (good signal)
  neutral      → professional (expected)
  surprise     → can indicate uncertainty
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MODEL_NAME = "j-hartmann/emotion-english-distilroberta-base"

# Emotion → interview signal mapping
_CONFIDENCE_IMPACT: Dict[str, float] = {
    "joy": +0.05,
    "neutral": 0.00,
    "surprise": -0.02,
    "fear": -0.08,
    "sadness": -0.06,
    "anger": -0.05,
    "disgust": -0.04,
}


@lru_cache(maxsize=1)
def _get_pipeline():
    try:
        from transformers import pipeline  # type: ignore
        logger.info("[emotion] loading text emotion model: %s", MODEL_NAME)
        pipe = pipeline(
            "text-classification",
            model=MODEL_NAME,
            top_k=None,           # return all labels with scores
            device=-1,            # CPU
            truncation=True,
            max_length=512,
        )
        logger.info("[emotion] model loaded")
        return pipe
    except Exception as exc:
        logger.warning("[emotion] could not load model: %s", exc)
        return None


def analyze_emotion(text: str) -> Dict[str, Any]:
    """
    Run emotion detection on the transcript text.
    Returns per-emotion probabilities and a derived confidence adjustment.
    """
    pipe = _get_pipeline()

    if pipe is None:
        return _neutral_result("model_unavailable")

    try:
        # Truncate to 512 tokens worth of text (model max)
        chunk = text[:2000]
        results: List[Dict] = pipe(chunk)[0]  # list of {label, score}

        scores = {r["label"].lower(): round(r["score"], 4) for r in results}
        dominant = max(scores, key=lambda k: scores[k])

        # Aggregate confidence adjustment
        adjustment = sum(
            _CONFIDENCE_IMPACT.get(label, 0.0) * score
            for label, score in scores.items()
        )

        highlights: List[Dict[str, Any]] = []
        if scores.get("fear", 0) > 0.30:
            highlights.append({
                "type": "tone",
                "severity": "warn",
                "message": "Your word choices suggest nervousness. Try slowing down and using more assertive language.",
            })
        if scores.get("anger", 0) > 0.25:
            highlights.append({
                "type": "tone",
                "severity": "warn",
                "message": "Your tone came across as aggressive in places. Keep responses calm and solution-focused.",
            })
        if scores.get("joy", 0) > 0.40:
            highlights.append({
                "type": "tone",
                "severity": "info",
                "message": "Your enthusiasm came through clearly — a strong positive signal.",
            })

        return {
            "available": True,
            "dominant_emotion": dominant,
            "scores": scores,
            "confidence_adjustment": round(adjustment, 4),
            "highlights": highlights,
        }

    except Exception as exc:
        logger.warning("[emotion] inference failed: %s", exc)
        return _neutral_result(str(exc))


def _neutral_result(reason: str) -> Dict[str, Any]:
    return {
        "available": False,
        "dominant_emotion": "neutral",
        "scores": {},
        "confidence_adjustment": 0.0,
        "highlights": [],
        "reason": reason,
    }
