"""Scoring input helpers. No database timestamps are treated as speech timing."""
import math


def answer_pairs(transcript: list[dict]) -> list[tuple[str | None, str]]:
    question = None
    answers = []
    for turn in transcript:
        text = turn.get("text", "").strip()
        if not text:
            continue
        if turn.get("speaker") == "ai":
            question = text
        elif turn.get("speaker") == "user":
            answers.append((question, text))
    return answers


def measured_duration(transcript: list[dict]) -> float | None:
    intervals = []
    for turn in transcript:
        if turn.get("speaker") != "user" or not turn.get("text", "").strip():
            continue
        start, end = turn.get("audioStartSeconds"), turn.get("audioEndSeconds")
        if (not isinstance(start, (float, int)) or not isinstance(end, (float, int))
                or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start):
            return None  # Typed or partially timed text cannot share a measured WPM.
        intervals.append((start, end))
    if not intervals:
        return None
    # Union offsets so overlapping transcription windows are not double-counted.
    intervals.sort()
    total = 0.0
    start, end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def text_windows(text: str, limit: int = 600) -> list[str]:
    """Bound individual inputs, but cover every character without resampling."""
    words = text.split()
    windows, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 > limit and current:
            windows.append(current)
            current = ""
        while len(word) > limit:
            if current:
                windows.append(current)
                current = ""
            windows.append(word[:limit])
            word = word[limit:]
        current = f"{current} {word}".strip()
    if current:
        windows.append(current)
    return windows or [""]
