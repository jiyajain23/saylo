import re
from typing import Any, Dict, List


SCENARIO_RULES = {
    "INTERVIEW": {
        "signals": {
            "impact": r"\b(impact|result|metric|improv|reduc|increas|launched|shipped|saved)\b",
            "reasoning": r"\b(because|so that|trade-?off|constraint|therefore|decided)\b",
            "specific_example": r"\b(project|team|customer|user|built|led|implemented)\b",
        },
        "notes": {
            "impact": "Add an impact line with a metric, outcome, or what changed.",
            "reasoning": "Make your reasoning explicit with trade-offs, constraints, or why that approach.",
            "specific_example": "Ground the answer in a specific example rather than a general claim.",
        },
    },
    "PITCH": {
        "signals": {
            "problem": r"\b(problem|pain|need|gap|opportunity)\b",
            "audience": r"\b(customer|user|buyer|market|audience|stakeholder)\b",
            "value": r"\b(value|benefit|save|grow|increase|reduce|different|unique)\b",
            "cta": r"\b(next step|ask|pilot|buy|invest|approve|try|sign up)\b",
        },
        "notes": {
            "problem": "Open with the problem or audience pain before jumping to the solution.",
            "audience": "Name the audience and why this matters to them.",
            "value": "Make the value proposition more concrete and differentiated.",
            "cta": "Close with a clear ask or next step.",
        },
    },
    "MEETING": {
        "signals": {
            "decision": r"\b(decision|recommend|proposal|option|approve|choose)\b",
            "action": r"\b(action|owner|next step|follow up|deadline|by friday|by monday)\b",
            "collaboration": r"\b(we|team|stakeholder|align|feedback|agree|blocker)\b",
            "concise_update": r"\b(status|update|summary|priority|risk)\b",
        },
        "notes": {
            "decision": "Clarify the decision or recommendation you want from the meeting.",
            "action": "State owners, next steps, or deadlines.",
            "collaboration": "Show how you are aligning with the team or stakeholders.",
            "concise_update": "Frame the update with status, priority, risks, or asks.",
        },
    },
}


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
    rules = SCENARIO_RULES.get(scenario, SCENARIO_RULES["INTERVIEW"])
    lower = text.lower()

    matched = []
    missing = []
    for name, pattern in rules["signals"].items():
        if re.search(pattern, lower):
            matched.append(name)
        else:
            missing.append(name)

    base_score = 0.55 + (0.35 * (len(matched) / max(1, len(rules["signals"]))))
    context_bonus = 0.10 if _context_match(lower, context) else 0.0
    score = round(min(1.0, base_score + context_bonus), 3)

    notes = [rules["notes"][name] for name in missing if name in rules["notes"]]
    if context and context_bonus == 0:
        notes.append("Tie the response more directly to the provided context.")

    return {
        "scenario": scenario,
        "score": score,
        "matchedSignals": matched,
        "missingSignals": missing,
        "notes": notes[:5],
    }
