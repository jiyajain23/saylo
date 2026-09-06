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

# ── Build graph ────────────────────────────────────────────────────────────────

def _build_graph():
    builder = StateGraph(AnalysisState)

    # Register all nodes
    builder.add_node("speech", speech_node)
    builder.add_node("nlp", nlp_node)
    builder.add_node("alignment", alignment_node)
    builder.add_node("voice", voice_node)
    builder.add_node("emotion", emotion_node)
    builder.add_node("vision", vision_node)
    builder.add_node("aggregator", aggregator_node)
    builder.add_node("insights", insights_node)
    builder.add_node("jobs", jobs_node)
    builder.add_node("template_store", template_store_node)

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
) -> AnalysisState:
    """
    Run the full analysis pipeline and return the final state.
    All parallel nodes execute concurrently via LangGraph's async runtime.
    """
    MAX_USER_CHARS = 8_000
    MAX_FULL_CHARS = 12_000

    user_text = "\n".join(t["text"] for t in transcript if t.get("speaker") == "user")
    full_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in transcript)

    if len(user_text) > MAX_USER_CHARS:
        logger.warning("[graph] user_text truncated %d → %d chars", len(user_text), MAX_USER_CHARS)
        user_text = user_text[:MAX_USER_CHARS]
    if len(full_text) > MAX_FULL_CHARS:
        logger.warning("[graph] full_text truncated %d → %d chars", len(full_text), MAX_FULL_CHARS)
        full_text = full_text[:MAX_FULL_CHARS]

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

    final_state: AnalysisState = _graph.invoke(initial_state)

    errors = final_state.get("errors", [])
    if errors:
        logger.warning("[graph] completed with %d non-fatal errors: %s", len(errors), errors)
    else:
        logger.info("[graph] completed successfully | confidence=%.3f", final_state.get("confidence", 0))

    return final_state
