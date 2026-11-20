"""
Analysis endpoint — delegates to the LangGraph pipeline.
"""

import logging
import asyncio
import time
from threading import Lock
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator

from graph.analysis_graph import run_analysis
from service_auth import require_gateway
from modules.model_registry import _log_rss

logger = logging.getLogger(__name__)
router = APIRouter()
_inference = None
_progress: dict[str, dict] = {}
_progress_lock = Lock()


class TranscriptTurn(BaseModel):
    speaker: Literal["user", "ai"]
    text: str
    ts: Optional[str] = None
    audioStartSeconds: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    audioEndSeconds: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)


class AnalyzeRequest(BaseModel):
    scenario: str = Field(default="INTERVIEW")
    context: Dict[str, Any] = Field(default_factory=dict)
    transcript: List[TranscriptTurn]
    audio_b64: Optional[str] = Field(default=None, max_length=38400000)
    audio_sample_rate: int = Field(default=16000)
    video_frames_b64: Optional[List[str]] = Field(default=None)
    job_id: Optional[str] = Field(default=None, max_length=80)
    session_id: Optional[str] = Field(default=None, max_length=80)

    @field_validator("transcript")
    @classmethod
    def transcript_not_empty(cls, v):
        if not v:
            raise ValueError("transcript must contain at least one turn")
        if sum(len(turn.text) for turn in v) > 120000:
            raise ValueError("transcript limit exceeded")
        return v

    @field_validator("scenario")
    @classmethod
    def normalize_scenario(cls, v: str) -> str:
        normalized = v.strip().upper()
        return normalized if normalized in {"INTERVIEW", "PITCH", "MEETING"} else "INTERVIEW"


@router.post("/analyze", dependencies=[Depends(require_gateway)])
async def analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    """
    Run the full LangGraph analysis pipeline asynchronously:
      speech + NLP (cross-encoder + MiniLM) + alignment (semantic) + voice emotion
      + text emotion + vision → aggregator → Gemini insight agent → job matching
    Pipeline is offloaded to a thread so the event loop stays responsive.
    """
    global _inference
    import functools

    transcript_dicts = [t.model_dump() for t in req.transcript]

    user_turns = [t for t in transcript_dicts if t["speaker"] == "user"]
    if not any(t["text"].strip() for t in user_turns):
        raise HTTPException(status_code=422, detail="No user turns found in transcript")

    loop = asyncio.get_event_loop()
    if _inference is not None and not _inference.done():
        raise HTTPException(503, "analysis_busy")
    # Note: _inference is assigned AFTER the busy-check above, which is correct
    # for single-worker deployments. The asyncio.shield() below ensures the CPU
    # thread keeps running even if the client cancels, so models are not
    # interrupted mid-inference.
    _log_rss("[analyze] request start")
    try:
        def progress(event):
            if not req.job_id:
                return
            with _progress_lock:
                current = _progress.setdefault(req.job_id, {"events": [], "updatedAt": time.time()})
                current["events"] = (current["events"] + [event])[-40:]
                current["updatedAt"] = time.time()
                current["sessionId"] = req.session_id

        _inference = loop.run_in_executor(
            None,
            functools.partial(
                run_analysis,
                scenario=req.scenario,
                context=req.context,
                transcript=transcript_dicts,
                audio_b64=req.audio_b64,
                audio_sample_rate=req.audio_sample_rate,
                video_frames_b64=req.video_frames_b64,
                progress_callback=progress,
            )
        )
        # Request cancellation must not release capacity while the CPU thread
        # still uses the models. Subsequent attempts receive a bounded retry.
        state = await asyncio.shield(_inference)
    except Exception as exc:
        logger.exception("[analyze] pipeline failed")
        raise HTTPException(status_code=500, detail="analysis_pipeline_failed") from exc

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
        "scoring_version": state.get("scoring_version", "2"),
    }


@router.get("/progress/{job_id}", dependencies=[Depends(require_gateway)])
async def progress(job_id: str) -> Dict[str, Any]:
    with _progress_lock:
        value = _progress.get(job_id)
        if value is None:
            return {"jobId": job_id, "events": []}
        return {"jobId": job_id, "sessionId": value.get("sessionId"),
                "events": list(value.get("events", [])), "updatedAt": value.get("updatedAt")}
