"use client";

import { useState } from "react";



type Issue = {
  id: string;
  emoji: string;
  title: string;
  tagline: string;
  why: string;
  signs: string[];
  drills: { title: string; steps: string }[];
  color: string;
};

const ISSUES: Issue[] = [
  {
    id: "fillers",
    emoji: "💬",
    title: "Filler Words",
    tagline: "Ums, uhs, and likes — the confidence killers",
    why: "Filler words signal uncertainty and erode listener trust. Replacing them with intentional pauses communicates control.",
    signs: ["Saying 'um', 'uh', 'like', 'you know' more than twice per minute", "Filling silence rather than pausing"],
    drills: [
      { title: "The Pause Replacement", steps: "Read a paragraph aloud. Every time you feel the urge to say 'um', pause for 1 full second instead. Repeat 3x." },
      { title: "Record + Count", steps: "Record yourself answering a question for 60s. Count every filler word. Aim to halve the count by your next attempt." },
      { title: "Slow Start", steps: "Begin your next answer with a deliberate 1-second pause before your first word. This resets your pace and kills the opening 'um'." }
    ],
    color: "#f59e0b"
  },
  {
    id: "pace",
    emoji: "⏱",
    title: "Speaking Pace",
    tagline: "Too fast loses clarity; too slow loses attention",
    why: "The ideal pace for professional communication is 130–160 WPM. Nervousness pushes you faster; boredom slows you. Both cost you.",
    signs: ["Rushing through key points", "Losing breath mid-sentence", "Listeners asking you to repeat yourself"],
    drills: [
      { title: "3-Speed Reading", steps: "Read a paragraph at 3 speeds: deliberate slow, comfortable, and fast. Find the speed that feels slightly slower than normal — that's your target." },
      { title: "Record & Measure", steps: "Record 60 seconds. Count words. Divide by 1. If > 170, practice reading the same text 30% slower." },
      { title: "Breath Marks", steps: "Annotate a script with breath-pause markers. Force a micro-pause at every comma and a full pause at every period." }
    ],
    color: "#6366f1"
  },
  {
    id: "clarity",
    emoji: "🔊",
    title: "Vocal Clarity",
    tagline: "Being heard clearly is a skill, not a trait",
    why: "Mumbling, trailing off at sentence ends, and swallowing consonants make you hard to follow even when your ideas are strong.",
    signs: ["Trailing off at the end of sentences", "Slurred consonants", "Listeners leaning in to hear you"],
    drills: [
      { title: "Consonant Crunch", steps: "Say 'Red lorry, yellow lorry' and 'She sells seashells' 5x each, overarticulating every consonant. Feels silly — works." },
      { title: "Upward Endings", steps: "Practice ending declarative sentences with a slight upward volume. Record and listen for trailing-off patterns." },
      { title: "The Pencil Trick", steps: "Hold a pencil lightly between your teeth (not biting) and read aloud for 2 minutes. When you remove it, your articulation improves." }
    ],
    color: "#10b981"
  },
  {
    id: "structure",
    emoji: "🗂",
    title: "Answer Structure",
    tagline: "Great ideas need a frame to land",
    why: "Unstructured answers ramble, lose the listener, and make you seem unprepared — even when you know the material.",
    signs: ["Giving long answers with no clear conclusion", "Starting your answer before knowing where it's going", "Repeating the same point in different words"],
    drills: [
      { title: "STAR in 90 Seconds", steps: "Pick a past experience. Tell it in: Situation (15s), Task (15s), Action (45s), Result (15s). Exactly 90 seconds total." },
      { title: "Bottom Line First", steps: "Practice answering questions with your conclusion first: 'The key thing I did was... because...' then expand." },
      { title: "3-Point Rule", steps: "Answer every open-ended question with exactly 3 points. Say them: 'There are three things I did: one... two... three...'" }
    ],
    color: "#7c3aed"
  },
  {
    id: "eyecontact",
    emoji: "👁",
    title: "Eye Contact",
    tagline: "Presence builds trust; looking away breaks it",
    why: "In video calls, eye contact means looking at the camera — not your own face. This is a learnable physical habit.",
    signs: ["Looking at your own preview during video calls", "Scanning the screen while talking", "Losing track of the camera lens position"],
    drills: [
      { title: "Sticky Dot Method", steps: "Place a small dot or sticker directly above your camera lens. Focus on the dot while speaking. Practice for 5 min daily." },
      { title: "5-4-1 Rhythm", steps: "Hold camera eye contact for 5 seconds, glance away for 4 seconds, return for 1 second. Repeat. This feels natural and avoids the stare." },
      { title: "Record Yourself", steps: "Record a 2-min answer with video. Watch it back with no sound. Identify where your gaze goes. Correct in next take." }
    ],
    color: "#06b6d4"
  },
  {
    id: "confidence",
    emoji: "⚡",
    title: "Projected Confidence",
    tagline: "Confidence is a performance, not a feeling",
    why: "Even when nervous, projecting confidence through voice, posture, and pacing creates a perception of credibility that you can then grow into.",
    signs: ["Starting sentences with 'I think' or 'Maybe' when you mean it as fact", "Upward inflection on statements (making them sound like questions)", "Shrinking physically — hunched shoulders, looking down"],
    drills: [
      { title: "Power Pose Reset", steps: "Before any session: stand tall, hands on hips, chin up for 2 minutes. Research shows this shifts hormone levels measurably." },
      { title: "Downward Inflection", steps: "Practice ending statements with a firm, slightly downward tone. Record yourself. Statements should not sound like questions." },
      { title: "Certainty Language", steps: "Replace 'I think' → 'I know', 'maybe' → 'likely', 'sort of' → 'specifically'. Practice with flashcards." }
    ],
    color: "#f43f5e"
  }
];

function IssueCard({ issue }: { issue: Issue }) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{
      borderRadius: "var(--radius-lg)",
      border: "1px solid var(--border)",
      background: "var(--card)",
      overflow: "hidden",
      transition: "border-color 0.2s"
    }}>
      <button
        onClick={() => setOpen((p) => !p)}
        style={{
          width: "100%", textAlign: "left", background: "none", border: "none",
          padding: "1.25rem 1.5rem", cursor: "pointer", color: "inherit",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div style={{
            width: "44px", height: "44px", borderRadius: "12px", flexShrink: 0,
            background: `${issue.color}20`, border: `1px solid ${issue.color}40`,
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.3rem"
          }}>
            {issue.emoji}
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: "1rem" }}>{issue.title}</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-2)", marginTop: "0.15rem" }}>{issue.tagline}</div>
          </div>
        </div>
        <span style={{ fontSize: "1.2rem", color: "var(--text-3)", flexShrink: 0, transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>›</span>
      </button>

      {open && (
        <div style={{ padding: "0 1.5rem 1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem", borderTop: "1px solid var(--border)" }}>
          {/* Why it matters */}
          <div style={{ padding: "0.85rem 1rem", borderRadius: "var(--radius-md)", background: `${issue.color}10`, border: `1px solid ${issue.color}25`, marginTop: "1.25rem" }}>
            <div style={{ fontSize: "0.78rem", fontWeight: 600, color: issue.color, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.4rem" }}>Why it matters</div>
            <div style={{ fontSize: "0.875rem", color: "var(--text-1)" }}>{issue.why}</div>
          </div>

          {/* Signs */}
          <div>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-2)", marginBottom: "0.5rem" }}>Signs you have this issue</div>
            <ul style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              {issue.signs.map((s, i) => (
                <li key={i} style={{ fontSize: "0.85rem", color: "var(--text-2)" }}>{s}</li>
              ))}
            </ul>
          </div>

          {/* Drills */}
          <div>
            <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-2)", marginBottom: "0.75rem" }}>Practice Drills</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {issue.drills.map((d, i) => (
                <div key={i} style={{ padding: "0.85rem 1rem", borderRadius: "var(--radius-md)", background: "rgba(255, 255, 255, 1)", border: "1px solid var(--border)" }}>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-1)", marginBottom: "0.35rem" }}>
                    {i + 1}. {d.title}
                  </div>
                  <div style={{ fontSize: "0.82rem", color: "var(--text-2)", lineHeight: 1.6 }}>{d.steps}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SpeechSupportPage() {
  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      <div>
        <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: 0 }}>💬 Speech Support</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9rem" }}>
          Targeted exercises and drills for the most common communication issues.
        </p>
      </div>

      {/* Quick tip banner */}
      <div style={{
        padding: "1rem 1.25rem", borderRadius: "var(--radius-md)",
        background: "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(124,58,237,0.08))",
        border: "1px solid rgba(99,102,241,0.2)",
        fontSize: "0.875rem", color: "var(--text-1)"
      }}>
        💡 <strong>How to use this:</strong> Identify your top issue from the <a href="/roadmap" style={{ color: "#a5b4fc" }}>Roadmap page</a>, then find it below. Do one drill per day for a week before your next practice session.
      </div>

      {/* Issue cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {ISSUES.map((issue) => (
          <IssueCard key={issue.id} issue={issue} />
        ))}
      </div>
    </div>
  );
}
