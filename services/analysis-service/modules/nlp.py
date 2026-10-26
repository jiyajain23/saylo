"""
Semantic NLP Module — layered scoring pipeline.

Model priority:
  1. Fine-tuned STAR classifier (model/star_answer/) — trained on real interview data
  2. Cross-Encoder relevance scoring (cross-encoder/ms-marco-MiniLM-L-6-v2)
  3. Sentence-transformer semantic similarity (all-MiniLM-L6-v2) — structure + relevance
  4. Regex pattern matching — deterministic fallback
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import concurrent.futures

from modules.template_store import get_templates
from modules.transcript import text_windows

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

# Weak language patterns that reduce clarity — kept as regex since this is deterministic
WEAK_LANGUAGE_RE = re.compile(
    r"\b(thing|stuff|basically|sort of|kind of|i guess|maybe|like|you know|whatever)\b",
    re.I,
)

VAGUE_OPENER_RE = re.compile(
    r"^(so|well|um|uh|yeah|okay|right)[,\s]",
    re.I,
)

def _get_star_path() -> Optional[pathlib.Path]:
    import pathlib
    custom = os.environ.get("STAR_MODEL_PATH")
    if custom:
        p = pathlib.Path(custom).resolve()
        if p.exists():
            return p
    root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
    for candidate in [root / "model" / "star_answer", root / "models" / "star_answer"]:
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def _get_star_model():
    """Load the fine-tuned STAR DistilBERT classifier (3-output regression)."""
    model_path = _get_star_path()
    if not model_path:
        logger.info("[nlp] STAR model directory (model/star_answer) not found — skipping")
        return None, None
    try:
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
        except (ImportError, AttributeError):
            from transformers.models.auto.tokenization_auto import AutoTokenizer  # type: ignore
            from transformers.models.auto.modeling_auto import AutoModelForSequenceClassification  # type: ignore
        import torch  # type: ignore
        logger.info("[nlp] loading STAR classifier from %s", model_path)
        tokenizer = AutoTokenizer.from_pretrained(str(model_path))
        model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
        model.eval()
        logger.info("[nlp] STAR classifier loaded successfully — outputs: structure, relevance, overall")
        return tokenizer, model
    except Exception as exc:
        logger.warning("[nlp] STAR classifier load failed: %s", exc)
        return None, None


CROSS_ENCODER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _get_cross_encoder():
    """Load the Cross-Encoder relevance model (Priority 2 scorer)."""
    try:
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except (ImportError, AttributeError):
            from sentence_transformers.cross_encoder import CrossEncoder  # type: ignore
        logger.info("[nlp] loading cross-encoder: %s", CROSS_ENCODER_NAME)
        model = CrossEncoder(CROSS_ENCODER_NAME, max_length=512)
        logger.info("[nlp] cross-encoder loaded successfully")
        return model
    except Exception as exc:
        logger.warning("[nlp] cross-encoder unavailable: %s — will fall back to sentence-transformer", exc)
        return None


@lru_cache(maxsize=1)
def _get_model():
    """Load MiniLM semantic model (Priority 3 structure scorer)."""
    try:
        import sentence_transformers
        st_cls = getattr(sentence_transformers, "SentenceTransformer", None)
        if not callable(st_cls):
            from sentence_transformers.SentenceTransformer import SentenceTransformer as st_cls
        logger.info("[nlp] loading sentence-transformer model: %s", MODEL_NAME)
        model = st_cls(MODEL_NAME)
        logger.info("[nlp] model loaded successfully")
        return model
    except Exception as exc:
        logger.warning("[nlp] sentence-transformers unavailable: %s — falling back to regex NLP", exc)
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


def _star_classify(user_text: str, scenario: str, question: Optional[str] = None) -> Optional[Tuple[float, float]]:
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
        question_ctx = question or f"[{scenario}] Evaluate this answer for structure and relevance:"
        # Match the training notebook's single Question/Answer input format.
        inputs = tokenizer(
            f"Question: {question_ctx}\nAnswer: {user_text}",
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        # DistilBERT does not use token_type_ids
        inputs.pop("token_type_ids", None)
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


def _cross_encoder_relevance(user_text: str, context: Dict[str, Any]) -> Optional[float]:
    """
    Use a pre-trained Cross-Encoder (ms-marco-MiniLM-L-6-v2) to score how relevant
    the user's answer is to the session context.

    The cross-encoder jointly encodes [query | passage] and outputs a raw logit;
    we sigmoid it and map to [0.45, 0.95].
    Returns None if the model is unavailable.
    """
    model = _get_cross_encoder()
    if model is None:
        return None

    # Build a compact query from context fields
    ctx_parts: List[str] = []
    for key in ["role", "company", "objective", "audience", "jobDescription", "topicNotes"]:
        val = context.get(key)
        if isinstance(val, str) and val.strip():
            ctx_parts.append(val.strip())
    for key in ["skills", "focusAreas", "candidateBackground"]:
        val = context.get(key)
        if isinstance(val, list):
            ctx_parts.extend(str(v) for v in val if isinstance(v, str))

    if not ctx_parts:
        return None  # No context — skip; let downstream scorer handle it

    query = " | ".join(ctx_parts)[:800]
    passage = user_text[:800]

    try:
        import math
        raw_score: float = float(model.predict([(query, passage)])[0])
        # Sigmoid maps unbounded logit → (0, 1)
        sigmoid = 1.0 / (1.0 + math.exp(-raw_score))
        # Scale to [0.45, 0.95] — gives comfortable operating range
        relevance = round(min(0.95, max(0.45, 0.45 + sigmoid * 0.50)), 3)
        logger.info("[nlp] cross-encoder raw=%.3f sigmoid=%.3f relevance=%.3f", raw_score, sigmoid, relevance)
        return relevance
    except Exception as exc:
        logger.warning("[nlp] cross-encoder inference failed: %s", exc)
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


def _clarity(text: str) -> tuple[float, int]:
    word_count = len(re.findall(r"\b[\w']+\b", text))
    clarity = .68 if word_count > 420 else .75 if word_count > 280 else .85
    weak_hits = len(WEAK_LANGUAGE_RE.findall(text))
    clarity -= min(.15, weak_hits * .02)
    if VAGUE_OPENER_RE.search(text.strip()):
        clarity -= .04
    return round(max(.45, min(clarity, .95)), 3), weak_hits


def analyze_language(text: str, context: Dict[str, Any], scenario: str = "INTERVIEW", question: Optional[str] = None) -> Dict[str, Any]:
    scenario = (scenario or "INTERVIEW").upper()
    clarity, weak_hits = _clarity(text)
    windows = text_windows(text)
    if len(windows) > 1:
        results = [analyze_language(window, context, scenario, question) for window in windows]
        weights = [max(1, len(window.split())) for window in windows]
        total = sum(weights)
        structure, relevance = (round(sum(r[key] * weight for r, weight in zip(results, weights)) / total, 3)
                                for key in ("structure", "relevance"))
        method = "+".join(dict.fromkeys(r["scoring_method"] for r in results))
        return _language_result(clarity, structure, relevance, method, weak_hits, scenario)

    # ── Semantic scoring (structure + relevance) ───────────────────────────────
    # Each window fits the existing small-model budget; all windows are scored.
    model_text = text

    # Priority 1: Fine-tuned STAR classifier
    star_result = _star_classify(model_text, scenario, question)

    if star_result is not None:
        structure, relevance = star_result
        method = "star_classifier"
    else:
        # Priority 2 + 3: Run cross-encoder and sentence-transformer in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            ce_fut = pool.submit(_cross_encoder_relevance, model_text, context)
            st_fut = pool.submit(_get_model)  # cached after first call — near-instant

        ce_relevance = ce_fut.result()
        st_model = st_fut.result()

        if st_model is not None:
            structure = _semantic_structure(st_model, model_text, scenario)
            if ce_relevance is not None:
                relevance = ce_relevance  # cross-encoder wins for relevance
                method = "cross_encoder+semantic"
            else:
                relevance = _semantic_relevance(st_model, model_text, context)
                method = "semantic"
        else:
            if ce_relevance is not None:
                structure = _regex_fallback_structure(model_text, scenario)
                relevance = ce_relevance
                method = "cross_encoder+regex"
            else:
                # Priority 4: Regex fallback
                structure = _regex_fallback_structure(model_text, scenario)
                relevance = _regex_fallback_relevance(model_text, context)
                method = "regex_fallback"

    return _language_result(clarity, structure, relevance, method, weak_hits, scenario)


def _language_result(clarity, structure, relevance, method, weak_hits, scenario):
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
