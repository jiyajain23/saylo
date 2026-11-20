"""
LangGraph analysis graph definition.

Architecture:
  START
    └─> [fan-out] → speech_node
                  → nlp_node
                  → alignment_node
                  → voice_node
                  → emotion_node
                  → vision_node
        [fan-in: aggregator_node]
           └─> insights_node
                 └─> jobs_node
                       └─> template_store_node
                              └─> END

All fan-out nodes run in parallel via LangGraph's async execution.
"""

from __future__ import annotations

import logging
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, START, END  # type: ignore

from graph.state import AnalysisState
from graph.nodes import (
    speech_node,
    nlp_node,
    alignment_node,
    voice_node,
    emotion_node,
    vision_node,
    aggregator_node,
    insights_node,
    jobs_node,
    template_store_node,
)

logger = logging.getLogger(__name__)
_progress_sink = contextvars.ContextVar("analysis_progress_sink", default=None)


def _emit(stage: str, status: str, error: str | None = None) -> None:
    sink = _progress_sink.get()
    if sink is None:
        return
    event = {"stage": stage, "status": status,
             "timestamp": datetime.now(timezone.utc).isoformat()}
    if error:
        event["error"] = error
    try:
        sink(event)
    except Exception:
        logger.debug("[graph] progress sink failed", exc_info=True)


def _instrument(name, node):
    def wrapped(state):
        _emit(name, "running")
        try:
            result = node(state)
            _emit(name, "completed")
            return result
        except Exception as exc:
            _emit(name, "failed", type(exc).__name__)
            raise
    return wrapped

# ── Build graph ────────────────────────────────────────────────────────────────

def _build_graph():
    builder = StateGraph(AnalysisState)

    # Register all nodes
    nodes = {"speech": speech_node, "nlp": nlp_node, "alignment": alignment_node,
             "voice": voice_node, "emotion": emotion_node, "vision": vision_node,
             "aggregator": aggregator_node, "insights": insights_node,
             "jobs": jobs_node, "template_store": template_store_node}
    for name, node in nodes.items():
        builder.add_node(name, _instrument(name, node))

    # Fan-out: START → all parallel analysis nodes
    for node in ("speech", "nlp", "alignment", "voice", "emotion", "vision"):
        builder.add_edge(START, node)

    # Fan-in: all parallel nodes → aggregator
    for node in ("speech", "nlp", "alignment", "voice", "emotion", "vision"):
        builder.add_edge(node, "aggregator")

    # Sequential tail: aggregator → insights → jobs → template_store → END
    builder.add_edge("aggregator", "insights")
    builder.add_edge("insights", "jobs")
    builder.add_edge("jobs", "template_store")
    builder.add_edge("template_store", END)

    return builder.compile()


# Compile once at import time
_graph = _build_graph()


# ── Public API ─────────────────────────────────────────────────────────────────

def run_analysis(
    scenario: str,
    context: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    audio_b64: Optional[str] = None,
    audio_sample_rate: int = 16000,
    video_frames_b64: Optional[List[str]] = None,
    progress_callback=None,
) -> AnalysisState:
    """
    Run the full analysis pipeline and return the final state.
    All parallel nodes execute concurrently via LangGraph's async runtime.
    """
    user_text = "\n".join(t["text"] for t in transcript if t.get("speaker") == "user")
    full_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in transcript)

    initial_state: AnalysisState = {
        "scenario": (scenario or "INTERVIEW").upper(),
        "context": context or {},
        "transcript": transcript,
        "user_text": user_text,
        "full_text": full_text,
        "audio_b64": audio_b64,
        "audio_sample_rate": audio_sample_rate,
        "video_frames_b64": video_frames_b64,
        "errors": [],
        "scoring_version": "2",
        # Defaults (overwritten by nodes)
        "speech": {},
        "nlp": {},
        "alignment": {},
        "voice": {},
        "emotion": {},
        "vision": {"score": 0.70, "available": False},
        "confidence": 0.70,
        "insights": {},
        "jobs": [],
    }

    logger.info(
        "[graph] starting analysis | scenario=%s turns=%d has_audio=%s has_video=%s",
        initial_state["scenario"],
        len(transcript),
        bool(audio_b64),
        bool(video_frames_b64),
    )

    # Thread-safety note: the 6 fan-out nodes (speech, nlp, alignment, voice,
    # emotion, vision) run concurrently via LangGraph. All calls to
    # sentence_model(), cross_encoder(), _get_pipeline(), and
    # _get_model_processor() now use threading.Lock double-checked locking in
    # model_registry / emotion / voice_emotion, so concurrent first-calls will
    # block rather than each loading the full model — no duplicate loading.
    # By startup warmup time all models are already resident, so the lock is
    # uncontested on every real request.

    token = _progress_sink.set(progress_callback)
    _emit("analysis", "started")
    try:
        try:
            final_state: AnalysisState = _graph.invoke(initial_state)
        except Exception as exc:
            _emit("analysis", "failed", type(exc).__name__)
            raise
        _emit("analysis", "completed")
    finally:
        _progress_sink.reset(token)

    errors = final_state.get("errors", [])
    if errors:
        logger.warning("[graph] completed with %d non-fatal errors: %s", len(errors), errors)
    else:
        logger.info("[graph] completed successfully | confidence=%.3f", final_state.get("confidence", 0))

    return final_state
