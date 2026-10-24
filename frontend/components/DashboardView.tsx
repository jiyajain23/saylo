import Link from "next/link";
import type { SessionListItem } from "../lib/api";
import {
  ArrowRight,
  Flame,
  Layers,
  Award,
  Calendar,
  Target,
  Mic,
  Eye,
  Network,
  Volume2,
  Briefcase,
  Presentation,
  Users,
  TrendingUp
} from "lucide-react";

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

const SCENARIO_ICON: Record<string, React.ReactNode> = {
  INTERVIEW: <Briefcase size={12} />,
  PITCH: <Presentation size={12} />,
  MEETING: <Users size={12} />
};

function Sparkline({ values, color = "#296e91" }: { values: number[]; color?: string }) {
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
    <svg className="chart" role="img" aria-label={`Confidence trend: ${values.map(v => `${Math.round(v * 100)}%`).join(", ")}`} width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
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

export type ProgressData = {
  totalSessions: number;
  analyzedSessions: number;
  avgConfidence: number | null;
  confidenceTrend: Array<{
    sessionId: string;
    title?: string | null;
    scenario: "INTERVIEW" | "PITCH" | "MEETING";
    createdAt: string;
    confidence: number | null;
  }>;
  skillTrend: Array<{
    sessionId: string;
    title?: string | null;
    scenario: "INTERVIEW" | "PITCH" | "MEETING";
    createdAt: string;
    confidence: number | null;
    clarity: number | null;
    structure: number | null;
    relevance: number | null;
    speechScore: number | null;
  }>;
  repeatedIssues: Array<{ issue: string; count: number }>;
  byScenario: Array<{ scenario: "INTERVIEW" | "PITCH" | "MEETING"; sessions: number; analyzed: number; avgConfidence: number | null }>;
};

export function DashboardView({
  sessions,
  progress
}: {
  sessions: SessionListItem[];
  progress: ProgressData | null;
}) {
  const streak = computeStreak(sessions);
  const lastSession = sessions[0] ?? null;
  const trendValues = (progress?.confidenceTrend ?? [])
    .filter((t) => t.confidence != null)
    .slice(-12)
    .map((t) => t.confidence as number);
  const topIssue = progress?.repeatedIssues?.[0] ?? null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* ── Top stat row ──────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))", gap: "1rem" }}>
        {/* Streak */}
        <div className="stat-card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Practice Streak
            </span>
            <Flame size={15} style={{ color: "#735200" }} />
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", marginTop: "0.4rem" }}>
            <span style={{ fontSize: "1.875rem", fontWeight: 800, color: "#154f67" }}>{streak}</span>
            <span style={{ color: "var(--text-2)", fontSize: "0.875rem", fontWeight: 500 }}>days</span>
          </div>
          <div style={{ marginTop: "0.5rem" }}>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${Math.min(streak / 7 * 100, 100)}%`, background: "#735200" }} />
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-3)", marginTop: "0.3rem" }}>
              {streak >= 7 ? "Week complete!" : `${7 - streak} days to weekly goal`}
            </div>
          </div>
        </div>

        {/* Total sessions */}
        <div className="stat-card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Total Sessions
            </span>
            <Layers size={15} style={{ color: "var(--accent)" }} />
          </div>
          <div style={{ fontSize: "1.875rem", fontWeight: 800, marginTop: "0.4rem", color: "#154f67" }}>
            {progress?.totalSessions ?? sessions.length}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.4rem" }}>
            {progress?.analyzedSessions ?? 0} analyzed
          </div>
        </div>

        {/* Avg confidence */}
        <div className="stat-card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Avg Confidence
            </span>
            <Award size={15} style={{ color: "var(--accent)" }} />
          </div>
          <div style={{ fontSize: "1.875rem", fontWeight: 800, marginTop: "0.4rem", color: "var(--accent)" }}>
            {progress?.avgConfidence != null ? `${Math.round(progress.avgConfidence * 100)}%` : "—"}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.4rem" }}>
            across all sessions
          </div>
        </div>

        {/* Last session */}
        <div className="stat-card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-2)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Last Session
            </span>
            <Calendar size={15} style={{ color: "var(--muted)" }} />
          </div>
          {lastSession ? (
            <>
              <div style={{ fontSize: "0.9375rem", fontWeight: 600, marginTop: "0.4rem", color: "#154f67", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {lastSession.title || SCENARIO_LABEL[lastSession.scenario]}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-2)", marginTop: "0.3rem" }}>
                {new Date(lastSession.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </div>
            </>
          ) : (
            <div style={{ fontSize: "0.875rem", color: "var(--text-3)", marginTop: "0.5rem" }}>No sessions yet</div>
          )}
        </div>
      </div>

      {/* ── Confidence trend + Focus area ─────────────────────────────────── */}
      <div className="two-column">
        {/* Trend */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <TrendingUp size={15} style={{ color: "var(--accent)" }} />
              <h2 style={{ fontSize: "0.9375rem", fontWeight: 700 }}>Confidence Trend</h2>
            </div>
            <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Last {trendValues.length} sessions</span>
          </div>
          {trendValues.length >= 2 ? (
            <Sparkline values={trendValues} />
          ) : (
            <div style={{ height: 48, display: "flex", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-3)" }}>
                Complete 2+ sessions to see your trend
              </span>
            </div>
          )}
          {trendValues.length >= 2 && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-3)" }}>
              <span>{`${Math.round((trendValues[0] ?? 0) * 100)}% start`}</span>
              <span>{`${Math.round((trendValues[trendValues.length - 1] ?? 0) * 100)}% latest`}</span>
            </div>
          )}
        </div>

        {/* Current focus area */}
        <div className="card-glow" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem" }}>
              <Target size={15} style={{ color: "var(--accent)" }} />
              <h2 style={{ fontSize: "0.9375rem", fontWeight: 700 }}>Current Focus Area</h2>
            </div>
            {topIssue ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                <div style={{
                  padding: "0.5rem 0.75rem",
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(41, 110, 145, 0.08)",
                  borderLeft: "3px solid var(--accent)",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  color: "#154f67",
                  lineHeight: 1.4
                }}>
                  {topIssue.issue}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-3)", paddingLeft: "0.15rem" }}>
                  Flagged {topIssue.count} time{topIssue.count !== 1 ? "s" : ""} across sessions
                </div>
              </div>
            ) : (
              <div style={{ color: "var(--text-3)", fontSize: "0.8125rem" }}>
                Complete 2+ analyzed sessions to get your focus area.
              </div>
            )}
          </div>
          {topIssue && (
            <div style={{ marginTop: "0.75rem" }}>
              <Link href="/roadmap" className="btn btn-ghost" style={{ padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}>
                <span>View roadmap</span>
                <ArrowRight size={12} />
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* ── Skills & Scenario breakdown ─────────────────────────────────────────────── */}
      {progress && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: "1rem" }}>
          {/* Skill Tracker */}
          <div className="card">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
              <h2 style={{ fontSize: "0.9375rem", fontWeight: 700 }}>Skill Progression</h2>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              {[
                { label: "Clarity", color: "#38bdf8", key: "clarity", icon: <Eye size={13} style={{ color: "#38bdf8" }} /> },
                { label: "Structure", color: "#296e91", key: "structure", icon: <Network size={13} style={{ color: "#296e91" }} /> },
                { label: "Relevance", color: "#9a2540", key: "relevance", icon: <Target size={13} style={{ color: "#9a2540" }} /> },
                { label: "Speech Delivery", color: "#735200", key: "speechScore", icon: <Volume2 size={13} style={{ color: "#735200" }} /> }
              ].map((skill) => {
                const vals = (progress.skillTrend || [])
                  .map(t => t[skill.key as keyof typeof t] as number | null)
                  .filter(v => v != null) as number[];
                const latest = vals.length > 0 ? vals[vals.length - 1]! : null;

                return (
                  <div key={skill.key}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.2rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        {skill.icon}
                        <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-1)" }}>{skill.label}</span>
                      </div>
                      <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: latest ? skill.color : "var(--text-3)" }}>
                        {latest ? `${Math.round(latest * 100)}%` : "—"}
                      </span>
                    </div>
                    {vals.length >= 2 ? (
                      <div style={{ minHeight: "36px", borderRadius: "var(--radius-sm)" }}>
                        <Sparkline values={vals.slice(-10)} color={skill.color} />
                      </div>
                    ) : (
                      <div style={{ height: "26px", display: "flex", alignItems: "center", background: "rgba(255,255,255,0.4)", borderRadius: "var(--radius-sm)", padding: "0 0.5rem" }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Need 2+ sessions</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
                <h2 style={{ fontSize: "0.9375rem", fontWeight: 700 }}>Scenario Breakdown</h2>
                <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>Avg confidence</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {progress.byScenario.map((item) => {
                  const pct = item.avgConfidence != null ? Math.round(item.avgConfidence * 100) : null;
                  const colorMap: Record<string, string> = { INTERVIEW: "#296e91", PITCH: "#296e91", MEETING: "#285c3b" };
                  const col = colorMap[item.scenario] ?? "#296e91";
                  return (
                    <div key={item.scenario} style={{
                      padding: "0.5rem 0.65rem",
                      borderRadius: "var(--radius-sm)",
                      background: "rgba(255, 255, 255, 0.6)",
                      border: "1px solid var(--border)",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.3rem"
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          <span className={`badge ${SCENARIO_COLOR[item.scenario]}`} style={{ padding: "0.15rem 0.45rem", fontSize: "0.7rem" }}>
                            {SCENARIO_ICON[item.scenario]}
                            <span>{SCENARIO_LABEL[item.scenario]}</span>
                          </span>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>
                            {item.sessions} session{item.sessions !== 1 ? "s" : ""}
                          </span>
                        </div>
                        <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: pct != null ? col : "var(--text-3)" }}>
                          {pct != null ? `${pct}%` : "—"}
                        </span>
                      </div>
                      <div className="progress-track" style={{ height: "0.25rem" }}>
                        <div className="progress-fill" style={{ width: `${pct ?? 0}%`, background: col }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div style={{
              marginTop: "0.75rem",
              padding: "0.45rem 0.65rem",
              borderRadius: "var(--radius-sm)",
              background: "rgba(41, 110, 145, 0.05)",
              border: "1px dashed var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              fontSize: "0.75rem",
              color: "var(--text-2)"
            }}>
              <span>Weekly target: 70%+</span>
              <Link href="/session" style={{ color: "var(--accent)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "0.2rem" }}>
                <span>Practice</span>
                <ArrowRight size={11} />
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* ── Recent sessions ────────────────────────────────────────────────── */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
          <h2 style={{ fontSize: "0.9375rem", fontWeight: 700, margin: 0 }}>Recent Sessions</h2>
          <Link href="/history" className="btn btn-ghost" style={{ padding: "0.3rem 0.75rem", fontSize: "0.75rem" }}>
            <span>View all</span>
            <ArrowRight size={13} />
          </Link>
        </div>
        {sessions.length === 0 ? (
          <div style={{ textAlign: "center", padding: "2.5rem 0", color: "var(--text-3)" }}>
            <div style={{ width: "3rem", height: "3rem", borderRadius: "50%", background: "rgba(41, 110, 145, 0.1)", display: "grid", placeItems: "center", margin: "0 auto 0.75rem" }}>
              <Mic size={22} style={{ color: "var(--accent)" }} />
            </div>
            <p style={{ fontWeight: 600, color: "var(--ink)" }}>No sessions yet</p>
            <p style={{ fontSize: "0.8125rem", color: "var(--muted)", marginTop: "0.25rem" }}>Start your first practice session to get real-time feedback</p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {sessions.slice(0, 5).map((s) => (
              <Link
                key={s.id}
                href={`/insights?sessionId=${encodeURIComponent(s.id)}`}
                style={{ textDecoration: "none" }}
              >
                <div className="list-item-hover" style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "0.65rem 0.875rem",
                  background: "rgba(255,255,255,0.7)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)",
                  transition: "all 0.14s ease", cursor: "pointer"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
                    <span className={`badge ${SCENARIO_COLOR[s.scenario]}`}>
                      {SCENARIO_ICON[s.scenario]}
                      <span>{SCENARIO_LABEL[s.scenario]}</span>
                    </span>
                    <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.title || `${SCENARIO_LABEL[s.scenario]} session`}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexShrink: 0 }}>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-3)" }}>
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
