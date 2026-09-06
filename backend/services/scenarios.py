"""
Scenarios, personas, and pressure-level configuration.
Port of services/scenarios.ts — pure data + helpers, no framework deps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# ── Scenarios ──────────────────────────────────────────────────────────────────

Scenario = Literal["INTERVIEW", "PITCH", "MEETING"]
SCENARIOS: list[Scenario] = ["INTERVIEW", "PITCH", "MEETING"]

# ── Persona Library ────────────────────────────────────────────────────────────

PersonaId = Literal[
    "DEFAULT",
    "THE_SKEPTIC",
    "THE_FRIENDLY",
    "THE_RUSHED",
    "THE_PANEL",
    "THE_CONFUSED",
]


@dataclass
class PersonaConfig:
    id: PersonaId
    label: str
    desc: str
    scenarios: list[Scenario]
    modifier: str


PERSONAS: list[PersonaConfig] = [
    PersonaConfig(
        id="DEFAULT",
        label="Standard",
        desc="Balanced, professional AI coach",
        scenarios=["INTERVIEW", "PITCH", "MEETING"],
        modifier="",
    ),
    PersonaConfig(
        id="THE_SKEPTIC",
        label="The Skeptic",
        desc="Challenges every claim and demands hard evidence",
        scenarios=["PITCH", "INTERVIEW"],
        modifier=(
            "PERSONA — The Skeptic: Challenge every claim the user makes. "
            "Ask 'how do you know that?', 'what's the evidence?', and "
            "'why should I believe this?' frequently. Be polite but persistently "
            "unconvinced until the user provides data, specifics, or a concrete "
            "example. Never accept vague answers."
        ),
    ),
    PersonaConfig(
        id="THE_FRIENDLY",
        label="The Mentor",
        desc="Supportive coach who encourages and guides",
        scenarios=["INTERVIEW", "PITCH", "MEETING"],
        modifier=(
            "PERSONA — The Mentor: Be warm, encouraging, and supportive. "
            "When the user gives a weak answer, gently reframe it as a learning moment: "
            "'That's a good start — want to try adding a specific example?' "
            "Celebrate good answers explicitly. Never be harsh."
        ),
    ),
    PersonaConfig(
        id="THE_RUSHED",
        label="The Rushed Manager",
        desc="Cuts off tangents and demands concise updates",
        scenarios=["MEETING", "PITCH"],
        modifier=(
            "PERSONA — The Rushed Manager: You are extremely time-pressured. "
            "Interrupt politely but firmly when answers are too long: "
            "'Sorry, I only have 2 minutes — bottom line it.' "
            "Reward brevity. If the user takes more than 4 sentences to answer, "
            "cut in and ask for the 1-sentence version. Always signal urgency."
        ),
    ),
    PersonaConfig(
        id="THE_PANEL",
        label="The Tough Panel",
        desc="Rapid-fire questions with minimal warmth",
        scenarios=["INTERVIEW"],
        modifier=(
            "PERSONA — The Tough Panel: You are a panel of senior interviewers. "
            "Be formal, brief, and move quickly. Ask back-to-back follow-ups without "
            "affirmation. Use phrases like 'next question:', 'be more specific:', "
            "'that answer was vague — rephrase.' Give no positive reinforcement. "
            "Probe for depth relentlessly."
        ),
    ),
    PersonaConfig(
        id="THE_CONFUSED",
        label="The Confused Stakeholder",
        desc="Needs everything explained simply, asks 'why does this matter?'",
        scenarios=["PITCH", "MEETING"],
        modifier=(
            "PERSONA — The Confused Stakeholder: Frequently say 'I'm not sure I follow' "
            "or 'can you explain that more simply?' Ask 'why does this matter to me?' "
            "after most claims. Force the user to communicate clearly without jargon. "
            "Act genuinely curious but not hostile — you want to understand, you just "
            "need simpler explanations."
        ),
    ),
]


def get_persona(persona_id: Optional[str]) -> PersonaConfig:
    for p in PERSONAS:
        if p.id == persona_id:
            return p
    return PERSONAS[0]


# ── Pressure Levels ────────────────────────────────────────────────────────────

PressureLevel = Literal[0, 1, 2, 3]


@dataclass
class PressureConfig:
    level: int
    label: str
    modifier: str


PRESSURE_LEVELS: list[PressureConfig] = [
    PressureConfig(level=0, label="None", modifier=""),
    PressureConfig(
        level=1,
        label="Mild",
        modifier=(
            "PRESSURE — Mild: Occasionally (every 3-4 exchanges) introduce a small "
            "curveball — an unexpected follow-up or a gentle challenge that shifts the "
            "topic slightly. Once during the session, note that time is running short."
        ),
    ),
    PressureConfig(
        level=2,
        label="Moderate",
        modifier=(
            "PRESSURE — Moderate: Regularly interrupt or redirect. At least once, cut "
            "the user off mid-answer politely and ask a completely new question. Play "
            "devil's advocate after every other answer. Introduce a time warning around "
            "the midpoint. Ask at least one hostile or combative question (e.g. 'Why "
            "would anyone choose you over a more experienced candidate?')."
        ),
    ),
    PressureConfig(
        level=3,
        label="High",
        modifier=(
            "PRESSURE — High: Simulate a high-stakes, hostile environment. Interrupt "
            "frequently. Openly disagree with user statements and challenge them to defend "
            "their position. Introduce unexpected topic changes. Express impatience with "
            "long answers. Ask at least 2 difficult 'why should we believe you?' questions. "
            "Simulate a crisis point mid-session where the stakes feel very high."
        ),
    ),
]


def get_pressure_modifier(level: Optional[int]) -> str:
    lvl = level if level is not None else 0
    for p in PRESSURE_LEVELS:
        if p.level == lvl:
            return p.modifier
    return ""


# ── Scenario Config ────────────────────────────────────────────────────────────

@dataclass
class ScenarioConfig:
    label: str
    ai_role: str
    opening_prompt: str
    live_goals: list[str]
    evaluation_focus: list[str]


SCENARIO_CONFIG: dict[Scenario, ScenarioConfig] = {
    "INTERVIEW": ScenarioConfig(
        label="Interview",
        ai_role="interviewer",
        opening_prompt="Start with a concise, realistic interview opener.",
        live_goals=[
            "ask role-relevant behavioral and technical follow-ups",
            "probe for examples, reasoning, trade-offs, and impact",
            "adapt to the candidate's resume and target job",
        ],
        evaluation_focus=["role relevance", "structured examples", "specific impact", "confidence"],
    ),
    "PITCH": ScenarioConfig(
        label="Pitch",
        ai_role="pitch reviewer and skeptical stakeholder",
        opening_prompt="Ask the user to deliver their pitch, then challenge clarity, audience fit, and persuasion.",
        live_goals=[
            "test the problem framing and value proposition",
            "ask about audience, differentiation, evidence, and call to action",
            "push for concise, persuasive answers",
        ],
        evaluation_focus=["problem framing", "audience fit", "persuasiveness", "clear call to action"],
    ),
    "MEETING": ScenarioConfig(
        label="Meeting",
        ai_role="meeting participant and facilitator",
        opening_prompt="Start a realistic work meeting and ask for the user's update or recommendation.",
        live_goals=[
            "encourage crisp updates, decisions, owners, and next steps",
            "ask clarifying questions when points are vague",
            "simulate stakeholder pressure and collaboration",
        ],
        evaluation_focus=["concision", "collaboration", "decision clarity", "action items"],
    ),
}


# ── Normalizers ────────────────────────────────────────────────────────────────

def normalize_scenario(value: object) -> Scenario:
    if value in SCENARIOS:
        return value  # type: ignore[return-value]
    return "INTERVIEW"


def normalize_persona(value: object) -> PersonaId:
    valid = [p.id for p in PERSONAS]
    if value in valid:
        return value  # type: ignore[return-value]
    return "DEFAULT"


def normalize_pressure_level(value: object) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
        if n in (0, 1, 2, 3):
            return n
    except (TypeError, ValueError):
        pass
    return 0
