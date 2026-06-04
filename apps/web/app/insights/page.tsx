"use client";

import { useEffect, useState } from "react";
import { getSession } from "../../lib/api";
import Link from "next/link";

const SCENARIO_LABELS: Record<string, string> = {
  INTERVIEW: "Interview",
  PITCH: "Pitch",
  MEETING: "Meeting"
};

const DONE_STATUSES = new Set(["READY", "FAILED"]);

function RadialScore({ value, label, size = 120 }: { value: number; label: string; size?: number }) {
  const r = size * 0.4;
  const circ = 2 * Math.PI * r;
  const fill = circ * (1 - value);
  const strokeWidth = size * 0.08;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem" }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--primary)"
            strokeWidth={strokeWidth}
            strokeDasharray={circ}
            strokeDashoffset={fill}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
          />
        </svg>
        <div style={{
          position: "absolute", top: 0, left: 0, width: "100%", height: "100%",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: `${size * 0.2}px`, fontWeight: 800, color: "var(--text-1)"
        }}>
          {Math.round(value * 100)}%
        </div>
      </div>
      <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-2)" }}>{label}</span>
    </div>
  );
}

export default function InsightsPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [hasReadUrl, setHasReadUrl] = useState(false);
  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    setSessionId(sp.get("sessionId"));
    setHasReadUrl(true);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let alive = true;
    let intervalId: any = null;

    const load = async () => {
      try {
        const res = await getSession(sessionId);
        if (!alive) return;
        setData(res.session);
        if (DONE_STATUSES.has(res.session?.status) && intervalId !== null) {
          clearInterval(intervalId);
          intervalId = null;
        }
      } catch {
        if (!alive) return;
        setError("Failed to load session.");
        if (intervalId !== null) clearInterval(intervalId);
      }
    };

    load();
    intervalId = setInterval(load, 2500);
    return () => {
      alive = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [sessionId]);

  if (!hasReadUrl) return <div className="text-sm text-white/60">Loading...</div>;
  if (!sessionId) return <div className="text-sm text-white/60">Missing sessionId.</div>;
  if (error) return <div className="text-sm text-white/60">{error}</div>;
  if (!data) return <div className="text-sm text-white/60">Loading session data...</div>;

  const analysis = data.analysis;

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      {/* Header */}
      <div className="card-glow" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1.5rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
            <span className={`badge badge-indigo`}>{SCENARIO_LABELS[data.scenario] || data.scenario}</span>
            <span className={`badge ${data.status === "READY" ? "badge-emerald" : "badge-amber"}`}>{data.status}</span>
          </div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: 0 }}>{data.title || "Practice Session"}</h1>
          <p style={{ color: "var(--text-2)", marginTop: "0.4rem", fontSize: "0.9rem" }}>
            {new Date(data.createdAt).toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })}
          </p>
        </div>
        {analysis?.confidence != null && (
          <RadialScore value={analysis.confidence} label="Overall Confidence" size={140} />
        )}
      </div>

      {data.status === "ANALYZING" && (
        <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
          <div className="animate-live" style={{ fontSize: "2rem", marginBottom: "1rem" }}>⚙️</div>
          <h3 style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Analyzing your performance...</h3>
          <p style={{ color: "var(--text-3)", fontSize: "0.875rem" }}>This will take about 30-60 seconds. Insights will appear automatically.</p>
        </div>
      )}

      {analysis && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Main Metrics */}
          <div className="card">
            <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1.25rem" }}>Performance Breakdown</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "1.25rem" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--primary-lt)" }}>
                  {analysis.speechMetrics?.score != null ? `${Math.round(analysis.speechMetrics.score * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.25rem" }}>Speech</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--violet)" }}>
                  {analysis.nlpMetrics?.score != null ? `${Math.round(analysis.nlpMetrics.score * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.25rem" }}>Language</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--emerald)" }}>
                  {analysis.alignment?.score != null ? `${Math.round(analysis.alignment.score * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.25rem" }}>Alignment</div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--amber)" }}>
                  {analysis.confidence != null ? `${Math.round(analysis.confidence * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.25rem" }}>Overall</div>
              </div>
            </div>
          </div>

          {/* Strengths & Weaknesses */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "1.5rem" }}>
            <div className="card" style={{ borderLeft: "4px solid var(--emerald)" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.25rem" }}>🌟</span> Key Strengths
              </h3>
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.75rem", padding: 0, listStyle: "none" }}>
                {(analysis.strengths || []).map((s: string, i: number) => (
                  <li key={i} style={{ fontSize: "0.875rem", color: "var(--text-2)", display: "flex", gap: "0.6rem" }}>
                    <span style={{ color: "var(--emerald)" }}>✓</span> {s}
                  </li>
                ))}
              </ul>
            </div>
            <div className="card" style={{ borderLeft: "4px solid var(--amber)" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.25rem" }}>🎯</span> Focus Areas
              </h3>
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.75rem", padding: 0, listStyle: "none" }}>
                {(analysis.weaknesses || []).map((s: string, i: number) => (
                  <li key={i} style={{ fontSize: "0.875rem", color: "var(--text-2)", display: "flex", gap: "0.6rem" }}>
                    <span style={{ color: "var(--amber)" }}>!</span> {s}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Detailed Suggestions */}
          <div className="card">
            <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1rem" }}>Coaching Suggestions</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {(analysis.suggestions || []).concat(analysis.alignment?.notes || []).map((s: string, i: number) => (
                <div key={i} style={{
                  padding: "0.85rem 1rem", borderRadius: "var(--radius-md)",
                  background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)",
                  fontSize: "0.875rem", color: "var(--text-2)", lineHeight: 1.5
                }}>
                  💡 {s}
                </div>
              ))}
            </div>
          </div>

          {/* Transcript Highlights */}
          {(analysis.highlights || []).length > 0 && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1rem" }}>Key Moments</h3>
              <div style={{ display: "grid", gap: "0.75rem" }}>
                {analysis.highlights.map((item: any, i: number) => (
                  <div key={i} className="bubble-ai" style={{ padding: "1rem", fontSize: "0.875rem", borderLeft: "4px solid var(--primary)" }}>
                    <div style={{ fontSize: "0.7rem", color: "var(--text-3)", fontWeight: 700, marginBottom: "0.4rem", textTransform: "uppercase" }}>Moment {i + 1}</div>
                    {item.message || String(item)}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Job Recommendations */}
          {(analysis.jobs || []).length > 0 && (
            <div className="card" style={{ borderTop: "4px solid #0077b5" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.25rem" }}>💼</span> Recommended Jobs
              </h3>
              <p style={{ fontSize: "0.875rem", color: "var(--text-3)", marginBottom: "1.25rem" }}>
                Based on your interview performance, here are some roles that match your skills.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
                {analysis.jobs.map((job: any, i: number) => (
                  <div key={i} style={{
                    padding: "1.25rem", borderRadius: "var(--radius-md)",
                    background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)",
                    display: "flex", flexDirection: "column", gap: "0.75rem", position: "relative",
                    overflow: "hidden"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <h4 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-1)", margin: 0, paddingRight: "3rem" }}>
                        {job.role}
                      </h4>
                      <div style={{ 
                        position: "absolute", top: "1.25rem", right: "1.25rem",
                        fontSize: "0.8rem", fontWeight: 800, 
                        color: job.match >= 80 ? "var(--emerald)" : "var(--primary-lt)",
                        background: job.match >= 80 ? "rgba(16, 185, 129, 0.1)" : "rgba(59, 130, 246, 0.1)",
                        padding: "0.2rem 0.5rem", borderRadius: "1rem"
                      }}>
                        {job.match}% Match
                      </div>
                    </div>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-2)", margin: 0, lineHeight: 1.5, flexGrow: 1 }}>
                      {job.explanation}
                    </p>
                    <a href={job.url} target="_blank" rel="noopener noreferrer" style={{
                      display: "inline-block", marginTop: "0.5rem", padding: "0.5rem 1rem",
                      background: "#0077b5", color: "white", fontSize: "0.85rem", fontWeight: 600,
                      borderRadius: "0.3rem", textDecoration: "none", textAlign: "center",
                      transition: "opacity 0.2s"
                    }} onMouseOver={(e) => e.currentTarget.style.opacity = "0.9"} onMouseOut={(e) => e.currentTarget.style.opacity = "1"}>
                      Search on LinkedIn
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Full Transcript */}
      <div className="card">
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1.5rem" }}>Full Transcript</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {(data.segments || []).map((t: any) => (
            <div key={t.id} style={{ display: "flex", flexDirection: "column", gap: "0.4rem", alignSelf: t.speaker === "user" ? "flex-end" : "flex-start", maxWidth: "85%" }}>
              <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-3)", alignSelf: t.speaker === "user" ? "flex-end" : "flex-start", padding: "0 0.5rem" }}>
                {t.speaker === "ai" ? "COACH" : "YOU"}
              </div>
              <div className={t.speaker === "user" ? "bubble-user" : "bubble-ai"} style={{ padding: "0.85rem 1.1rem", fontSize: "0.9rem" }}>
                {t.text}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer Navigation */}
      <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginTop: "1rem" }}>
        <Link href="/history" className="btn btn-ghost">← Back to History</Link>
        <Link href="/session" className="btn btn-primary">Start New Session</Link>
      </div>
    </div>
  );
}
