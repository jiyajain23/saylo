"""
Semantic NLP Module — uses the fine-tuned STAR DistilBERT classifier as the
primary structure/relevance scorer, with sentence-transformer similarity as
a secondary method and regex as a final fallback.

Model priority:
  1. Fine-tuned STAR classifier (models/star_answer/) — trained on real interview data
  2. Sentence-transformer semantic similarity against adaptive templates
  3. Regex pattern matching (legacy fallback)
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from modules.template_store import get_templates

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

# Path to fine-tuned STAR DistilBERT classifier
_STAR_MODEL_PATH = os.environ.get(
    "STAR_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "star_answer")
)

# Templates are loaded dynamically at runtime via get_templates(scenario)
# so each call picks up any new high-confidence answers from the adaptive store.


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
def _get_star_model():
    """Load the fine-tuned STAR DistilBERT classifier (3-output regression)."""
    import pathlib
    model_path = pathlib.Path(_STAR_MODEL_PATH).resolve()
    if not model_path.exists():
        logger.info("[nlp] STAR model not found at %s — skipping", model_path)
        return None, None
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
        import torch  # type: ignore
        logger.info("[nlp] loading STAR classifier from %s", model_path)
        tokenizer = AutoTokenizer.from_pretrained(str(model_path))
        model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
        model.eval()
        logger.info("[nlp] STAR classifier loaded — outputs: structure, relevance, overall")
        return tokenizer, model
    except Exception as exc:
        logger.warning("[nlp] STAR classifier load failed: %s", exc)
        return None, None


@lru_cache(maxsize=1)
def _get_model():
    """Load MiniLM semantic model (secondary/fallback scorer)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        logger.info("[nlp] loading sentence-transformer model: %s", MODEL_NAME)
        model = SentenceTransformer(MODEL_NAME)
        logger.info("[nlp] model loaded successfully")
        return model
    except ImportError:
        logger.warning("[nlp] sentence-transformers not installed — falling back to regex NLP")
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


def _star_classify(user_text: str, scenario: str) -> Optional[Tuple[float, float]]:
    """
    Run the fine-tuned STAR DistilBERT classifier.
    Returns (structure_score, relevance_score) both in [0, 1], or None if unavailable.
    Model was trained with 3 regression outputs: [structure_score, relevance_score, overall].
    """
    tokenizer, model = _get_star_model()
    if tokenizer is None:
        return None
    try:
        import torch
        # Encode question+answer as a pair; use scenario as pseudo-question context
        question_ctx = f"[{scenario}] Evaluate this answer for structure and relevance:"
        inputs = tokenizer(
            question_ctx, user_text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        with torch.no_grad():
            outputs = model(**inputs)
        logits = outputs.logits.squeeze().tolist()
        if isinstance(logits, float):
            logits = [logits, logits, logits]
        # Clamp to [0.1, 0.95]
        structure = round(max(0.10, min(0.95, float(logits[0]))), 3)
        relevance = round(max(0.10, min(0.95, float(logits[1]))), 3)
        return structure, relevance
    except Exception as exc:
        logger.warning("[nlp] STAR classifier inference failed: %s", exc)
        return None


def _semantic_structure(model, user_text: str, scenario: str) -> float:
    """
    Score structure by comparing user input to adaptive gold-standard templates.
    Templates are loaded at runtime from template_store (per-scenario).
    """
    templates = get_templates(scenario)  # adaptive, loaded at call time
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
    # Priority 1: Fine-tuned STAR classifier
    star_result = _star_classify(text[:1000], scenario)

    if star_result is not None:
        structure, relevance = star_result
        method = "star_classifier"
    else:
        # Priority 2: MiniLM sentence-transformer
        model = _get_model()
        if model is not None:
            structure = _semantic_structure(model, text, scenario)
            relevance = _semantic_relevance(model, text, context)
            method = "semantic"
        else:
            # Priority 3: Regex fallback
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
