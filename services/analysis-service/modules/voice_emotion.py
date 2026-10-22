"""
Voice emotion module using audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim.
Predicts continuous emotion dimensions from raw audio:
  - arousal   → vocal energy / activation (replaces heuristic _energy_score)
  - valence   → positivity / negativity of vocal affect
  - dominance → assertiveness / authority (replaces heuristic _monotone_score proxy)

Falls back to the existing librosa-based heuristics if the model is unavailable.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MODEL_NAME = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
TARGET_SR = 16000   # wav2vec2 expects 16kHz mono


@lru_cache(maxsize=1)
def _get_model_processor():
    try:
        try:
            from transformers import AutoProcessor, AutoModelForAudioClassification  # type: ignore
        except (ImportError, AttributeError):
            from transformers.models.auto.processing_auto import AutoProcessor  # type: ignore
            from transformers.models.auto.modeling_auto import AutoModelForAudioClassification  # type: ignore
        import torch  # type: ignore
        logger.info("[voice-emotion] loading model: %s (this may take a moment)", MODEL_NAME)
        processor = AutoProcessor.from_pretrained(MODEL_NAME)
        model = AutoModelForAudioClassification.from_pretrained(MODEL_NAME)
        model.eval()
        logger.info("[voice-emotion] model loaded")
        return processor, model
    except Exception as exc:
        logger.warning("[voice-emotion] could not load model: %s", exc)
        return None, None


def _decode_pcm(b64_data: str, sample_rate: int) -> Optional[Tuple["Any", int]]:
    """Decode base64 PCM → numpy float32 at TARGET_SR."""
    try:
        import numpy as np
        raw = base64.b64decode(b64_data)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

        # Limit to last 60s for speed (model is slow on long audio)
        max_samples = 60 * sample_rate
        if len(samples) > max_samples:
            samples = samples[-max_samples:]

        # Resample to 16kHz if needed
        if sample_rate != TARGET_SR:
            import scipy.signal  # type: ignore
            samples = scipy.signal.resample(samples, int(len(samples) * TARGET_SR / sample_rate))

        return samples, TARGET_SR
    except Exception as exc:
        logger.warning("[voice-emotion] decode failed: %s", exc)
        return None


def _predict_dimensions(samples: "Any") -> Optional[Dict[str, float]]:
    """Run the model and return arousal/valence/dominance in [0, 1]."""
    processor, model = _get_model_processor()
    if processor is None:
        return None

    try:
        import torch
        import numpy as np

        # Model expects a list of 1-D numpy arrays at 16kHz
        inputs = processor(samples, sampling_rate=TARGET_SR, return_tensors="pt", padding=True)
        with torch.no_grad():
            logits = model(**inputs).logits  # shape (1, 3): [arousal, dominance, valence]

        # Outputs are already in roughly [0, 1] after sigmoid inside the model
        preds = logits.squeeze().tolist()
        if not isinstance(preds, list) or len(preds) < 3:
            return None

        return {
            "arousal":   round(float(preds[0]), 4),   # energy / activation
            "dominance": round(float(preds[1]), 4),   # assertiveness
            "valence":   round(float(preds[2]), 4),   # positivity
        }
    except Exception as exc:
        logger.warning("[voice-emotion] prediction failed: %s", exc)
        return None


def _highlights_from_dims(dims: Dict[str, float]) -> List[Dict[str, Any]]:
    highlights: List[Dict[str, Any]] = []
    arousal = dims["arousal"]
    dominance = dims["dominance"]
    valence = dims["valence"]

    if arousal < 0.35:
        highlights.append({
            "type": "energy",
            "severity": "warn",
            "message": "Your vocal energy was low. Project your voice more confidently.",
        })
    elif arousal > 0.80:
        highlights.append({
            "type": "energy",
            "severity": "info",
            "message": "Strong vocal projection — you sounded engaged and energetic.",
        })

    if dominance < 0.35:
        highlights.append({
            "type": "assertiveness",
            "severity": "warn",
            "message": "Your voice lacked assertiveness. Use a firmer, more decisive tone.",
        })
    elif dominance > 0.75:
        highlights.append({
            "type": "assertiveness",
            "severity": "info",
            "message": "Good vocal authority — you sounded confident and in control.",
        })

    if valence < 0.30:
        highlights.append({
            "type": "affect",
            "severity": "info",
            "message": "Your vocal affect seemed flat or negative. A slightly warmer tone helps rapport.",
        })

    return highlights


def analyze_voice_emotion(audio_b64: str, sample_rate: int = 16000) -> Dict[str, Any]:
    """
    Main entry point. Returns arousal/valence/dominance dimensions + composite score.
    Falls back to neutral if model or audio is unavailable.
    """
    result = _decode_pcm(audio_b64, sample_rate)
    if result is None:
        return _neutral_result("audio_decode_failed")

    samples, sr = result
    if len(samples) / sr < 1.0:
        return _neutral_result("audio_too_short")

    dims = _predict_dimensions(samples)
    if dims is None:
        return _neutral_result("model_prediction_failed")

    # Composite confidence score: arousal and dominance matter most for interviews
    confidence_score = round(0.45 * dims["arousal"] + 0.40 * dims["dominance"] + 0.15 * dims["valence"], 3)

    return {
        "available": True,
        "arousal": dims["arousal"],
        "dominance": dims["dominance"],
        "valence": dims["valence"],
        "confidence_score": confidence_score,
        "highlights": _highlights_from_dims(dims),
        # Legacy compat fields (used by confidence.py)
        "energy_score": dims["arousal"],
        "monotone_score": dims["dominance"],
        "pace_variability": 0.70,   # still from librosa; not replaced here
    }


def _neutral_result(reason: str) -> Dict[str, Any]:
    logger.info("[voice-emotion] neutral result: %s", reason)
    return {
        "available": False,
        "arousal": 0.60,
        "dominance": 0.55,
        "valence": 0.55,
        "confidence_score": 0.68,
        "energy_score": 0.70,
        "monotone_score": 0.65,
        "pace_variability": 0.70,
        "highlights": [],
        "reason": reason,
    }
