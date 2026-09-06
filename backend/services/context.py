"""
Context engine: builds structured context from resume/JD/notes, and formats it
for injection into Gemini system prompts.
Port of services/contextEngine.ts.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from services.scenarios import normalize_scenario, Scenario


# ── Helpers ────────────────────────────────────────────────────────────────────

def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in (s.strip() for s in items):
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _first_line_value(text: str, labels: list[str]) -> Optional[str]:
    escaped = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"^(?:{escaped})\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _split_terms(text: str, patterns: list[re.Pattern]) -> list[str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    matched = [line for line in lines if any(p.search(line) for p in patterns)]
    terms: list[str] = []
    for line in matched:
        # Strip everything up to and including the first colon
        body = re.sub(r"^.*?:\s*", "", line)
        terms.extend(t.strip() for t in re.split(r"[,/|;]+", body))
    return _uniq(terms)


def _compact(parts: list[Optional[str]]) -> str:
    return "\n\n".join(p for p in parts if p and p.strip())


# ── Public API ─────────────────────────────────────────────────────────────────

StructuredContext = dict[str, Any]


def build_structured_context(input_data: dict[str, Any]) -> tuple[str, StructuredContext]:
    """
    Build (context_raw, context_json) from the user-supplied session body.
    Mirrors buildStructuredContext() in contextEngine.ts.
    """
    scenario: Scenario = normalize_scenario(input_data.get("scenario"))

    def _clean(key: str) -> Optional[str]:
        v = input_data.get(key)
        return v.strip()[:30_000] if isinstance(v, str) and v.strip() else None

    sources: dict[str, Optional[str]] = {
        "resume": _clean("resumeText"),
        "jobDescription": _clean("jobDescription"),
        "topicNotes": _clean("topicNotes"),
        "freeText": _clean("freeText") or _clean("contextText") or _clean("text"),
    }

    text = _compact([sources["resume"], sources["jobDescription"], sources["topicNotes"], sources["freeText"]])
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # ── Role ──
    role = _first_line_value(text, ["role", "target role", "position"])
    if not role:
        m = re.search(
            r"(product manager|software engineer|data analyst|designer|founder|sales|consultant)"
            r"(?:\s+(intern|new grad|junior|senior|lead))?",
            text,
            re.IGNORECASE,
        )
        if m:
            role = m.group(0)

    # ── Company ──
    company = _first_line_value(text, ["company", "organization"])
    if not company:
        m2 = re.search(r"at\s+([A-Z][\w&.-]{1,})", text)
        if m2:
            company = re.sub(r"^at\s+", "", m2.group(0), flags=re.IGNORECASE).strip()

    # ── Other fields ──
    audience = _first_line_value(text, ["audience", "stakeholders", "listener"])
    objective = _first_line_value(text, ["objective", "goal", "purpose", "meeting goal", "pitch goal"])

    skills = _split_terms(text, [re.compile(r"skills", re.I), re.compile(r"tech", re.I),
                                  re.compile(r"stack", re.I), re.compile(r"tools", re.I)])
    projects = _uniq(
        [line for line in lines if re.search(r"project|built|launched|shipped", line, re.I)][:8]
    )
    focus_areas = _split_terms(text, [re.compile(r"focus", re.I), re.compile(r"looking for", re.I),
                                       re.compile(r"evaluate", re.I), re.compile(r"assessment", re.I),
                                       re.compile(r"areas", re.I)])
    candidate_background = _uniq(
        [line for line in lines if re.search(r"experience|background|worked|led|built|managed|intern", line, re.I)][:8]
    )

    context_json: StructuredContext = {
        "scenario": scenario,
        "role": role.strip() if role else None,
        "company": company.strip() if company else None,
        "audience": audience.strip() if audience else None,
        "objective": objective.strip() if objective else None,
        "skills": skills or None,
        "projects": projects or None,
        "focusAreas": focus_areas or None,
        "candidateBackground": candidate_background or None,
        "rawSummary": " | ".join(lines[:10]) if lines else None,
        "sources": {k: v for k, v in sources.items() if v},
    }

    return text, context_json


def format_context_for_prompt(ctx: Optional[StructuredContext]) -> str:
    """Render context dict as a bullet-point block for injection into a system prompt."""
    if not ctx:
        return ""

    parts: list[str] = []
    if ctx.get("role"):
        parts.append(f"Role/topic target: {ctx['role']}")
    if ctx.get("company"):
        parts.append(f"Company/organization: {ctx['company']}")
    if ctx.get("audience"):
        parts.append(f"Audience/stakeholders: {ctx['audience']}")
    if ctx.get("objective"):
        parts.append(f"Objective: {ctx['objective']}")
    if ctx.get("level"):
        parts.append(f"Level: {ctx['level']}")
    if ctx.get("skills"):
        parts.append(f"Skills: {', '.join(ctx['skills'])}")
    if ctx.get("projects"):
        parts.append(f"Projects/examples: {'; '.join(ctx['projects'][:5])}")
    if ctx.get("focusAreas"):
        parts.append(f"Focus areas: {', '.join(ctx['focusAreas'])}")
    if ctx.get("candidateBackground"):
        parts.append(f"Candidate background: {'; '.join(ctx['candidateBackground'][:4])}")
    if ctx.get("rawSummary"):
        parts.append(f"Notes: {ctx['rawSummary']}")

    if not parts:
        return ""
    return "\n\nSession context:\n- " + "\n- ".join(parts)
