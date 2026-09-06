"""
LangGraph state schema for the analysis pipeline.
All nodes read from and write into this shared TypedDict.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class AnalysisState(TypedDict, total=False):
    # ── Inputs ─────────────────────────────────────────────────────────────────
    scenario: str
    context: Dict[str, Any]
    transcript: List[Dict[str, Any]]   # [{speaker, text, ts}, ...]
    user_text: str                      # concatenated user turns
    full_text: str                      # full labelled transcript
    audio_b64: Optional[str]
    audio_sample_rate: int
    video_frames_b64: Optional[List[str]]

    # ── Module outputs ─────────────────────────────────────────────────────────
    speech: Dict[str, Any]
    nlp: Dict[str, Any]
    alignment: Dict[str, Any]
    voice: Dict[str, Any]
    vision: Dict[str, Any]
    emotion: Dict[str, Any]            # text emotion

    # ── Aggregated ─────────────────────────────────────────────────────────────
    confidence: float
    insights: Dict[str, Any]           # strengths, weaknesses, suggestions, coaching_note
    jobs: List[Dict[str, Any]]

    # ── Metadata ───────────────────────────────────────────────────────────────
    errors: List[str]                  # non-fatal errors collected during the run
