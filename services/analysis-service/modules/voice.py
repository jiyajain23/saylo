"""
Voice Quality Module — librosa-based audio energy, confidence, and monotone detection.

Takes raw base64-encoded PCM audio (16kHz, 16-bit mono) and extracts:
  - energy_score     : Overall vocal energy (low = timid, high = confident projection)
  - monotone_score   : Pitch variation (low = monotone, high = expressive)
  - confidence_score : Composite voice confidence index
  - pace_variability : Whether the user varied their speaking pace (pauses, emphasis)
  - highlights       : Actionable feedback items

Falls back gracefully if librosa/numpy are unavailable or audio is malformed.
"""

from __future__ import annotations

import base64
import io
import logging
import math
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _load_audio_from_pcm(b64_data: str, sample_rate: int = 16000) -> "tuple[Any, int] | None":
    """Decode base64 PCM bytes → numpy float32 array using librosa."""
    try:
        import numpy as np
        import librosa  # type: ignore

        raw = base64.b64decode(b64_data)
        # PCM 16-bit little-endian → float32
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        
        # Performance optimization: Limit to last 180 seconds (3 minutes)
        max_samples = 180 * sample_rate
        if len(samples) > max_samples:
            samples = samples[-max_samples:]
            
        # Downsample to 11025 Hz (sufficient for energy/expressiveness and much faster)
        if sample_rate != 11025:
            import scipy.signal # type: ignore
            samples = scipy.signal.resample(samples, int(len(samples) * 11025 / sample_rate))
        return samples, 11025
    except Exception as exc:
        logger.warning("[voice] audio decode failed: %s", exc)
        return None


def _energy_score(samples: "Any", sr: int) -> float:
    """
    RMS energy normalized to [0, 1].
    Very quiet speakers (RMS < 0.05) score < 0.5.
    Well-projected speakers (RMS 0.1–0.3) score 0.75–0.95.
    """
    try:
        import librosa
        import numpy as np

        rms = librosa.feature.rms(y=samples, frame_length=2048, hop_length=512)[0]
        mean_rms = float(np.mean(rms))
        # Map to [0, 1]: target range 0.08–0.25
        if mean_rms < 0.01:
            return 0.30
        score = min(1.0, mean_rms / 0.25)
        # Penalize clipping (over-projection)
        if mean_rms > 0.5:
            score = max(0.5, score - 0.15)
        return round(score, 3)
    except Exception as exc:
        logger.warning("[voice] energy scoring failed: %s", exc)
        return 0.65  # Neutral fallback


def _monotone_score(samples: "Any", sr: int) -> float:
    """
    Pitch (F0) standard deviation. Low std = monotone, high std = expressive.
    Returns a score in [0, 1] where higher = more expressive.
    """
    try:
        import librosa
        import numpy as np

        # Further downsample for pitch detection (8kHz is plenty for human voice F0)
        import scipy.signal
        samples_low = scipy.signal.resample(samples, int(len(samples) * 8000 / sr))
        
        # Use pyin for robust pitch estimation — increase hop_length for speed
        f0, voiced_flag, _ = librosa.pyin(
            samples_low,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=8000,
            frame_length=1024,
            hop_length=1024, # Fast processing
        )
        voiced_f0 = f0[voiced_flag] if voiced_flag is not None else np.array([])
        if len(voiced_f0) < 10:
            return 0.60  # Not enough voiced frames — can't reliably score

        std = float(np.std(voiced_f0))
        mean = float(np.mean(voiced_f0))
        # Coefficient of variation — normalizes for speaker pitch range
        cv = std / max(mean, 1.0)

        # Map CV to [0, 1]: target range 0.05–0.25
        if cv < 0.03:
            return 0.35  # Monotone
        if cv < 0.08:
            return 0.60  # Slightly varied
        if cv < 0.18:
            return 0.82  # Good expressiveness
        return 0.90  # Very expressive (diminishing returns above this)
    except Exception as exc:
        logger.warning("[voice] pitch analysis failed: %s", exc)
        return 0.60  # Neutral fallback


def _pace_variability(samples: "Any", sr: int) -> float:
    """
    Silence ratio and pause distribution.
    Healthy speakers pause intentionally (15–30% silence), monotone speakers don't.
    Returns a score in [0, 1].
    """
    try:
        import librosa
        import numpy as np

        # Split into voiced/silent intervals
        intervals = librosa.effects.split(samples, top_db=30)
        total_frames = len(samples)
        if total_frames == 0:
            return 0.65

        voiced_frames = sum(end - start for start, end in intervals)
        silence_ratio = 1.0 - (voiced_frames / total_frames)

        # Ideal: 15–35% silence (natural pauses)
        if 0.12 <= silence_ratio <= 0.38:
            return 0.88
        if silence_ratio < 0.05:
            return 0.55  # No pauses — rushed
        if silence_ratio > 0.55:
            return 0.50  # Too many/long pauses — hesitant
        return 0.72
    except Exception as exc:
        logger.warning("[voice] pace variability failed: %s", exc)
        return 0.70  # Neutral fallback


def analyze_voice(audio_b64: str, sample_rate: int = 16000) -> Dict[str, Any]:
    """
    Main entry point. Takes base64 PCM audio and returns voice quality metrics.
    If audio is unavailable or librosa is not installed, returns neutral placeholder scores.
    """
    result = _load_audio_from_pcm(audio_b64, sample_rate)
    if result is None:
        return _neutral_result("audio_decode_failed")

    samples, sr = result

    # Require at least 1 second of audio
    if len(samples) / sr < 1.0:
        return _neutral_result("audio_too_short")

    energy = _energy_score(samples, sr)
    monotone = _monotone_score(samples, sr)
    pace_var = _pace_variability(samples, sr)

    # Composite confidence score
    confidence_score = round(0.40 * energy + 0.40 * monotone + 0.20 * pace_var, 3)

    highlights: List[Dict[str, Any]] = []

    if energy < 0.50:
        highlights.append({
            "type": "energy",
            "severity": "warn",
            "message": "Your vocal energy was low. Project your voice more confidently."
        })
    elif energy > 0.90:
        highlights.append({
            "type": "energy",
            "severity": "info",
            "message": "Your vocal projection was strong."
        })

    if monotone < 0.50:
        highlights.append({
            "type": "monotone",
            "severity": "warn",
            "message": "Your pitch was quite flat. Vary your tone to emphasize key points."
        })
    elif monotone >= 0.80:
        highlights.append({
            "type": "expressiveness",
            "severity": "info",
            "message": "Good vocal expressiveness — your tone varied naturally."
        })

    if pace_var < 0.60:
        highlights.append({
            "type": "pace_rhythm",
            "severity": "info",
            "message": "Try adding deliberate pauses after key points for more impact."
        })

    logger.info(
        "[voice] energy=%.3f monotone=%.3f pace_var=%.3f confidence=%.3f",
        energy, monotone, pace_var, confidence_score
    )

    return {
        "energy_score": energy,
        "monotone_score": monotone,
        "pace_variability": pace_var,
        "confidence_score": confidence_score,
        "highlights": highlights,
        "available": True,
    }


def _neutral_result(reason: str) -> Dict[str, Any]:
    """Return a neutral, non-penalizing result when audio analysis is unavailable."""
    logger.info("[voice] returning neutral result: %s", reason)
    return {
        "energy_score": 0.70,
        "monotone_score": 0.65,
        "pace_variability": 0.70,
        "confidence_score": 0.68,
        "highlights": [],
        "available": False,
        "reason": reason,
    }
