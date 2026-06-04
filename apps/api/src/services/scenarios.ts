export const SCENARIOS = ["INTERVIEW", "PITCH", "MEETING"] as const;

export type Scenario = (typeof SCENARIOS)[number];

// ── Persona Library ────────────────────────────────────────────────────────────

export type PersonaId =
  | "DEFAULT"
  | "THE_SKEPTIC"
  | "THE_FRIENDLY"
  | "THE_RUSHED"
  | "THE_PANEL"
  | "THE_CONFUSED";

export interface PersonaConfig {
  id: PersonaId;
  label: string;
  desc: string;
  /** Which scenarios this persona is compatible with */
  scenarios: Scenario[];
  /** Injected into system prompt to shape AI behaviour */
  modifier: string;
}

export const PERSONAS: PersonaConfig[] = [
  {
    id: "DEFAULT",
    label: "Standard",
    desc: "Balanced, professional AI coach",
    scenarios: ["INTERVIEW", "PITCH", "MEETING"],
    modifier: ""
  },
  {
    id: "THE_SKEPTIC",
    label: "The Skeptic",
    desc: "Challenges every claim and demands hard evidence",
    scenarios: ["PITCH", "INTERVIEW"],
    modifier:
      "PERSONA — The Skeptic: Challenge every claim the user makes. Ask 'how do you know that?', 'what's the evidence?', and 'why should I believe this?' frequently. Be polite but persistently unconvinced until the user provides data, specifics, or a concrete example. Never accept vague answers."
  },
  {
    id: "THE_FRIENDLY",
    label: "The Mentor",
    desc: "Supportive coach who encourages and guides",
    scenarios: ["INTERVIEW", "PITCH", "MEETING"],
    modifier:
      "PERSONA — The Mentor: Be warm, encouraging, and supportive. When the user gives a weak answer, gently reframe it as a learning moment: 'That's a good start — want to try adding a specific example?' Celebrate good answers explicitly. Never be harsh."
  },
  {
    id: "THE_RUSHED",
    label: "The Rushed Manager",
    desc: "Cuts off tangents and demands concise updates",
    scenarios: ["MEETING", "PITCH"],
    modifier:
      "PERSONA — The Rushed Manager: You are extremely time-pressured. Interrupt politely but firmly when answers are too long: 'Sorry, I only have 2 minutes — bottom line it.' Reward brevity. If the user takes more than 4 sentences to answer, cut in and ask for the 1-sentence version. Always signal urgency."
  },
  {
    id: "THE_PANEL",
    label: "The Tough Panel",
    desc: "Rapid-fire questions with minimal warmth",
    scenarios: ["INTERVIEW"],
    modifier:
      "PERSONA — The Tough Panel: You are a panel of senior interviewers. Be formal, brief, and move quickly. Ask back-to-back follow-ups without affirmation. Use phrases like 'next question:', 'be more specific:', 'that answer was vague — rephrase.' Give no positive reinforcement. Probe for depth relentlessly."
  },
  {
    id: "THE_CONFUSED",
    label: "The Confused Stakeholder",
    desc: "Needs everything explained simply, asks 'why does this matter?'",
    scenarios: ["PITCH", "MEETING"],
    modifier:
      "PERSONA — The Confused Stakeholder: Frequently say 'I'm not sure I follow' or 'can you explain that more simply?' Ask 'why does this matter to me?' after most claims. Force the user to communicate clearly without jargon. Act genuinely curious but not hostile — you want to understand, you just need simpler explanations."
  }
];

export function getPersona(id: PersonaId | null | undefined): PersonaConfig {
  return PERSONAS.find((p) => p.id === id) ?? PERSONAS[0]!;
}

// ── Pressure Mode ──────────────────────────────────────────────────────────────

export type PressureLevel = 0 | 1 | 2 | 3;

export interface PressureConfig {
  level: PressureLevel;
  label: string;
  modifier: string;
}

export const PRESSURE_LEVELS: PressureConfig[] = [
  {
    level: 0,
    label: "None",
    modifier: ""
  },
  {
    level: 1,
    label: "Mild",
    modifier:
      "PRESSURE — Mild: Occasionally (every 3-4 exchanges) introduce a small curveball — an unexpected follow-up or a gentle challenge that shifts the topic slightly. Once during the session, note that time is running short."
  },
  {
    level: 2,
    label: "Moderate",
    modifier:
      "PRESSURE — Moderate: Regularly interrupt or redirect. At least once, cut the user off mid-answer politely and ask a completely new question. Play devil's advocate after every other answer. Introduce a time warning around the midpoint. Ask at least one hostile or combative question (e.g. 'Why would anyone choose you over a more experienced candidate?')."
  },
  {
    level: 3,
    label: "High",
    modifier:
      "PRESSURE — High: Simulate a high-stakes, hostile environment. Interrupt frequently. Openly disagree with user statements and challenge them to defend their position. Introduce unexpected topic changes. Express impatience with long answers. Ask at least 2 difficult 'why should we believe you?' questions. Simulate a crisis point mid-session where the stakes feel very high."
  }
];

export function getPressureModifier(level: PressureLevel | null | undefined): string {
  return PRESSURE_LEVELS.find((p) => p.level === (level ?? 0))?.modifier ?? "";
}

type ScenarioConfig = {
  label: string;
  aiRole: string;
  openingPrompt: string;
  liveGoals: string[];
  evaluationFocus: string[];
};

export const scenarioConfig: Record<Scenario, ScenarioConfig> = {
  INTERVIEW: {
    label: "Interview",
    aiRole: "interviewer",
    openingPrompt: "Start with a concise, realistic interview opener.",
    liveGoals: [
      "ask role-relevant behavioral and technical follow-ups",
      "probe for examples, reasoning, trade-offs, and impact",
      "adapt to the candidate's resume and target job"
    ],
    evaluationFocus: ["role relevance", "structured examples", "specific impact", "confidence"]
  },
  PITCH: {
    label: "Pitch",
    aiRole: "pitch reviewer and skeptical stakeholder",
    openingPrompt: "Ask the user to deliver their pitch, then challenge clarity, audience fit, and persuasion.",
    liveGoals: [
      "test the problem framing and value proposition",
      "ask about audience, differentiation, evidence, and call to action",
      "push for concise, persuasive answers"
    ],
    evaluationFocus: ["problem framing", "audience fit", "persuasiveness", "clear call to action"]
  },
  MEETING: {
    label: "Meeting",
    aiRole: "meeting participant and facilitator",
    openingPrompt: "Start a realistic work meeting and ask for the user's update or recommendation.",
    liveGoals: [
      "encourage crisp updates, decisions, owners, and next steps",
      "ask clarifying questions when points are vague",
      "simulate stakeholder pressure and collaboration"
    ],
    evaluationFocus: ["concision", "collaboration", "decision clarity", "action items"]
  }
};

export function normalizeScenario(value: unknown): Scenario {
  return SCENARIOS.includes(value as Scenario) ? (value as Scenario) : "INTERVIEW";
}
export function normalizePersona(value: unknown): PersonaId {
  const ids = PERSONAS.map((p) => p.id);
  return ids.includes(value as PersonaId) ? (value as PersonaId) : "DEFAULT";
}

export function normalizePressureLevel(value: unknown): PressureLevel {
  const n = Number(value);
  return ([0, 1, 2, 3] as PressureLevel[]).includes(n as PressureLevel)
    ? (n as PressureLevel)
    : 0;
}
