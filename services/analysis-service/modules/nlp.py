"""
Semantic NLP Module — replaces regex keyword matching with sentence-transformer embeddings.

How it works:
1. Embeds the full user answer and the question/context using a lightweight local model
   (all-MiniLM-L6-v2, ~22MB, runs on CPU in ~50ms).
2. Computes cosine similarity between the answer and the question to get a "relevance" score
   that reflects *meaning*, not keyword overlap.
3. Uses the same embeddings to check structural patterns by comparing to scenario-specific
   "gold standard" template phrases.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

# ── Scenario-specific "gold standard" templates ────────────────────────────────
# These represent what a high-scoring answer LOOKS like for each scenario.
# Semantic similarity to these templates drives the structure score.
SCENARIO_TEMPLATES: Dict[str, List[str]] = {
    "INTERVIEW": [
        "In my previous role, I was faced with a situation where I had to solve a difficult problem. "
        "My task was to improve the outcome. I took specific actions including coordinating with my team "
        "and measuring results. As a result, we achieved a measurable improvement.",
        "I managed a cross-functional project under tight constraints and delivered it on schedule. "
        "The impact was a 20% reduction in cost and improved team velocity.",
    ],
    "PITCH": [
        "The core problem we are solving is a significant pain point for our target market. "
        "Our solution uniquely addresses this because of our differentiated approach. "
        "We have evidence of traction, including early customers and metrics. "
        "We are asking for investment to scale our go-to-market strategy.",
        "The market size is large, our team has deep domain expertise, "
        "and we have a clear and defensible business model.",
    ],
    "MEETING": [
        "The current status of the project is on track. The key decision we need to make today is "
        "which approach to take. I recommend option A because it reduces risk. "
        "The action item will be owned by the engineering team with a deadline of next Friday.",
        "We have three blockers. For each one I have a proposed resolution and an owner assigned.",
    ],
}

# Weak language patterns that reduce clarity — kept as regex since this is deterministic
WEAK_LANGUAGE_RE = re.compile(
    r"\b(thing|stuff|basically|sort of|kind of|i guess|maybe|like|you know|whatever)\b",
    re.I,
)

VAGUE_OPENER_RE = re.compile(
    r"^(so|well|um|uh|yeah|okay|right)[,\s]",
    re.I,
)


@lru_cache(maxsize=1)
def _get_model():
    """Load model once and cache. LRU with maxsize=1 acts as a singleton."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        logger.info("[nlp] loading sentence-transformer model: %s", MODEL_NAME)
        model = SentenceTransformer(MODEL_NAME)
        logger.info("[nlp] model loaded successfully")
        return model
    except ImportError:
        logger.warning("[nlp] sentence-transformers not installed — falling back to regex NLP")
        return None
    except Exception as exc:
        logger.error("[nlp] failed to load model: %s", exc)
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two 1-D vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _semantic_relevance(model, user_text: str, context: Dict[str, Any]) -> float:
    """
    Embed the user's answer and a context document, return cosine similarity.
    Falls back to 0.75 (neutral) if embedding fails.
    """
    # Build a short context "document" from the structured context fields
    ctx_parts: List[str] = []
    for key in ["role", "company", "audience", "objective", "jobDescription", "topicNotes"]:
        val = context.get(key)
        if isinstance(val, str) and val.strip():
            ctx_parts.append(val.strip())
    for key in ["skills", "focusAreas", "candidateBackground"]:
        val = context.get(key)
        if isinstance(val, list):
            ctx_parts.extend(str(v) for v in val if isinstance(v, str))

    if not ctx_parts:
        return 0.75  # No context to compare against — neutral score

    context_doc = " ".join(ctx_parts)[:1200]  # Truncate for speed

    try:
        embeddings = model.encode([user_text[:1000], context_doc], normalize_embeddings=True)
        similarity = _cosine_similarity(embeddings[0], embeddings[1])
        # Map similarity to [0.5, 0.95] range — raw cosine can be very low even for good answers
        return round(min(0.95, max(0.50, 0.5 + similarity * 0.5)), 3)
    except Exception as exc:
        logger.warning("[nlp] semantic relevance failed: %s", exc)
        return 0.72


def _semantic_structure(model, user_text: str, scenario: str) -> float:
    """
    Compare the user's answer to gold-standard templates for the scenario.
    Returns similarity score in [0.55, 0.95].
    """
    templates = SCENARIO_TEMPLATES.get(scenario, SCENARIO_TEMPLATES["INTERVIEW"])

    try:
        all_texts = [user_text[:1000]] + templates
        embeddings = model.encode(all_texts, normalize_embeddings=True)
        user_emb = embeddings[0]
        # Score = max similarity to any template
        best = max(_cosine_similarity(user_emb, embeddings[i + 1]) for i in range(len(templates)))
        return round(min(0.95, max(0.55, 0.55 + best * 0.45)), 3)
    except Exception as exc:
        logger.warning("[nlp] semantic structure failed: %s", exc)
        return 0.70


def _regex_fallback_structure(text: str, scenario: str) -> float:
    """Original regex-based structure scoring used as fallback."""
    common_cues = [
        r"\b(first|second|third|finally)\b",
        r"\b(i would|my approach|i will|we should)\b",
        r"\b(result|impact|metric|improved|reduced|increased)\b",
    ]
    scenario_cues = {
        "INTERVIEW": [r"\b(situation|task|action|result|learned)\b"],
        "PITCH": [r"\b(problem|solution|market|proof|ask|next step)\b"],
        "MEETING": [r"\b(status|decision|owner|deadline|next step|blocker)\b"],
    }
    cues = common_cues + scenario_cues.get(scenario, [])
    hits = sum(1 for cue in cues if re.search(cue, text, re.I))
    if hits >= 3:
        return 0.9
    if hits >= 1:
        return 0.75
    return 0.6


def _regex_fallback_relevance(text: str, context: Dict[str, Any]) -> float:
    """Original regex-based relevance scoring used as fallback."""
    ctx_terms: List[str] = []
    for key in ["role", "company", "audience", "objective"]:
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            ctx_terms.extend(re.findall(r"\b[\w']+\b", value.lower()))
    ctx_terms = [t for t in ctx_terms if len(t) >= 3]
    if not ctx_terms:
        return 0.75
    lower = text.lower()
    matches = sum(1 for term in set(ctx_terms) if term in lower)
    if matches >= 6:
        return 0.9
    if matches >= 3:
        return 0.82
    if matches >= 1:
        return 0.72
    return 0.6


def _structure_suggestion(scenario: str) -> str:
    if scenario == "PITCH":
        return "Use a pitch arc: problem → audience → solution → proof → ask."
    if scenario == "MEETING":
        return "Use a meeting arc: status → decision needed → options → owner → next step."
    return "Use STAR: Situation → Task → Action → Result. Keeps answers tight and memorable."


def _relevance_suggestion(scenario: str) -> str:
    if scenario == "PITCH":
        return "Map each claim to the audience's pain, priority, or expected outcome."
    if scenario == "MEETING":
        return "Tie every update directly to the meeting goal, decision, or stakeholder concern."
    return "Explicitly map your example to what the role needs: skills, decisions, and impact."


def analyze_language(text: str, context: Dict[str, Any], scenario: str = "INTERVIEW") -> Dict[str, Any]:
    scenario = (scenario or "INTERVIEW").upper()
    word_count = len(re.findall(r"\b[\w']+\b", text))

    # ── Clarity (deterministic — regex is correct here) ───────────────────────
    clarity = 0.85
    if word_count > 420:
        clarity = 0.68
    elif word_count > 280:
        clarity = 0.75

    weak_hits = len(WEAK_LANGUAGE_RE.findall(text))
    vague_opener = bool(VAGUE_OPENER_RE.search(text.strip()))
    clarity -= min(0.15, weak_hits * 0.02)
    if vague_opener:
        clarity -= 0.04
    clarity = round(max(0.45, min(clarity, 0.95)), 3)

    # ── Semantic scoring (structure + relevance) ───────────────────────────────
    model = _get_model()

    if model is not None:
        structure = _semantic_structure(model, text, scenario)
        relevance = _semantic_relevance(model, text, context)
        method = "semantic"
    else:
        structure = _regex_fallback_structure(text, scenario)
        relevance = _regex_fallback_relevance(text, context)
        method = "regex_fallback"

    logger.info("[nlp] scoring method=%s structure=%.3f relevance=%.3f clarity=%.3f",
                method, structure, relevance, clarity)

    score = round(0.40 * clarity + 0.35 * structure + 0.25 * relevance, 3)

    strengths: List[str] = []
    weaknesses: List[str] = []
    suggestions: List[str] = []

    if structure >= 0.80:
        strengths.append("Your response had a clear, well-structured narrative.")
    else:
        weaknesses.append("Your response lacked a clear structure or framework.")
        suggestions.append(_structure_suggestion(scenario))

    if relevance >= 0.80:
        strengths.append("Your answer was highly relevant to the session context.")
    else:
        weaknesses.append("Parts of your answer were not clearly tied to the specific context.")
        suggestions.append(_relevance_suggestion(scenario))

    if clarity >= 0.82:
        strengths.append("Your language was specific, clear, and professional.")
    else:
        weaknesses.append("Some language was vague or imprecise.")
        suggestions.append(
            f"Replace vague words ({weak_hits} found) with concrete metrics, owners, or outcomes."
        )

    return {
        "clarity": clarity,
        "structure": structure,
        "relevance": relevance,
        "score": score,
        "scoring_method": method,
        "strengths": strengths[:4],
        "weaknesses": weaknesses[:4],
        "suggestions": suggestions[:5],
    }
