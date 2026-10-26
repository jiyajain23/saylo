"use client";
import type { getProgress } from "@/lib/api";
import Link from "next/link";
import {
  Trophy,
  Target,
  Award,
  Zap,
  Sparkles,
  CheckCircle2,
  Circle,
  PlayCircle,
  ArrowRight,
  TrendingUp,
  Briefcase,
  Presentation,
  Users
} from "lucide-react";

const ISSUE_TIPS: Record<string, { tip: string; drill: string; videoUrl?: string }> = {
  "filler words": { tip: "Pause intentionally instead of filling silence.", drill: "Read a paragraph aloud, pausing at every comma.", videoUrl: "https://www.youtube.com/watch?v=kYv_M_hX2i4" },
  "pace": { tip: "Target 130–160 words per minute. Record yourself and count.", drill: "Read text at 3 speeds: slow, normal, fast.", videoUrl: "https://www.youtube.com/watch?v=eIho2S0ZahI" },
  "eye contact": { tip: "Look at the camera lens, not your own preview.", drill: "Practice 5 seconds on camera, 4 seconds off, repeat.", videoUrl: "https://www.youtube.com/watch?v=8jEIqEdA8b4" },
  "posture": { tip: "Shoulders relaxed, chin level, sit 10cm back.", drill: "Sit against a wall for 5 minutes before each session.", videoUrl: "https://www.youtube.com/watch?v=Ks-_Mh1QhMc" },
  "structure": { tip: "Use STAR (Situation, Task, Action, Result).", drill: "Tell a past experience in exactly 90 seconds using STAR.", videoUrl: "https://www.youtube.com/watch?v=8PjwO2bCvlQ" },
  "clarity": { tip: "Overarticulate consonants when nervous. Slow your opening.", drill: "Read tongue twisters for 2 minutes to warm up.", videoUrl: "https://www.youtube.com/watch?v=WPvGqX-TXP0" },
  "confidence": { tip: "Power pose 2 minutes before speaking.", drill: "Record a 60-second intro video each morning this week.", videoUrl: "https://www.youtube.com/watch?v=Ks-_Mh1QhMc" }
};

function getIssueTip(issue: string) {
  const lower = issue.toLowerCase();
  for (const key of Object.keys(ISSUE_TIPS)) {
    if (lower.includes(key)) return { key, ...ISSUE_TIPS[key] };
  }
  return { key: issue, tip: "Keep practicing to reduce this pattern.", drill: "Review your session transcripts for specific examples.", videoUrl: undefined };
}

const MILESTONES = [
  { id: "first",      label: "First Session",         check: (n: number) => n >= 1, icon: <Sparkles size={18} /> },
  { id: "three",      label: "3 Sessions",            check: (n: number) => n >= 3, icon: <Zap size={18} /> },
  { id: "ten",        label: "10 Sessions",           check: (n: number) => n >= 10, icon: <Trophy size={18} /> },
  { id: "confidence", label: "Avg confidence > 70%",  check: (_: number, avg: number | null) => (avg ?? 0) >= 0.7, icon: <Award size={18} /> },
  { id: "allscenario",label: "Tried all 3 scenarios", check: (_: number, __: number | null, all: boolean) => all, icon: <Target size={18} /> }
];

function Sparkline({ values, color = "#296e91" }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const w = 120, h = 36;
  const max = Math.max(...values, 0.01);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`);
  return (
    <svg className="chart" role="img" aria-label={`Confidence trend: ${values.map(v => `${Math.round(v * 100)}%`).join(", ")}`} width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={`M${pts.join("L")}`} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function RoadmapView({ progress }: { progress: Awaited<ReturnType<typeof getProgress>> }) {
  const totalSessions = progress?.totalSessions ?? 0;
  const avgConf = progress?.avgConfidence ?? null;
  const allScenarios = (progress?.byScenario ?? []).every((s) => s.sessions > 0);
  const issues = progress?.repeatedIssues ?? [];
  const trendByScenario = progress?.byScenario ?? [];
  const nextRecommendation = [...trendByScenario]
    .filter((s) => s.analyzed > 0)
    .sort((a, b) => (a.avgConfidence ?? 0) - (b.avgConfidence ?? 0))[0] ?? null;

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      <div className="page-heading">
        <h1>Improvement Roadmap</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9375rem" }}>
          Your personalized path to confident, high-impact communication.
        </p>
      </div>

      {/* Milestones */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
          <Trophy size={16} style={{ color: "var(--accent)" }} />
          <h2>Milestones</h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 180px), 1fr))", gap: "0.75rem" }}>
          {MILESTONES.map((m) => {
            const done = m.check(totalSessions, avgConf, allScenarios);
            return (
              <div key={m.id} style={{
                padding: "0.875rem 1rem", borderRadius: "var(--radius-md)",
                border: `1.5px solid ${done ? "rgba(40,92,59,0.35)" : "var(--border)"}`,
                background: done ? "linear-gradient(135deg, rgba(231,242,223,0.7), rgba(255,255,255,0.9))" : "rgba(255,255,255,0.7)",
                display: "flex", flexDirection: "column", gap: "0.4rem"
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ color: done ? "var(--success)" : "var(--muted)" }}>{m.icon}</div>
                  {done ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--success)" }}>
                      <CheckCircle2 size={13} />
                      <span>Done</span>
                    </span>
                  ) : (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem", color: "var(--muted)" }}>
                      <Circle size={12} />
                      <span>In progress</span>
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "0.875rem", fontWeight: 700, color: done ? "#154f67" : "var(--text-1)" }}>
                  {m.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Focus areas */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
          <Target size={16} style={{ color: "var(--accent)" }} />
          <h2>Ranked Focus Areas</h2>
        </div>
        {issues.length === 0 ? (
          <p style={{ color: "var(--text-3)", fontSize: "0.875rem" }}>
            Complete 2+ analyzed sessions to unlock your personalized focus areas.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            {issues.map((item, i) => {
              const info = getIssueTip(item.issue);
              return (
                <div key={item.issue} style={{
                  padding: "1rem 1.25rem", borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border)",
                  background: i === 0 ? "rgba(41,110,145,0.06)" : "rgba(255,255,255,0.6)"
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      {i === 0 && (
                        <span className="badge badge-rose" style={{ fontSize: "0.7rem" }}>Top Priority</span>
                      )}
                      <span style={{ fontWeight: 700, fontSize: "0.9375rem", color: "#154f67" }}>{item.issue}</span>
                    </div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>
                      Seen {item.count} time{item.count !== 1 ? "s" : ""} across sessions
                    </span>
                  </div>
                  <div style={{ marginTop: "0.75rem", padding: "0.75rem 1rem", borderRadius: "var(--radius-sm)", background: "rgba(255,255,255,0.8)", border: "1px solid var(--border)", fontSize: "0.875rem", color: "var(--ink)", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                    <div><strong>Tip:</strong> {info.tip}</div>
                    <div><strong>Drill:</strong> {info.drill}</div>
                    {info.videoUrl && (
                      <div style={{ marginTop: "0.25rem" }}>
                        <a href={info.videoUrl} target="_blank" rel="noopener noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", color: "var(--accent)", fontWeight: 600 }}>
                          <PlayCircle size={14} />
                          <span>Watch Video Tutorial on YouTube</span>
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Scenario trends */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
          <TrendingUp size={16} style={{ color: "var(--accent)" }} />
          <h2>Scenario Trends</h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 220px), 1fr))", gap: "1rem" }}>
          {trendByScenario.map((item) => {
            const colorMap: Record<string, string> = { INTERVIEW: "#296e91", PITCH: "#296e91", MEETING: "#285c3b" };
            const col = colorMap[item.scenario] ?? "#296e91";
            const iconMap: Record<string, React.ReactNode> = {
              INTERVIEW: <Briefcase size={14} />,
              PITCH: <Presentation size={14} />,
              MEETING: <Users size={14} />
            };
            const vals = (progress?.confidenceTrend ?? [])
              .filter((t) => t.scenario === item.scenario && t.confidence != null)
              .map((t) => t.confidence as number);
            return (
              <div key={item.scenario} style={{ padding: "0.875rem 1rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "rgba(255,255,255,0.6)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontWeight: 700, fontSize: "0.875rem", color: "var(--ink)" }}>
                    {iconMap[item.scenario]}
                    <span>{item.scenario}</span>
                  </span>
                  <span style={{ fontWeight: 800, color: col }}>{item.avgConfidence != null ? `${Math.round(item.avgConfidence * 100)}%` : "—"}</span>
                </div>
                <div style={{ marginTop: "0.6rem" }}>
                  {vals.length >= 2 ? <Sparkline values={vals} color={col} /> : <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Not enough data</span>}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-3)", marginTop: "0.4rem" }}>
                  {item.sessions} session{item.sessions !== 1 ? "s" : ""}, {item.analyzed} analyzed
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recommendation */}
      {nextRecommendation && (
        <div className="card-glow" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Next Session Recommendation
            </div>
            <div style={{ fontSize: "1.0625rem", fontWeight: 700, color: "#154f67", marginTop: "0.25rem" }}>
              Practice {nextRecommendation.scenario}
            </div>
            <div style={{ fontSize: "0.875rem", color: "var(--text-2)", marginTop: "0.2rem" }}>
              Weakest scenario — {nextRecommendation.avgConfidence != null ? `avg ${Math.round(nextRecommendation.avgConfidence * 100)}% confidence` : "no data yet"}.
            </div>
          </div>
          <Link href="/session" className="btn btn-primary">
            <span>Start session</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      )}
    </div>
  );
}
