"""
Analysis endpoint — delegates to the LangGraph pipeline.
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from graph.analysis_graph import run_analysis

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
    audio_b64: Optional[str] = Field(default=None)
    audio_sample_rate: int = Field(default=16000)
    video_frames_b64: Optional[List[str]] = Field(default=None)

    @field_validator("transcript")
    @classmethod
    def transcript_not_empty(cls, v):
        if not v:
            raise ValueError("transcript must contain at least one turn")
        return v

    @field_validator("scenario")
    @classmethod
    def normalize_scenario(cls, v: str) -> str:
        normalized = v.strip().upper()
        return normalized if normalized in {"INTERVIEW", "PITCH", "MEETING"} else "INTERVIEW"


@router.post("/analyze")
def analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    """
    Run the full LangGraph analysis pipeline:
      speech + NLP (STAR classifier) + alignment (semantic) + voice emotion
      + text emotion + vision → aggregator → Gemini insight agent → job matching
    """
    transcript_dicts = [t.model_dump() for t in req.transcript]

    user_turns = [t for t in transcript_dicts if t["speaker"] == "user"]
    if not any(t["text"].strip() for t in user_turns):
        raise HTTPException(status_code=422, detail="No user turns found in transcript")

    try:
        state = run_analysis(
            scenario=req.scenario,
            context=req.context,
            transcript=transcript_dicts,
            audio_b64=req.audio_b64,
            audio_sample_rate=req.audio_sample_rate,
            video_frames_b64=req.video_frames_b64,
        )
    except Exception as exc:
        logger.exception("[analyze] pipeline failed")
        raise HTTPException(status_code=500, detail=f"analysis pipeline error: {exc}") from exc

    return {
        "speech":     state.get("speech", {}),
        "nlp":        state.get("nlp", {}),
        "alignment":  state.get("alignment", {}),
        "voice":      state.get("voice", {}),
        "emotion":    state.get("emotion", {}),
        "vision":     state.get("vision", {}),
        "confidence": state.get("confidence", 0.70),
        "insights":   state.get("insights", {}),
        "jobs":       state.get("jobs", []),
        "errors":     state.get("errors", []),
    }
