import { getProgress } from "../../lib/api";

export const metadata = { title: "Improvement Roadmap – SpeakEZ" };

const ISSUE_TIPS: Record<string, {tip: string; drill: string; videoUrl?: string }> = {
  "filler words": { tip: "Pause intentionally instead of filling silence.", drill: "Read a paragraph aloud, pausing at every comma.", videoUrl: "https://www.youtube.com/watch?v=kYv_M_hX2i4" },
  "pace": {tip: "Target 130–160 words per minute. Record yourself and count.", drill: "Read text at 3 speeds: slow, normal, fast.", videoUrl: "https://www.youtube.com/watch?v=eIho2S0ZahI" },
  "eye contact": {tip: "Look at the camera lens, not your own preview.", drill: "Practice 5 seconds on camera, 4 seconds off, repeat.", videoUrl: "https://www.youtube.com/watch?v=8jEIqEdA8b4" },
  "posture": {tip: "Shoulders relaxed, chin level, sit 10cm back.", drill: "Sit against a wall for 5 minutes before each session.", videoUrl: "https://www.youtube.com/watch?v=Ks-_Mh1QhMc" },
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
  { id: "first",      label: "First Session",        emoji: "🚀", check: (n: number) => n >= 1 },
  { id: "three",      label: "3 Sessions",            emoji: "🎯", check: (n: number) => n >= 3 },
  { id: "ten",        label: "10 Sessions",           emoji: "🏅", check: (n: number) => n >= 10 },
  { id: "confidence", label: "Avg confidence > 70%", emoji: "⚡", check: (_: number, avg: number | null) => (avg ?? 0) >= 0.7 },
  { id: "allscenario",label: "Tried all 3 scenarios", emoji: "🌐", check: (_: number, __: number | null, all: boolean) => all }
];

function Sparkline({ values, color = "#6366f1" }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const w = 120, h = 36;
  const max = Math.max(...values, 0.01);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={`M${pts.join("L")}`} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default async function RoadmapPage() {
  const progress = await getProgress().catch(() => null);
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
      <div>
        <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: 0 }}>🗺 Improvement Roadmap</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9rem" }}>
          Your personalized path to confident, high-impact communication.
        </p>
      </div>

      {/* Milestones */}
      <div className="card">
        <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1.25rem" }}>🏆 Milestones</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem" }}>
          {MILESTONES.map((m) => {
            const done = m.check(totalSessions, avgConf, allScenarios);
            return (
              <div key={m.id} style={{
                padding: "0.85rem", borderRadius: "var(--radius-md)",
                border: `1px solid ${done ? "rgba(99,102,241,0.3)" : "var(--border)"}`,
                background: done ? "rgba(99,102,241,0.08)" : "rgba(255,255,255,0.01)",
                opacity: done ? 1 : 0.45
              }}>
                <div style={{ fontSize: "1rem" }}>{m.emoji}</div>
                <div style={{ fontSize: "0.9rem", fontWeight: 600, marginTop: "0.4rem", color: done ? "#0d2c94ff" : "var(--text-2)" }}>
                  {m.label}
                </div>
                {done && <div style={{ fontSize: "0.8rem", color: "#177851ff", marginTop: "0.2rem" }}>Achieved ✓</div>}
              </div>
            );
          })}
        </div>
      </div>

      {/* Focus areas */}
      <div className="card">
        <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1.25rem" }}>🎯 Ranked Focus Areas</h2>
        {issues.length === 0 ? (
          <p style={{ color: "var(--text-3)", fontSize: "0.875rem" }}>
            Complete 2+ analyzed sessions to unlock your personalized focus areas.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {issues.map((item, i) => {
              const info = getIssueTip(item.issue);
              return (
                <div key={item.issue} style={{
                  padding: "1rem 1.25rem", borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border)",
                  background: i === 0 ? "rgba(99,102,241,0.06)" : "rgba(255,255,255,0.01)"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                        {i === 0 && <span style={{ color: "#fc1a1aff" }}>Top Priority: </span>}
                        {item.issue}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>
                        Seen {item.count} time{item.count !== 1 ? "s" : ""} across sessions
                      </div>
                    </div>
                  </div>
                  <div style={{ marginTop: "0.85rem", padding: "0.85rem", borderRadius: "var(--radius-sm)", background: "rgba(244, 244, 244, 0.2)", fontSize: "0.8rem", color: "var(--text-2)", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                    <span><strong>Tip:</strong> {info.tip}</span>
                    <span><strong>Drill:</strong> {info.drill}</span>
                    {info.videoUrl && (
                      <span style={{ marginTop: "0.25rem" }}>
                        <strong>Watch:</strong> <a href={info.videoUrl} target="_blank" rel="noopener noreferrer" style={{ color: "#1b309eff", textDecoration: "underline" }}>Video Tutorial on YouTube</a>
                      </span>
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
        <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1.25rem" }}>📈 Scenario Trends</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "1rem" }}>
          {trendByScenario.map((item) => {
            const colorMap: Record<string, string> = { INTERVIEW: "#6366f1", PITCH: "#7c3aed", MEETING: "#10b981" };
            const col = colorMap[item.scenario] ?? "#6366f1";
            const vals = (progress?.confidenceTrend ?? [])
              .filter((t) => t.scenario === item.scenario && t.confidence != null)
              .map((t) => t.confidence as number);
            return (
              <div key={item.scenario} style={{ padding: "1rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{item.scenario}</span>
                  <span style={{ fontWeight: 700, color: col }}>{item.avgConfidence != null ? `${Math.round(item.avgConfidence * 100)}%` : "—"}</span>
                </div>
                <div style={{ marginTop: "0.75rem" }}>
                  {vals.length >= 2 ? <Sparkline values={vals} color={col} /> : <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Not enough data</span>}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-3)", marginTop: "0.4rem" }}>
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
            <div style={{ fontSize: "0.72rem", color: "var(--text-2)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>Next Session Recommendation</div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#a5b4fc", marginTop: "0.35rem" }}>Practice {nextRecommendation.scenario}</div>
            <div style={{ fontSize: "0.82rem", color: "var(--text-2)", marginTop: "0.2rem" }}>
              Weakest scenario — {nextRecommendation.avgConfidence != null ? `avg ${Math.round(nextRecommendation.avgConfidence * 100)}% confidence` : "no data yet"}.
            </div>
          </div>
          <a href="/session" className="btn btn-primary">Start session →</a>
        </div>
      )}
    </div>
  );
}
