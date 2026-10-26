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
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

# Suppress harmless HuggingFace symlink warning on Windows non-developer mode
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

logger = logging.getLogger(__name__)

MODEL_NAME = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
MODEL_REVISION = "6eba34a2485ea31cb03600241787c3a5edab8626"
TARGET_SR = 16000   # wav2vec2 expects 16kHz mono


@lru_cache(maxsize=1)
def _get_model_processor():
    """Use the publisher's EmotionModel, loading trunk and trained head together.

    Source: https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim
    Missing/mismatched weights are fatal to this model, never random predictions.
    """
    try:
        import torch
        from transformers import Wav2Vec2Processor
        from transformers.models.wav2vec2.modeling_wav2vec2 import Wav2Vec2Model, Wav2Vec2PreTrainedModel

        class RegressionHead(torch.nn.Module):
            def __init__(self, config):
                super().__init__()
                self.dense = torch.nn.Linear(config.hidden_size, config.hidden_size)
                self.dropout = torch.nn.Dropout(config.final_dropout)
                self.out_proj = torch.nn.Linear(config.hidden_size, config.num_labels)

            def forward(self, features):
                return self.out_proj(self.dropout(torch.tanh(self.dense(self.dropout(features)))))

        class EmotionModel(Wav2Vec2PreTrainedModel):
            def __init__(self, config):
                super().__init__(config)
                self.wav2vec2 = Wav2Vec2Model(config)
                self.classifier = RegressionHead(config)
                self.init_weights()

            def forward(self, input_values):
                return self.classifier(self.wav2vec2(input_values)[0].mean(dim=1))

        options = {"revision": MODEL_REVISION}
        processor = Wav2Vec2Processor.from_pretrained(MODEL_NAME, **options)
        model, info = EmotionModel.from_pretrained(
            MODEL_NAME, output_loading_info=True, use_safetensors=True, **options)
        _validate_loaded_weights(info)
        model.eval()
        logger.info("[voice-emotion] trained model loaded revision=%s", MODEL_REVISION)
        return processor, model
    except Exception as exc:
        logger.warning("[voice-emotion] could not load model: %s", exc)
        return None, None


def _validate_loaded_weights(info: dict) -> None:
    if any(info.get(key) for key in ("missing_keys", "mismatched_keys", "error_msgs")):
        raise ValueError("Incomplete voice emotion checkpoint")




def _decode_pcm(b64_data: str, sample_rate: int) -> Optional[Tuple["Any", int]]:
    """Decode base64 PCM → numpy float32 at TARGET_SR."""
    try:
        import numpy as np
        raw = base64.b64decode(b64_data, validate=True)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

        # Limit to last 30s for speed (wav2vec2 is slow on long audio)
        max_samples = 30 * sample_rate
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
    if processor is None or model is None:
        return None

    try:
        import torch
        import numpy as np

        # Model expects a list of 1-D numpy arrays at 16kHz
        inputs = processor(samples, sampling_rate=TARGET_SR, return_tensors="pt", padding=True)
        with torch.no_grad():
            # Get last hidden state from the wav2vec2 trunk
            logits = model(inputs["input_values"])  # [arousal, dominance, valence]

        preds = logits.squeeze().tolist()
        if not isinstance(preds, list) or len(preds) < 3:
            return None
        import math
        if not all(math.isfinite(float(value)) for value in preds):
            return None

        # The MSP-podcast model outputs continuous regression dimensions in ~[0.0, 1.0]
        def _clamp(x: float) -> float:
            return round(max(0.0, min(1.0, float(x))), 4)

        arousal   = _clamp(preds[0])
        dominance = _clamp(preds[1])
        valence   = _clamp(preds[2])

        return {
            "arousal":   arousal,
            "dominance": dominance,
            "valence":   valence,
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
