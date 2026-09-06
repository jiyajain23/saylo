"""
LLM-powered insight agent using LangChain + Gemini Flash.
Replaces hardcoded `if score >= 0.80` feedback strings with dynamic,
personalised coaching generated from the actual scores and transcript.

Fallback chain:
  1. Gemini Flash (google-generativeai, if GEMINI_API_KEY set)
  2. Rule-based fallback (existing score-threshold logic)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Prompt template ────────────────────────────────────────────────────────────

_INSIGHT_PROMPT = """\
You are an expert communication coach analysing a {scenario} practice session.

## Session Scores
- Overall confidence: {confidence:.0%}
- Speech: WPM={wpm:.0f}, fillers={fillers}, score={speech_score:.0%}
- NLP: clarity={clarity:.0%}, structure={structure:.0%}, relevance={relevance:.0%}
- Alignment: matched signals={matched}, missing signals={missing}
- Voice: arousal={arousal:.0%}, dominance={dominance:.0%}, valence={valence:.0%}
- Emotional tone: dominant={dominant_emotion}

## Transcript Excerpt (last ~400 words of user speech)
{transcript_excerpt}

## Your Task
Write concise, specific, actionable feedback. Output ONLY valid JSON with exactly these keys:
{{
  "strengths": ["<strength 1>", "<strength 2>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>"],
  "suggestions": ["<suggestion 1>", "<suggestion 2>", "<suggestion 3>"],
  "coaching_note": "<2-3 sentence personalised paragraph addressing the candidate directly>"
}}

Rules:
- strengths/weaknesses: 2-3 items max, each under 12 words, SPECIFIC to their scores
- suggestions: 2-4 actionable items, each starting with a verb
- coaching_note: warm but honest, reference their actual performance
- Do NOT use generic phrases like "great job" or "needs improvement"
- Do NOT output anything outside the JSON
"""


def _build_prompt(
    scenario: str,
    speech: Dict[str, Any],
    nlp: Dict[str, Any],
    alignment: Dict[str, Any],
    voice: Dict[str, Any],
    emotion: Dict[str, Any],
    confidence: float,
    transcript_excerpt: str,
) -> str:
    return _INSIGHT_PROMPT.format(
        scenario=scenario,
        confidence=confidence,
        wpm=speech.get("wpm_estimate", 140),
        fillers=speech.get("fillers", 0),
        speech_score=speech.get("score", 0.7),
        clarity=nlp.get("clarity", 0.7),
        structure=nlp.get("structure", 0.7),
        relevance=nlp.get("relevance", 0.7),
        matched=", ".join(alignment.get("matchedSignals", [])) or "none",
        missing=", ".join(alignment.get("missingSignals", [])) or "none",
        arousal=voice.get("arousal", 0.6),
        dominance=voice.get("dominance", 0.55),
        valence=voice.get("valence", 0.55),
        dominant_emotion=emotion.get("dominant_emotion", "neutral"),
        transcript_excerpt=transcript_excerpt[:1600],
    )


def _call_gemini(prompt: str) -> Optional[str]:
    """Call Gemini Flash via google-generativeai SDK."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            model_name=os.environ.get("GEMINI_INSIGHT_MODEL", "gemini-2.0-flash"),
            generation_config={"temperature": 0.4, "max_output_tokens": 512},
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        logger.warning("[insights] Gemini call failed: %s", exc)
        return None


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM output (handles markdown code fences)."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON block inside the text
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    logger.warning("[insights] could not parse LLM JSON output")
    return None


def _rule_based_fallback(
    scenario: str,
    nlp: Dict[str, Any],
    alignment: Dict[str, Any],
    speech: Dict[str, Any],
    confidence: float,
) -> Dict[str, Any]:
    """Score-threshold fallback — used when no LLM is available."""
    strengths: List[str] = list(nlp.get("strengths", []))
    weaknesses: List[str] = list(nlp.get("weaknesses", []))
    suggestions: List[str] = list(nlp.get("suggestions", []))

    if speech.get("score", 0) >= 0.80:
        strengths.append("Clean, well-paced delivery with few filler words.")
    elif speech.get("fillers", 0) > 5:
        weaknesses.append("Frequent filler words reduced impact.")
        suggestions.append("Replace filler words with deliberate pauses.")

    if alignment.get("score", 0) >= 0.80:
        strengths.append("Your answer addressed the key signals for this scenario.")

    coaching_note = (
        f"You scored {confidence:.0%} overall. "
        + ("Focus on adding concrete examples and metrics to your answers. " if confidence < 0.70 else "")
        + "Keep practising to build consistency across scenarios."
    )

    return {
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "suggestions": suggestions[:4],
        "coaching_note": coaching_note,
        "generated_by": "rule_based_fallback",
    }


def generate_insights(
    scenario: str,
    speech: Dict[str, Any],
    nlp: Dict[str, Any],
    alignment: Dict[str, Any],
    voice: Dict[str, Any],
    emotion: Dict[str, Any],
    confidence: float,
    user_text: str,
) -> Dict[str, Any]:
    """
    Generate personalised coaching insights.
    Tries Gemini Flash first; falls back to rule-based if unavailable.
    """
    # Trim transcript to last ~400 words for the prompt
    words = user_text.split()
    excerpt = " ".join(words[-400:]) if len(words) > 400 else user_text

    prompt = _build_prompt(scenario, speech, nlp, alignment, voice, emotion, confidence, excerpt)

    raw = _call_gemini(prompt)

    if raw:
        parsed = _parse_json(raw)
        if parsed and all(k in parsed for k in ("strengths", "weaknesses", "suggestions", "coaching_note")):
            parsed["generated_by"] = "gemini"
            logger.info("[insights] generated by Gemini Flash")
            return parsed
        logger.warning("[insights] LLM output did not parse cleanly — falling back")

    logger.info("[insights] using rule-based fallback")
    return _rule_based_fallback(scenario, nlp, alignment, speech, confidence)
