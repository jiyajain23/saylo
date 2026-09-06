import Link from "next/link";
import { getProgress, listSessions } from "../lib/api";
import type { SessionListItem } from "../lib/api";

const SCENARIO_COLOR: Record<string, string> = {
  INTERVIEW: "badge-indigo",
  PITCH: "badge-violet",
  MEETING: "badge-emerald"
};

const SCENARIO_LABEL: Record<string, string> = {
  INTERVIEW: "Interview",
  PITCH: "Pitch",
  MEETING: "Meeting"
};

/** Build a tiny SVG sparkline from an array of 0-1 values. */
function Sparkline({ values, color = "#53D8FB" }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const w = 180, h = 48;
  const max = Math.max(...values, 0.01);
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - (v / max) * (h - 4) - 2;
    return `${x},${y}`;
  });
  const lineD = `M${pts.join("L")}`;
  const areaD = `M${pts[0]}L${pts.join("L")}L${w},${h}L0,${h}Z`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill="url(#sg)" />
      <path d={lineD} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Compute a practice streak (consecutive days with at least one session). */
function computeStreak(sessions: SessionListItem[]): number {
  if (!sessions.length) return 0;
  const days = new Set(
    sessions.map((s) => new Date(s.createdAt).toISOString().slice(0, 10))
  );
  const sorted = Array.from(days).sort().reverse();
  let streak = 0;
  let cursor = new Date();
  cursor.setHours(0, 0, 0, 0);
  for (const day of sorted) {
    const d = new Date(day);
    const diff = Math.round((cursor.getTime() - d.getTime()) / 86400000);
    if (diff > 1) break;
    streak++;
    cursor = d;
  }
  return streak;
}

/** Radial ring for confidence score. */
function ConfidenceRing({ value }: { value: number }) {
  const r = 28, circ = 2 * Math.PI * r;
  const fill = circ * (1 - value);
  return (
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
      <circle
        cx="36" cy="36" r={r} fill="none"
        stroke="#6366f1" strokeWidth="5"
        strokeDasharray={`${circ}`}
        strokeDashoffset={fill}
        strokeLinecap="round"
        transform="rotate(-90 36 36)"
      />
      <text x="36" y="40" textAnchor="middle" fontSize="13" fontWeight="700" fill="#e2e8f0">
        {Math.round(value * 100)}%
      </text>
    </svg>
  );
}

export default async function DashboardPage() {
  const [{ sessions }, progress] = await Promise.all([
    listSessions().catch(() => ({ sessions: [] as SessionListItem[] })),
    getProgress().catch(() => null)
  ]);

  const streak = computeStreak(sessions);
  const lastSession = sessions[0] ?? null;
  const trendValues = (progress?.confidenceTrend ?? [])
    .filter((t) => t.confidence != null)
    .slice(-12)
    .map((t) => t.confidence as number);
  const topIssue = progress?.repeatedIssues?.[0] ?? null;

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 800, lineHeight: 1.2, margin: 0 }}>
            Welcome back...
          </h1>
          <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9rem" }}>
            {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
          </p>
        </div>
        <Link href="/session" className="btn btn-primary" style={{ fontSize: "0.9rem", padding: "0.6rem 1.25rem" }}>
          🎙 Start practice
        </Link>
      </div>

      {/* ── Top stat row ──────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "1rem" }}>
        {/* Streak */}
        <div className="stat-card" style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.1), var(--card))" }}>
          <div style={{ fontSize: "0.72rem", color: "var(--text-2)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>Practice Streak</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", marginTop: "0.5rem" }}>
            <span style={{ fontSize: "2rem", fontWeight: 800 }}>{streak}</span>
            <span style={{ color: "var(--text-2)", fontSize: "0.85rem" }}>days</span>
            {/* <span style={{ fontSize: "1.4rem" }}>{streak >= 3 ? "🔥" : streak >= 1 ? "✨" : ""}</span> */}
          </div>
          <div style={{ marginTop: "0.6rem" }}>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${Math.min(streak / 7 * 100, 100)}%`, background: "#f59e0b" }} />
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-3)", marginTop: "0.3rem" }}>
              {streak >= 7 ? "Week complete! 🏆" : `${7 - streak} days to weekly goal`}
            </div>
          </div>
        </div>

        {/* Total sessions */}
        <div className="stat-card">
          <div style={{ fontSize: "0.72rem", color: "var(--text-2)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>Total Sessions</div>
          <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.5rem" }}>
            {progress?.totalSessions ?? sessions.length}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.4rem" }}>
            {progress?.analyzedSessions ?? 0} analyzed
          </div>
        </div>

        {/* Avg confidence */}
        <div className="stat-card">
          <div style={{ fontSize: "0.72rem", color: "var(--text-2)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>Avg Confidence</div>
          <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.5rem", color: "#a5b4fc" }}>
            {progress?.avgConfidence != null ? `${Math.round(progress.avgConfidence * 100)}%` : "—"}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.4rem" }}>
            across all sessions
          </div>
        </div>

        {/* Last session */}
        <div className="stat-card">
          <div style={{ fontSize: "0.72rem", color: "var(--text-2)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>Last Session</div>
          {lastSession ? (
            <>
              <div style={{ fontSize: "0.95rem", fontWeight: 600, marginTop: "0.5rem" }}>
                {lastSession.title || SCENARIO_LABEL[lastSession.scenario]}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.3rem" }}>
                {new Date(lastSession.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </div>
            </>
          ) : (
            <div style={{ fontSize: "0.9rem", color: "var(--text-3)", marginTop: "0.5rem" }}>No sessions yet</div>
          )}
        </div>
      </div>

      {/* ── Confidence trend + Focus area ─────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        {/* Trend */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>Confidence Trend</h2>
            <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Last {trendValues.length} sessions</span>
          </div>
          {trendValues.length >= 2 ? (
            <Sparkline values={trendValues} />
          ) : (
            <div style={{ height: 48, display: "flex", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem", color: "var(--text-3)" }}>
                Complete 2+ sessions to see your trend
              </span>
            </div>
          )}
          {trendValues.length >= 2 && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem", fontSize: "0.72rem", color: "var(--text-3)" }}>
              <span>{`${Math.round((trendValues[0] ?? 0) * 100)}% start`}</span>
              <span>{`${Math.round((trendValues[trendValues.length - 1] ?? 0) * 100)}% latest`}</span>
            </div>
          )}
        </div>

        {/* Current focus area */}
        <div className="card-glow">
          <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1rem 0" }}>Current Focus Area</h2>
          {topIssue ? (
            <>
              <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#a5b4fc" }}>{topIssue.issue}</div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-2)", marginTop: "0.4rem" }}>
                Flagged {topIssue.count} time{topIssue.count !== 1 ? "s" : ""} across sessions
              </div>
              <div style={{ marginTop: "1rem" }}>
                <Link href="/roadmap" className="btn btn-ghost" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
                  View roadmap →
                </Link>
              </div>
            </>
          ) : (
            <div style={{ color: "var(--text-3)", fontSize: "0.875rem" }}>
              Complete 2+ analyzed sessions to get your focus area.
            </div>
          )}
        </div>
      </div>

      {/* ── Skills & Scenario breakdown ─────────────────────────────────────────────── */}
      {progress && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "1rem" }}>
          {/* Skill Tracker */}
          <div className="card">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>Skill Progression</h2>
            </div>
            
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              {[
                { label: "Clarity", color: "#38bdf8", key: "clarity" },
                { label: "Structure", color: "#a78bfa", key: "structure" },
                { label: "Relevance", color: "#f472b6", key: "relevance" },
                { label: "Speech Delivery", color: "#fbbf24", key: "speechScore" }
              ].map((skill) => {
                const vals = (progress.skillTrend || [])
                  .map(t => t[skill.key as keyof typeof t] as number | null)
                  .filter(v => v != null) as number[];
                const latest = vals.length > 0 ? vals[vals.length - 1]! : null;
                
                return (
                  <div key={skill.key}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
                      <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-2)" }}>{skill.label}</span>
                      <span style={{ fontSize: "0.85rem", fontWeight: 700, color: latest ? skill.color : "var(--text-3)" }}>
                        {latest ? `${Math.round(latest * 100)}%` : "—"}
                      </span>
                    </div>
                    {vals.length >= 2 ? (
                      <div style={{ height: "32px", overflow: "hidden", borderRadius: "var(--radius-sm)", opacity: 0.85 }}>
                         <Sparkline values={vals.slice(-10)} color={skill.color} />
                      </div>
                    ) : (
                      <div style={{ height: "32px", display: "flex", alignItems: "center", background: "rgba(255,255,255,0.02)", borderRadius: "var(--radius-sm)", padding: "0 0.5rem" }}>
                         <span style={{ fontSize: "0.7rem", color: "var(--text-4)" }}>Need 2+ sessions</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card">
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1.25rem 0" }}>Scenario Breakdown</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {progress.byScenario.map((item) => {
                const pct = item.avgConfidence != null ? Math.round(item.avgConfidence * 100) : null;
                const colorMap: Record<string, string> = { INTERVIEW: "#6366f1", PITCH: "#7c3aed", MEETING: "#10b981" };
                const col = colorMap[item.scenario] ?? "#6366f1";
                return (
                  <div key={item.scenario}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.35rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span className={`badge ${SCENARIO_COLOR[item.scenario]}`}>{SCENARIO_LABEL[item.scenario]}</span>
                        <span style={{ fontSize: "0.78rem", color: "var(--text-3)" }}>
                          {item.sessions} session{item.sessions !== 1 ? "s" : ""}
                        </span>
                      </div>
                      <span style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-1)" }}>
                        {pct != null ? `${pct}%` : "—"}
                      </span>
                    </div>
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${pct ?? 0}%`, background: col }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── Recent sessions ────────────────────────────────────────────────── */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 700, margin: 0 }}>Recent Sessions</h2>
          <Link href="/history" style={{ fontSize: "0.8rem", color: "var(--primary-lt)", textDecoration: "none" }}>
            View all →
          </Link>
        </div>
        {sessions.length === 0 ? (
          <div style={{ textAlign: "center", padding: "2rem 0", color: "var(--text-3)", fontSize: "0.9rem" }}>
            <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>🎙</div>
            No sessions yet. Start your first practice!
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {sessions.slice(0, 5).map((s) => (
              <Link
                key={s.id}
                href={`/insights?sessionId=${encodeURIComponent(s.id)}`}
                style={{ textDecoration: "none" }}
              >
                <div className="list-item-hover" style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "0.75rem 1rem",
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)",
                  transition: "all 0.15s", cursor: "pointer"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
                    <span className={`badge ${SCENARIO_COLOR[s.scenario]}`}>{SCENARIO_LABEL[s.scenario]}</span>
                    <span style={{ fontSize: "0.875rem", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.title || `${SCENARIO_LABEL[s.scenario]} session`}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexShrink: 0 }}>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-3)" }}>
                      {new Date(s.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </span>
                    <span className={`badge ${s.status === "READY" ? "badge-emerald" : s.status === "FAILED" ? "badge-rose" : "badge-slate"}`}>
                      {s.status}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
