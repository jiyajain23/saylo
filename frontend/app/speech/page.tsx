"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Lightbulb,
  ChevronDown,
  MessageSquareOff,
  Gauge,
  Volume2,
  Network,
  Eye,
  Award,
  Dumbbell,
  CheckCircle2
} from "lucide-react";

type Issue = {
  id: string;
  title: string;
  tagline: string;
  why: string;
  signs: string[];
  drills: { title: string; steps: string }[];
  color: string;
  icon: React.ReactNode;
};

const ISSUES: Issue[] = [
  {
    id: "fillers",
    title: "Filler Words",
    tagline: "Ums, uhs, and likes — the confidence killers",
    why: "Filler words signal uncertainty and erode listener trust. Replacing them with intentional pauses communicates control.",
    signs: ["Saying 'um', 'uh', 'like', 'you know' more than twice per minute", "Filling silence rather than pausing"],
    drills: [
      { title: "The Pause Replacement", steps: "Read a paragraph aloud. Every time you feel the urge to say 'um', pause for 1 full second instead. Repeat 3x." },
      { title: "Record + Count", steps: "Record yourself answering a question for 60s. Count every filler word. Aim to halve the count by your next attempt." },
      { title: "Slow Start", steps: "Begin your next answer with a deliberate 1-second pause before your first word. This resets your pace and kills the opening 'um'." }
    ],
    color: "#735200",
    icon: <MessageSquareOff size={20} style={{ color: "#735200" }} />
  },
  {
    id: "pace",
    title: "Speaking Pace",
    tagline: "Too fast loses clarity; too slow loses attention",
    why: "The ideal pace for professional communication is 130–160 WPM. Nervousness pushes you faster; boredom slows you. Both cost you.",
    signs: ["Rushing through key points", "Losing breath mid-sentence", "Listeners asking you to repeat yourself"],
    drills: [
      { title: "3-Speed Reading", steps: "Read a paragraph at 3 speeds: deliberate slow, comfortable, and fast. Find the speed that feels slightly slower than normal — that's your target." },
      { title: "Record & Measure", steps: "Record 60 seconds. Count words. Divide by 1. If > 170, practice reading the same text 30% slower." },
      { title: "Breath Marks", steps: "Annotate a script with breath-pause markers. Force a micro-pause at every comma and a full pause at every period." }
    ],
    color: "#296e91",
    icon: <Gauge size={20} style={{ color: "#296e91" }} />
  },
  {
    id: "clarity",
    title: "Vocal Clarity",
    tagline: "Being heard clearly is a skill, not a trait",
    why: "Mumbling, trailing off at sentence ends, and swallowing consonants make you hard to follow even when your ideas are strong.",
    signs: ["Trailing off at the end of sentences", "Slurred consonants", "Listeners leaning in to hear you"],
    drills: [
      { title: "Consonant Crunch", steps: "Say 'Red lorry, yellow lorry' and 'She sells seashells' 5x each, overarticulating every consonant. Feels silly — works." },
      { title: "Upward Endings", steps: "Practice ending declarative sentences with a slight upward volume. Record and listen for trailing-off patterns." },
      { title: "The Pencil Trick", steps: "Hold a pencil lightly between your teeth (not biting) and read aloud for 2 minutes. When you remove it, your articulation improves." }
    ],
    color: "#285c3b",
    icon: <Volume2 size={20} style={{ color: "#285c3b" }} />
  },
  {
    id: "structure",
    title: "Answer Structure",
    tagline: "Great ideas need a frame to land",
    why: "Unstructured answers ramble, lose the listener, and make you seem unprepared — even when you know the material.",
    signs: ["Giving long answers with no clear conclusion", "Starting your answer before knowing where it's going", "Repeating the same point in different words"],
    drills: [
      { title: "STAR in 90 Seconds", steps: "Pick a past experience. Tell it in: Situation (15s), Task (15s), Action (45s), Result (15s). Exactly 90 seconds total." },
      { title: "Bottom Line First", steps: "Practice answering questions with your conclusion first: 'The key thing I did was... because...' then expand." },
      { title: "3-Point Rule", steps: "Answer every open-ended question with exactly 3 points. Say them: 'There are three things I did: one... two... three...'" }
    ],
    color: "#296e91",
    icon: <Network size={20} style={{ color: "#296e91" }} />
  },
  {
    id: "eyecontact",
    title: "Eye Contact",
    tagline: "Presence builds trust; looking away breaks it",
    why: "In video calls, eye contact means looking at the camera — not your own face. This is a learnable physical habit.",
    signs: ["Looking at your own preview during video calls", "Scanning the screen while talking", "Losing track of the camera lens position"],
    drills: [
      { title: "Sticky Dot Method", steps: "Place a small dot or sticker directly above your camera lens. Focus on the dot while speaking. Practice for 5 min daily." },
      { title: "5-4-1 Rhythm", steps: "Hold camera eye contact for 5 seconds, glance away for 4 seconds, return for 1 second. Repeat. This feels natural and avoids the stare." },
      { title: "Record Yourself", steps: "Record a 2-min answer with video. Watch it back with no sound. Identify where your gaze goes. Correct in next take." }
    ],
    color: "#296e91",
    icon: <Eye size={20} style={{ color: "#296e91" }} />
  },
  {
    id: "confidence",
    title: "Projected Confidence",
    tagline: "Confidence is a performance, not a feeling",
    why: "Even when nervous, projecting confidence through voice, posture, and pacing creates a perception of credibility that you can then grow into.",
    signs: ["Starting sentences with 'I think' or 'Maybe' when you mean it as fact", "Upward inflection on statements (making them sound like questions)", "Shrinking physically — hunched shoulders, looking down"],
    drills: [
      { title: "Power Pose Reset", steps: "Before any session: stand tall, hands on hips, chin up for 2 minutes. Research shows this shifts hormone levels measurably." },
      { title: "Downward Inflection", steps: "Practice ending statements with a firm, slightly downward tone. Record yourself. Statements should not sound like questions." },
      { title: "Certainty Language", steps: "Replace 'I think' → 'I know', 'maybe' → 'likely', 'sort of' → 'specifically'. Practice with flashcards." }
    ],
    color: "#9a2540",
    icon: <Award size={20} style={{ color: "#9a2540" }} />
  }
];

function IssueCard({ issue }: { issue: Issue }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="issue-card" style={{
      borderRadius: "var(--radius-lg)",
      border: "1px solid var(--border)",
      background: "var(--card)",
      overflow: "hidden",
      transition: "border-color 0.2s"
    }}>
      <button className="issue-trigger" aria-expanded={open} aria-controls={`issue-${issue.id}`}
        onClick={() => setOpen((p) => !p)}
        style={{
          width: "100%", textAlign: "left", background: "none", border: "none",
          padding: "1rem 1.25rem", cursor: "pointer", color: "inherit",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
          <div style={{
            width: "38px", height: "38px", borderRadius: "10px", flexShrink: 0,
            background: `${issue.color}15`, border: `1px solid ${issue.color}35`,
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            {issue.icon}
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "#154f67" }}>{issue.title}</div>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-2)", marginTop: "0.15rem" }}>{issue.tagline}</div>
          </div>
        </div>
        <div style={{
          color: "var(--text-3)", flexShrink: 0,
          transform: open ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 0.2s ease"
        }}>
          <ChevronDown size={18} />
        </div>
      </button>

      {open && (
        <div id={`issue-${issue.id}`} style={{ padding: "0 1.25rem 1.25rem", display: "flex", flexDirection: "column", gap: "1rem", borderTop: "1px solid var(--border)" }}>
          {/* Why it matters */}
          <div style={{ padding: "0.75rem 1rem", borderRadius: "var(--radius-md)", background: `${issue.color}10`, border: `1px solid ${issue.color}25`, marginTop: "1rem" }}>
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: issue.color, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.3rem" }}>Why it matters</div>
            <div style={{ fontSize: "0.875rem", color: "var(--text-1)", lineHeight: 1.55 }}>{issue.why}</div>
          </div>

          {/* Signs */}
          <div>
            <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-2)", marginBottom: "0.4rem" }}>Signs you have this issue</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              {issue.signs.map((s, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.45rem", fontSize: "0.8125rem", color: "var(--text-1)" }}>
                  <CheckCircle2 size={13} style={{ color: issue.color, marginTop: "0.2rem", flexShrink: 0 }} />
                  <span>{s}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Drills */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-2)", marginBottom: "0.6rem" }}>
              <Dumbbell size={14} />
              <span>Practice Drills</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {issue.drills.map((d, i) => (
                <div key={i} style={{ padding: "0.75rem 1rem", borderRadius: "var(--radius-md)", background: "#ffffff", border: "1px solid var(--border)" }}>
                  <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "#154f67", marginBottom: "0.25rem" }}>
                    {i + 1}. {d.title}
                  </div>
                  <div style={{ fontSize: "0.8125rem", color: "var(--text-2)", lineHeight: 1.55 }}>{d.steps}</div>
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
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="page-heading">
        <h1>Speech Support</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9375rem" }}>
          Targeted exercises and drills for the most common communication issues.
        </p>
      </div>

      {/* Quick tip banner */}
      <div style={{
        padding: "0.875rem 1.25rem", borderRadius: "var(--radius-md)",
        background: "linear-gradient(135deg, rgba(41,110,145,0.12), rgba(40,92,59,0.08))",
        border: "1px solid rgba(41,110,145,0.2)",
        fontSize: "0.875rem", color: "var(--text-1)",
        display: "flex", alignItems: "flex-start", gap: "0.6rem"
      }}>
        <Lightbulb size={18} style={{ color: "var(--accent)", flexShrink: 0, marginTop: "0.15rem" }} />
        <div>
          <strong>How to use this:</strong> Identify your top issue from the{" "}
          <Link href="/roadmap" style={{ color: "var(--accent)", fontWeight: 600, textDecoration: "underline" }}>
            Roadmap page
          </Link>
          , then find it below. Do one drill per day for a week before your next practice session.
        </div>
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
