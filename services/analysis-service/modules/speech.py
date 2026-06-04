import re
from typing import Any, Dict, List


FILLER_RE = re.compile(r"\b(um+|uh+|like|you know|basically|actually|sort of|kind of)\b", re.I)


def _count_sentences(text: str) -> int:
    parts = re.split(r"[.!?]+", text)
    return max(1, len([p for p in parts if p.strip()]))


def analyze_speech(transcript: str) -> Dict[str, Any]:
    words = re.findall(r"\b[\w']+\b", transcript)
    word_count = len(words)

    filler_matches = list(FILLER_RE.finditer(transcript))
    filler_count = len(filler_matches)

    # We don't have real timestamps in MVP. Estimate duration from text length.
    # Assumption: ~140 wpm baseline (neutral speaking pace).
    est_minutes = max(0.25, word_count / 140.0)
    wpm = word_count / est_minutes

    sentences = _count_sentences(transcript)
    avg_words_per_sentence = word_count / max(1, sentences)

    filler_per_100 = (filler_count / max(1, word_count)) * 100.0

    pace_score = 1.0
    if wpm > 175:
        pace_score = 0.6
    elif wpm < 105:
        pace_score = 0.7

    filler_score = 1.0
    if filler_per_100 > 4:
        filler_score = 0.6
    elif filler_per_100 > 2:
        filler_score = 0.8

    structure_score = 1.0
    if avg_words_per_sentence > 28:
        structure_score = 0.75

    score = round(0.45 * pace_score + 0.35 * filler_score + 0.20 * structure_score, 3)

    highlights: List[Dict[str, Any]] = []
    if wpm > 175:
        highlights.append({"type": "pace", "severity": "warn", "message": "Speaking pace is a bit fast."})
    elif wpm < 105:
        highlights.append({"type": "pace", "severity": "info", "message": "Speaking pace is a bit slow."})

    if filler_per_100 > 2:
        highlights.append(
            {
                "type": "fillers",
                "severity": "info" if filler_per_100 <= 4 else "warn",
                "message": "Filler words are frequent; try replacing them with short pauses.",
            }
        )

    return {
        "word_count": word_count,
        "estimated_minutes": round(est_minutes, 3),
        "wpm_estimate": round(wpm, 1),
        "fillers": filler_count,
        "filler_per_100_words": round(filler_per_100, 2),
        "avg_words_per_sentence": round(avg_words_per_sentence, 1),
        "score": score,
        "highlights": highlights,
    }