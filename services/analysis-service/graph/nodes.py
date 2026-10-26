"""
LangGraph node functions for the analysis pipeline.
Each node reads from AnalysisState, does its work, and returns a dict of updates.
All five analysis nodes run in parallel via LangGraph's Send/fan-out mechanism.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from graph.state import AnalysisState
from modules.speech import analyze_speech
from modules.nlp import analyze_language
from modules.alignment import analyze_alignment
from modules.confidence import compute_confidence
from modules.emotion import analyze_emotion
from modules.insights import generate_insights
from modules.job_match import generate_job_recommendations
from modules.template_store import maybe_add_template
from modules.transcript import answer_pairs, measured_duration

logger = logging.getLogger(__name__)


# ── Parallel analysis nodes ────────────────────────────────────────────────────

def speech_node(state: AnalysisState) -> Dict[str, Any]:
    """Analyse speech metrics from the user transcript text."""
    try:
        result = analyze_speech(state["user_text"], measured_duration(state.get("transcript", [])))
        logger.info("[node:speech] score=%.3f wpm=%s fillers=%d",
                    result.get("score", 0), result.get("wpm_estimate", 0), result.get("fillers", 0))
        return {"speech": result}
    except Exception as exc:
        logger.exception("[node:speech] failed: %s", exc)
        return {"speech": {"score": 0.70, "error": str(exc)},
                "errors": [f"speech: {exc}"]}


def nlp_node(state: AnalysisState) -> Dict[str, Any]:
    """Analyse language quality, structure, and relevance (STAR classifier → MiniLM → regex)."""
    try:
        pairs = answer_pairs(state.get("transcript", [])) or [(None, state["user_text"])]
        answers = [analyze_language(text, state.get("context", {}), state["scenario"], question=question)
                   for question, text in pairs]
        result = {key: round(sum(a.get(key, .70) for a in answers) / len(answers), 3)
                  for key in ("score", "clarity", "structure", "relevance")}
        for key in ("strengths", "weaknesses", "suggestions"):
            result[key] = list(dict.fromkeys(item for a in answers for item in a.get(key, [])))[:5]
        result["scoring_method"] = "+".join(dict.fromkeys(a.get("scoring_method", "unknown") for a in answers))
        result["aggregation"] = "equal_weight_per_user_answer"
        result["answer_count"] = len(answers)
        logger.info("[node:nlp] method=%s structure=%.3f relevance=%.3f clarity=%.3f",
                    result.get("scoring_method"), result.get("structure"), result.get("relevance"), result.get("clarity"))
        return {"nlp": result}
    except Exception as exc:
        logger.exception("[node:nlp] failed: %s", exc)
        return {"nlp": {"score": 0.70, "error": str(exc)},
                "errors": [f"nlp: {exc}"]}


def alignment_node(state: AnalysisState) -> Dict[str, Any]:
    """Detect scenario signals via semantic embedding (catches paraphrases)."""
    try:
        result = analyze_alignment(state["scenario"], state["user_text"], state.get("context", {}))
        logger.info("[node:alignment] method=%s matched=%s score=%.3f",
                    result.get("scoring_method"), result.get("matchedSignals"), result.get("score"))
        return {"alignment": result}
    except Exception as exc:
        logger.exception("[node:alignment] failed: %s", exc)
        return {"alignment": {"score": 0.65, "error": str(exc)},
                "errors": [f"alignment: {exc}"]}


def voice_node(state: AnalysisState) -> Dict[str, Any]:
    """
    Analyse voice quality.
    Tries audeering wav2vec2 emotion model first (arousal/dominance/valence),
    falls back to librosa heuristics.
    """
    audio_b64 = state.get("audio_b64")
    sr = state.get("audio_sample_rate", 16000)

    if not audio_b64:
        from modules.voice import _neutral_result as librosa_neutral
        return {"voice": librosa_neutral("no_audio")}

    # Try wav2vec2 emotion model first
    try:
        from modules.voice_emotion import analyze_voice_emotion
        result = analyze_voice_emotion(audio_b64, sr)
        if result.get("available"):
            logger.info("[node:voice] wav2vec2 arousal=%.3f dom=%.3f val=%.3f",
                        result["arousal"], result["dominance"], result["valence"])
            return {"voice": result}
    except Exception as exc:
        logger.warning("[node:voice] wav2vec2 failed, falling back to librosa: %s", exc)

    # Fallback: librosa heuristics
    try:
        from modules.voice import analyze_voice
        result = analyze_voice(audio_b64, sr)
        return {"voice": result}
    except Exception as exc:
        logger.exception("[node:voice] librosa failed: %s", exc)
        return {"voice": {"available": False, "confidence_score": 0.68, "error": str(exc)},
                "errors": [f"voice: {exc}"]}


def emotion_node(state: AnalysisState) -> Dict[str, Any]:
    """Detect emotional tone in the transcript text."""
    try:
        result = analyze_emotion(state["user_text"])
        logger.info("[node:emotion] dominant=%s available=%s",
                    result.get("dominant_emotion"), result.get("available"))
        return {"emotion": result}
    except Exception as exc:
        logger.exception("[node:emotion] failed: %s", exc)
        return {"emotion": {"available": False, "dominant_emotion": "neutral",
                            "confidence_adjustment": 0.0, "highlights": [], "error": str(exc)},
                "errors": [f"emotion: {exc}"]}


def vision_node(state: AnalysisState) -> Dict[str, Any]:
    """Body language via MediaPipe (eye contact, posture). Placeholder if no frames."""
    frames = state.get("video_frames_b64")
    if not frames:
        return {"vision": {"score": 0.70, "available": False, "reason": "no_frames"}}
    # MediaPipe vision module (future implementation)
    return {"vision": {"score": 0.70, "available": False, "reason": "vision_not_implemented"}}


# ── Aggregator node ────────────────────────────────────────────────────────────

def aggregator_node(state: AnalysisState) -> Dict[str, Any]:
    """Compute weighted confidence score from all analysis dimensions."""
    speech = state.get("speech", {})
    nlp = state.get("nlp", {})
    alignment = state.get("alignment", {})
    vision = state.get("vision", {"score": 0.70})
    voice = state.get("voice", {})
    emotion = state.get("emotion", {"confidence_adjustment": 0.0})

    confidence = compute_confidence(speech, nlp, alignment, vision, voice)

    # Apply text emotion adjustment (small, bounded)
    adj = emotion.get("confidence_adjustment", 0.0)
    confidence = round(max(0.0, min(1.0, confidence + adj * 0.5)), 3)

    logger.info("[node:aggregator] confidence=%.3f (emotion_adj=%.4f)", confidence, adj)
    return {"confidence": confidence}


# ── Insight agent node ─────────────────────────────────────────────────────────

def insights_node(state: AnalysisState) -> Dict[str, Any]:
    """Generate personalised coaching (Gemini Flash → rule-based fallback)."""
    result = generate_insights(
        scenario=state["scenario"],
        speech=state.get("speech", {}),
        nlp=state.get("nlp", {}),
        alignment=state.get("alignment", {}),
        voice=state.get("voice", {}),
        emotion=state.get("emotion", {}),
        confidence=state.get("confidence", 0.70),
        user_text=state["user_text"],
    )
    # Merge emotion highlights into speech highlights
    speech = state.get("speech", {})
    all_highlights = (
        speech.get("highlights", [])
        + state.get("voice", {}).get("highlights", [])
        + state.get("emotion", {}).get("highlights", [])
    )
    return {
        "insights": {
            "highlights": all_highlights,
            "strengths": result.get("strengths", []),
            "weaknesses": result.get("weaknesses", []),
            "suggestions": result.get("suggestions", []),
            "coaching_note": result.get("coaching_note", ""),
            "generated_by": result.get("generated_by", "unknown"),
        }
    }


# ── Job match node ─────────────────────────────────────────────────────────────

def jobs_node(state: AnalysisState) -> Dict[str, Any]:
    """Semantic job matching using MiniLM embeddings against job catalogue."""
    jobs = generate_job_recommendations(
        scenario=state["scenario"],
        context=state.get("context", {}),
        confidence=state.get("confidence", 0.70),
    )
    return {"jobs": jobs}


# ── Template store node ────────────────────────────────────────────────────────

def template_store_node(state: AnalysisState) -> Dict[str, Any]:
    """If this was a high-confidence session, persist transcript as a gold standard template."""
    # Reviewed templates remain available to NLP. Public-user speech must not
    # silently become shared training/scoring material.
    return {}   # no state update needed
