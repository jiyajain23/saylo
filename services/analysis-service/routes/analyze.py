import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from modules.speech import analyze_speech
from modules.nlp import analyze_language
from modules.alignment import analyze_alignment
from modules.confidence import compute_confidence
from modules.voice import analyze_voice
from modules.jobs import generate_job_recommendations

logger = logging.getLogger(__name__)

router = APIRouter()


class TranscriptTurn(BaseModel):
    speaker: Literal["user", "ai"]
    text: str
    ts: Optional[str] = None


class AnalyzeRequest(BaseModel):
    scenario: str = Field(default="INTERVIEW")
    context: Dict[str, Any] = Field(default_factory=dict)
    transcript: List[TranscriptTurn]
    # Optional: base64-encoded PCM audio (16kHz, 16-bit mono) for voice analysis
    audio_b64: Optional[str] = Field(default=None)
    audio_sample_rate: int = Field(default=16000)

    @field_validator("transcript")
    @classmethod
    def transcript_not_empty(cls, v: List[TranscriptTurn]) -> List[TranscriptTurn]:
        if not v:
            raise ValueError("transcript must contain at least one turn")
        return v

    @field_validator("scenario")
    @classmethod
    def normalize_scenario(cls, v: str) -> str:
        normalized = v.strip().upper()
        allowed = {"INTERVIEW", "PITCH", "MEETING"}
        return normalized if normalized in allowed else "INTERVIEW"


@router.post("/analyze")
def analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    """
    Run all analysis modules on the provided transcript and return a
    combined result with speech, NLP, alignment, and confidence scores.
    """
    # Build a plain text representation: only user turns are evaluated for
    # speech metrics; the full transcript is used for alignment/NLP context.
    user_text = "\n".join(t.text for t in req.transcript if t.speaker == "user")
    full_text = "\n".join(f"{t.speaker}: {t.text}" for t in req.transcript)

    # Cap text sizes to prevent memory/time overruns on very long sessions.
    # NLP encodes up to 1000 chars; alignment uses regex over the full text.
    # Keeping a generous cap avoids slow serialization and embedding on huge inputs.
    MAX_USER_CHARS = 8_000
    MAX_FULL_CHARS = 12_000
    if len(user_text) > MAX_USER_CHARS:
        logger.warning("[analyze] user_text truncated %d -> %d chars", len(user_text), MAX_USER_CHARS)
        user_text = user_text[:MAX_USER_CHARS]
    if len(full_text) > MAX_FULL_CHARS:
        logger.warning("[analyze] full_text truncated %d -> %d chars", len(full_text), MAX_FULL_CHARS)
        full_text = full_text[:MAX_FULL_CHARS]

    if not user_text.strip():
        raise HTTPException(status_code=422, detail="No user turns found in transcript")

    try:
        speech = analyze_speech(user_text)
    except Exception as exc:
        logger.exception("speech analysis failed")
        raise HTTPException(status_code=500, detail=f"speech analysis error: {exc}") from exc

    try:
        nlp = analyze_language(full_text, req.context, req.scenario)
    except Exception as exc:
        logger.exception("nlp analysis failed")
        raise HTTPException(status_code=500, detail=f"nlp analysis error: {exc}") from exc

    try:
        alignment = analyze_alignment(req.scenario, full_text, req.context)
    except Exception as exc:
        logger.exception("alignment analysis failed")
        raise HTTPException(status_code=500, detail=f"alignment analysis error: {exc}") from exc

    # Vision module placeholder
    vision: Dict[str, float] = {"score": 0.7}

    # Voice analysis — runs if audio was provided by client
    voice: Dict[str, Any] = {"available": False, "confidence_score": 0.68}
    try:
        if req.audio_b64:
            voice = analyze_voice(req.audio_b64, req.audio_sample_rate)
    except Exception as exc:
        logger.exception("voice analysis failed")
        voice = {"available": False, "confidence_score": 0.68, "reason": str(exc)}

    confidence = float(compute_confidence(speech, nlp, alignment, vision, voice))

    jobs = generate_job_recommendations(req.scenario, req.context, confidence)

    insights = {
        "highlights": speech.get("highlights", []) + voice.get("highlights", []),
        "strengths": nlp.get("strengths", []),
        "weaknesses": nlp.get("weaknesses", []),
        "suggestions": nlp.get("suggestions", []),
    }

    logger.info(
        "analysis complete | scenario=%s turns=%d confidence=%.3f voice_available=%s nlp_method=%s",
        req.scenario,
        len(req.transcript),
        confidence,
        voice.get("available", False),
        nlp.get("scoring_method", "unknown"),
    )

    return {
        "speech": speech,
        "nlp": nlp,
        "alignment": alignment,
        "voice": voice,
        "confidence": confidence,
        "insights": insights,
        "jobs": jobs,
    }
