"""
Semantic alignment module.
Replaces hard regex rules with sentence-transformer embedding similarity,
catching paraphrased signals (e.g. "we moved the needle" → impact) that
regex misses. Falls back to regex if the model is unavailable.
"""

from __future__ import annotations

import re
import logging
from functools import lru_cache
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Semantic signal descriptions ───────────────────────────────────────────────
# Each signal has a natural-language description that gets embedded.
# Similarity to this description replaces regex pattern matching.

SCENARIO_SIGNALS: Dict[str, Dict[str, str]] = {
    "INTERVIEW": {
        "impact":           "quantified outcome metric result improvement reduction increase delivered",
        "reasoning":        "decision rationale trade-off constraint because therefore chose approach",
        "specific_example": "specific project team customer user built led implemented real situation",
        "learning":         "learned takeaway retrospective improved next time would do differently",
    },
    "PITCH": {
        "problem":   "problem pain point need gap customer frustration opportunity unmet",
        "audience":  "customer user buyer target market audience stakeholder who benefits",
        "value":     "value benefit save grow increase reduce differentiated unique solution",
        "traction":  "pilot customer signed revenue traction proof metrics users growth",
        "cta":       "ask next step invest approve pilot buy sign up call to action",
    },
    "MEETING": {
        "decision":        "decision recommendation proposal option choose approve select",
        "action":          "action item owner next step follow-up deadline responsible by Friday",
        "collaboration":   "team stakeholder align consensus feedback blocker dependency",
        "concise_update":  "status update summary priority risk on-track behind schedule",
    },
}

SCENARIO_SIGNAL_NOTES: Dict[str, Dict[str, str]] = {
    "INTERVIEW": {
        "impact":           "Add a concrete impact line with a metric, outcome, or measurable change.",
        "reasoning":        "Make your reasoning explicit — state the trade-offs, constraints, or why you chose that path.",
        "specific_example": "Ground the answer in a real, specific example rather than a general claim.",
        "learning":         "Add a brief reflection on what you learned or would do differently.",
    },
    "PITCH": {
        "problem":  "Open with the customer's problem or pain before jumping to your solution.",
        "audience": "Name the target audience and explain why this matters specifically to them.",
        "value":    "Make the value proposition concrete — use numbers, comparisons, or a before/after.",
        "traction": "Include a proof point: a pilot, signed customer, metric, or letter of intent.",
        "cta":      "Close with a clear and specific ask or next step for the audience.",
    },
    "MEETING": {
        "decision":       "Clarify the decision or recommendation you need from this meeting.",
        "action":         "State clear action items with owners and deadlines.",
        "collaboration":  "Show how you are keeping the team or stakeholders aligned.",
        "concise_update": "Frame the update with status, priority, key risks, or blockers.",
    },
}

_SIM_THRESHOLD = 0.42   # cosine similarity ≥ this = signal present


@lru_cache(maxsize=1)
def _get_model():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        logger.info("[alignment] loading MiniLM model for semantic signal detection")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model
    except Exception as exc:
        logger.warning("[alignment] could not load model: %s", exc)
        return None


@lru_cache(maxsize=32)
def _embed_signal_descriptions(scenario: str):
    """Pre-compute and cache signal description embeddings per scenario."""
    model = _get_model()
    if model is None:
        return None, None
    signals = SCENARIO_SIGNALS.get(scenario, SCENARIO_SIGNALS["INTERVIEW"])
    names = list(signals.keys())
    descs = list(signals.values())
    embeddings = model.encode(descs, normalize_embeddings=True)
    return names, embeddings


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))   # embeddings are already normalized


def _semantic_detect(user_text: str, scenario: str) -> Tuple[List[str], List[str]]:
    """
    Use sentence-transformer embeddings to detect which signals are present/missing.
    Returns (matched_names, missing_names).
    """
    model = _get_model()
    if model is None:
        return [], list(SCENARIO_SIGNALS.get(scenario, SCENARIO_SIGNALS["INTERVIEW"]).keys())

    names, sig_embeddings = _embed_signal_descriptions(scenario)
    if names is None:
        return [], list(SCENARIO_SIGNALS.get(scenario, SCENARIO_SIGNALS["INTERVIEW"]).keys())

    # Encode the user text in overlapping chunks to handle long answers
    # (MiniLM max 256 tokens — chunk at ~500 chars with overlap)
    text = user_text[:3000]
    chunks = []
    step = 450
    for i in range(0, max(1, len(text)), step):
        chunk = text[i:i + 500]
        if chunk.strip():
            chunks.append(chunk)

    if not chunks:
        return [], names

    chunk_embeddings = model.encode(chunks, normalize_embeddings=True)
    # For each signal, take the max similarity across all chunks
    matched, missing = [], []
    for idx, name in enumerate(names):
        sig_emb = sig_embeddings[idx]
        max_sim = max(_cosine(chunk_emb, sig_emb) for chunk_emb in chunk_embeddings)
        if max_sim >= _SIM_THRESHOLD:
            matched.append(name)
        else:
            missing.append(name)

    return matched, missing


def _regex_detect(text: str, scenario: str) -> Tuple[List[str], List[str]]:
    """Legacy regex fallback."""
    _REGEX_RULES: Dict[str, Dict[str, str]] = {
        "INTERVIEW": {
            "impact":           r"\b(impact|result|metric|improv|reduc|increas|launched|shipped|saved)\b",
            "reasoning":        r"\b(because|so that|trade-?off|constraint|therefore|decided)\b",
            "specific_example": r"\b(project|team|customer|user|built|led|implemented)\b",
            "learning":         r"\b(learned|takeaway|retrospective|next time|would have)\b",
        },
        "PITCH": {
            "problem":  r"\b(problem|pain|need|gap|opportunity)\b",
            "audience": r"\b(customer|user|buyer|market|audience|stakeholder)\b",
            "value":    r"\b(value|benefit|save|grow|increase|reduce|different|unique)\b",
            "traction": r"\b(traction|pilot|signed|revenue|proof|metrics)\b",
            "cta":      r"\b(next step|ask|pilot|buy|invest|approve|try|sign up)\b",
        },
        "MEETING": {
            "decision":       r"\b(decision|recommend|proposal|option|approve|choose)\b",
            "action":         r"\b(action|owner|next step|follow up|deadline|by friday|by monday)\b",
            "collaboration":  r"\b(we|team|stakeholder|align|feedback|agree|blocker)\b",
            "concise_update": r"\b(status|update|summary|priority|risk)\b",
        },
    }
    rules = _REGEX_RULES.get(scenario, _REGEX_RULES["INTERVIEW"])
    lower = text.lower()
    matched = [name for name, pat in rules.items() if re.search(pat, lower)]
    missing = [name for name in rules if name not in matched]
    return matched, missing


def _context_match(text: str, context: Dict[str, Any]) -> bool:
    terms: List[str] = []
    for key in ["role", "company", "audience", "objective"]:
        value = context.get(key)
        if isinstance(value, str):
            terms.extend(re.findall(r"\b[\w']+\b", value.lower()))
    for key in ["skills", "focusAreas"]:
        value = context.get(key)
        if isinstance(value, list):
            terms.extend([str(item).lower() for item in value if isinstance(item, str)])
    terms = [term for term in terms if len(term) >= 4]
    return any(term in text for term in set(terms))


def analyze_alignment(scenario: str, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    scenario = (scenario or "INTERVIEW").upper()

    # Try semantic detection first, fall back to regex
    matched, missing = _semantic_detect(text, scenario)
    method = "semantic"
    if not matched and not missing:
        matched, missing = _regex_detect(text, scenario)
        method = "regex_fallback"

    total_signals = len(SCENARIO_SIGNALS.get(scenario, SCENARIO_SIGNALS["INTERVIEW"]))
    base_score = 0.55 + (0.35 * (len(matched) / max(1, total_signals)))
    context_bonus = 0.10 if _context_match(text.lower(), context) else 0.0
    score = round(min(1.0, base_score + context_bonus), 3)

    notes_map = SCENARIO_SIGNAL_NOTES.get(scenario, SCENARIO_SIGNAL_NOTES["INTERVIEW"])
    notes = [notes_map[name] for name in missing if name in notes_map]
    if context and context_bonus == 0:
        notes.append("Tie the response more directly to the provided context.")

    logger.info(
        "[alignment] method=%s scenario=%s matched=%s missing=%s score=%.3f",
        method, scenario, matched, missing, score,
    )

    return {
        "scenario": scenario,
        "score": score,
        "matchedSignals": matched,
        "missingSignals": missing,
        "notes": notes[:5],
        "scoring_method": method,
    }
