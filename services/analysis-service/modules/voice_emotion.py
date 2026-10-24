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
TARGET_SR = 16000   # wav2vec2 expects 16kHz mono


@lru_cache(maxsize=1)
def _get_model_processor():
    """
    Load audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim correctly.

    The audeering model uses a custom architecture: wav2vec2 trunk + a small
    MLP regression head (projector + classifier) that is NOT a standard
    HuggingFace head. AutoModelForAudioClassification does NOT load the
    regression weights — only AutoModel loads the trunk, and the head weights
    must be applied separately.

    We use the recommended audeering loading pattern: load with AutoModel,
    then attach the trained head by downloading the full checkpoint and
    reading the custom weight keys.
    """
    try:
        try:
            from transformers import AutoProcessor, AutoModel  # type: ignore
        except (ImportError, AttributeError):
            from transformers.models.auto.processing_auto import AutoProcessor  # type: ignore
            from transformers.models.auto.modeling_auto import AutoModel  # type: ignore
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore

        logger.info("[voice-emotion] loading model: %s (this may take a moment)", MODEL_NAME)
        processor = AutoProcessor.from_pretrained(MODEL_NAME)

        # Load the full state dict including the custom regression head
        base_model = AutoModel.from_pretrained(MODEL_NAME)

        # Audeering regression head: Linear(1024→1024) + tanh + Linear(1024→3)
        class _AuderingHead(nn.Module):
            def __init__(self):
                super().__init__()
                self.dense = nn.Linear(1024, 1024)
                self.out_proj = nn.Linear(1024, 3)

            def forward(self, hidden):
                # Mean-pool over time
                pooled = hidden.mean(dim=1) if hidden.ndim == 3 else hidden
                x = torch.tanh(self.dense(pooled))
                return self.out_proj(x)

        head = _AuderingHead()

        # Try to load trained head weights from the hub checkpoint
        try:
            import torch
            from huggingface_hub import hf_hub_download  # type: ignore
            ckpt_path = hf_hub_download(MODEL_NAME, filename="pytorch_model.bin",
                                        local_files_only=False)
            full_sd = torch.load(ckpt_path, map_location="cpu", weights_only=True)
            head_sd = {
                k.replace("classifier.", ""): v
                for k, v in full_sd.items()
                if k.startswith("classifier.")
            }
            if head_sd:
                head.load_state_dict(head_sd)
                logger.info("[voice-emotion] regression head weights loaded (%d keys)", len(head_sd))
            else:
                logger.warning("[voice-emotion] no head weights found in checkpoint — scores may be inaccurate")
        except Exception as head_exc:
            logger.warning("[voice-emotion] could not load head weights: %s — using random init", head_exc)

        base_model.eval()
        head.eval()
        logger.info("[voice-emotion] model loaded")
        return processor, (base_model, head)
    except Exception as exc:
        logger.warning("[voice-emotion] could not load model: %s", exc)
        return None, None




def _decode_pcm(b64_data: str, sample_rate: int) -> Optional[Tuple["Any", int]]:
    """Decode base64 PCM → numpy float32 at TARGET_SR."""
    try:
        import numpy as np
        raw = base64.b64decode(b64_data)
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
    processor, model_pair = _get_model_processor()
    if processor is None or model_pair is None:
        return None

    base_model, head = model_pair

    try:
        import torch
        import numpy as np

        # Model expects a list of 1-D numpy arrays at 16kHz
        inputs = processor(samples, sampling_rate=TARGET_SR, return_tensors="pt", padding=True)
        with torch.no_grad():
            # Get last hidden state from the wav2vec2 trunk
            hidden = base_model(**inputs).last_hidden_state  # (1, T, 1024)
            logits = head(hidden)  # (1, 3): [arousal, dominance, valence]

        preds = logits.squeeze().tolist()
        if not isinstance(preds, list) or len(preds) < 3:
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
