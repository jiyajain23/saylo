"use client";

import { useEffect, useState } from "react";
import { getSession, endSession } from "../../lib/api";
import Link from "next/link";
import {
  CheckCircle2,
  AlertTriangle,
  Briefcase,
  ExternalLink,
  ArrowLeft,
  RotateCcw,
  Sparkles,
  TrendingUp,
  MessageSquare,
  Award,
  Layers
} from "lucide-react";

const SCENARIO_LABELS: Record<string, string> = {
  INTERVIEW: "Interview",
  PITCH: "Pitch",
  MEETING: "Meeting"
};

const DONE_STATUSES = new Set(["READY", "FAILED"]);

// ─── LangGraph Pipeline Visualizer ────────────────────────────────────────────

const PIPELINE_STAGES = [
  ["speech", "Speech", "Measuring pace, pauses, fillers, and delivery."],
  ["nlp", "Language", "Scoring clarity, structure, and relevance."],
  ["alignment", "Alignment", "Checking scenario-specific answer signals."],
  ["voice", "Voice", "Analyzing vocal energy and confidence."],
  ["emotion", "Emotion", "Estimating emotional tone from the transcript."],
  ["vision", "Vision", "Reviewing available posture and eye-contact metrics."],
  ["aggregator", "Score", "Combining the measured dimensions."],
  ["insights", "Coaching", "Generating personalized feedback."],
  ["jobs", "Job Match", "Matching the session context to relevant roles."],
  ["template_store", "Finalize", "Saving the completed analysis."],
] as const;

function AnalysisPipeline({ progress }: { progress?: { events?: Array<{ stage: string; status: string; error?: string }> } | null }) {
  const latest = new Map((progress?.events ?? []).map(event => [event.stage, event]));
  const completed = PIPELINE_STAGES.filter(([id]) => latest.get(id)?.status === "completed").length;
  return (
    <section className="card analysis-loading" role="status" aria-live="polite">
      <h2>Analyzing your performance</h2>
      <p style={{ margin: "0.5rem auto 0", color: "var(--muted)", fontSize: "0.875rem" }}>
        {completed} of {PIPELINE_STAGES.length} stages complete. Parallel measurement stages may finish in any order.
      </p>
      <div className="analysis-stages" aria-label="Live analysis pipeline" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.65rem", marginTop: "1rem" }}>
        {PIPELINE_STAGES.map(([id, label, description]) => {
          const event = latest.get(id);
          const status = event?.status ?? "pending";
          const color = status === "completed" ? "var(--emerald)" : status === "running" ? "var(--accent)" : status === "failed" ? "#b54747" : "var(--muted)";
          return (
            <div key={id} aria-label={`${label}: ${status}`} style={{ border: `1px solid ${color}`, borderRadius: "var(--radius-md)", padding: "0.7rem", textAlign: "left", color, opacity: status === "pending" ? 0.65 : 1, boxShadow: status === "running" ? "0 0 16px rgba(41,110,145,.25)" : "none", transition: "all .25s ease" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700 }}>
                <span>{status === "completed" ? "✓ " : status === "failed" ? "! " : status === "running" ? "◌ " : "○ "}{label}</span>
                <span style={{ fontSize: "0.7rem", textTransform: "uppercase" }}>{status}</span>
              </div>
              <div style={{ marginTop: "0.3rem", color: "var(--muted)", fontSize: "0.72rem" }}>{event?.error || description}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RadialScore({ value, label, size = 110 }: { value: number; label: string; size?: number }) {
  const r = size * 0.38;
  const circ = 2 * Math.PI * r;
  const fill = circ * (1 - value);
  const strokeWidth = size * 0.08;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg role="img" aria-label={`${label}: ${Math.round(value * 100)}%`} width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="#dce8ec"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--accent)"
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
          fontSize: `${size * 0.22}px`, fontWeight: 800, color: "#154f67"
        }}>
          {Math.round(value * 100)}%
        </div>
      </div>
      <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-2)" }}>{label}</span>
    </div>
  );
}

export default function InsightsPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [hasReadUrl, setHasReadUrl] = useState(false);
  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    setSessionId(sp.get("sessionId"));
    setHasReadUrl(true);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let alive = true;
    let intervalId: ReturnType<typeof setTimeout> | null = null;

    const load = async () => {
      try {
        const res = await getSession(sessionId);
        if (!alive) return;
        setData(res.session);
        if (!DONE_STATUSES.has(res.session?.status)) {
          intervalId = setTimeout(load, 5000);
        }
      } catch {
        if (!alive) return;
        setError("Failed to load session.");
        if (intervalId !== null) clearTimeout(intervalId);
      }
    };

    load();
    return () => {
      alive = false;
      if (intervalId) clearTimeout(intervalId);
    };
  }, [sessionId]);

  if (!hasReadUrl) return <div className="state-message" role="status">Loading...</div>;
  if (!sessionId) return <div className="state-message" role="status">Missing sessionId.</div>;
  if (error) return <div className="state-message error-message" role="alert">{error}</div>;
  if (!data) return <div className="state-message" role="status">Loading session data...</div>;

  const analysis = data.analysis;

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header */}
      <div className="card-glow" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1.25rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
            <span className="badge badge-indigo">{SCENARIO_LABELS[data.scenario] || data.scenario}</span>
            <span className={`badge ${data.status === "READY" ? "badge-emerald" : "badge-amber"}`}>{data.status}</span>
          </div>
          <h1>{data.title || "Practice Session"}</h1>
          <p style={{ color: "var(--text-2)", marginTop: "0.25rem", fontSize: "0.875rem" }}>
            {new Date(data.createdAt).toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })}
          </p>
        </div>
        {analysis?.confidence != null && (
          <RadialScore value={analysis.confidence} label="Overall Confidence" size={110} />
        )}
      </div>

      {data.status === "ANALYZING" && <AnalysisPipeline progress={data.analysisJob?.progress} />}
      {data.analysisJob && data.status === "ANALYZING" && (
        <p role="status" style={{ color: "var(--muted)" }}>
          {data.analysisJob.status === "UPLOADING" ? "Saving private audio. Analysis starts after the upload is confirmed."
            : data.analysisJob.status === "QUEUED" ? "Queued for the analysis worker. You can leave this page and return later."
            : "The analysis worker is processing your session."}
          {data.analysisJob.errorCode && " A previous attempt failed; a bounded retry is pending."}
        </p>
      )}
      {data.status === "FAILED" && (
        <p role="alert">This session could not be completed ({data.failureCode || "analysis_failed"}).
          Your saved transcript remains available. No successful analysis is claimed.</p>
      )}
      {(data.status === "ENDED" || data.analysisJob?.status === "UPLOADING") && (
        <button className="btn btn-primary" disabled={retrying} onClick={async () => {
          setRetrying(true);
          try {
            await endSession(sessionId);
            setData((await getSession(sessionId)).session);
          } catch (error) {
            setError(error instanceof Error ? error.message : "Completion could not be retried.");
          } finally { setRetrying(false); }
        }}>{retrying ? "Saving session…" : "Retry End & Analyze"}</button>
      )}

      {analysis && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Main Metrics */}
          <div className="card">
            <h2 style={{ marginBottom: "1rem" }}>Performance Breakdown</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 140px), 1fr))", gap: "1rem" }}>
              <div style={{ textAlign: "center", padding: "0.75rem", background: "rgba(255,255,255,0.7)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: "1.625rem", fontWeight: 800, color: "var(--accent)" }}>
                  {analysis.speechMetrics?.score != null ? `${Math.round(analysis.speechMetrics.score * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.2rem" }}>Speech</div>
              </div>
              <div style={{ textAlign: "center", padding: "0.75rem", background: "rgba(255,255,255,0.7)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: "1.625rem", fontWeight: 800, color: "var(--accent)" }}>
                  {analysis.nlpMetrics?.score != null ? `${Math.round(analysis.nlpMetrics.score * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.2rem" }}>Language</div>
              </div>
              <div style={{ textAlign: "center", padding: "0.75rem", background: "rgba(255,255,255,0.7)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: "1.625rem", fontWeight: 800, color: "var(--emerald)" }}>
                  {analysis.alignment?.score != null ? `${Math.round(analysis.alignment.score * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.2rem" }}>Alignment</div>
              </div>
              <div style={{ textAlign: "center", padding: "0.75rem", background: "rgba(255,255,255,0.7)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: "1.625rem", fontWeight: 800, color: "#735200" }}>
                  {analysis.confidence != null ? `${Math.round(analysis.confidence * 100)}%` : "—"}
                </div>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", marginTop: "0.2rem" }}>Overall</div>
              </div>
            </div>
          </div>

          {/* Strengths & Weaknesses */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", gap: "1.25rem" }}>
            <div className="card" style={{ borderLeft: "4px solid var(--emerald)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", marginBottom: "0.75rem" }}>
                <CheckCircle2 size={16} style={{ color: "var(--emerald)" }} />
                <h3>Key Strengths</h3>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {(analysis.strengths || []).map((s: string, i: number) => (
                  <div key={i} style={{ fontSize: "0.875rem", color: "var(--ink)", display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                    <span style={{ color: "var(--emerald)", fontWeight: 800, flexShrink: 0 }}>•</span>
                    <span>{s}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card" style={{ borderLeft: "4px solid var(--amber)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", marginBottom: "0.75rem" }}>
                <AlertTriangle size={16} style={{ color: "var(--amber)" }} />
                <h3>Focus Areas</h3>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {(analysis.weaknesses || []).map((s: string, i: number) => (
                  <div key={i} style={{ fontSize: "0.875rem", color: "var(--ink)", display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                    <span style={{ color: "var(--amber)", fontWeight: 800, flexShrink: 0 }}>•</span>
                    <span>{s}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Detailed Suggestions */}
          <div className="card">
            <h3 style={{ marginBottom: "0.875rem" }}>Coaching Suggestions</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {(analysis.suggestions || []).concat(analysis.alignment?.notes || []).map((s: string, i: number) => (
                <div key={i} style={{
                  padding: "0.75rem 1rem", borderRadius: "var(--radius-md)",
                  background: "rgba(255,255,255,0.7)", border: "1px solid var(--border)",
                  fontSize: "0.875rem", color: "var(--ink)", lineHeight: 1.5,
                  display: "flex", gap: "0.75rem", alignItems: "flex-start"
                }}>
                  <span style={{ color: "var(--accent)", fontWeight: 700, flexShrink: 0, fontSize: "0.75rem", marginTop: "0.1rem" }}>{String(i + 1).padStart(2, "0")}</span>
                  <span>{s}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Transcript Highlights */}
          {(analysis.highlights || []).length > 0 && (
            <div className="card">
              <h3 style={{ marginBottom: "0.875rem" }}>Key Moments</h3>
              <div style={{ display: "grid", gap: "0.6rem" }}>
                {analysis.highlights.map((item: any, i: number) => (
                  <div key={i} className="bubble-ai" style={{ padding: "0.875rem 1rem", fontSize: "0.875rem", borderLeft: "4px solid var(--accent)" }}>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-3)", fontWeight: 700, marginBottom: "0.3rem", textTransform: "uppercase" }}>Moment {i + 1}</div>
                    {item.message || String(item)}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Job Recommendations */}
          {(analysis.jobs || []).length > 0 && (
            <div className="card" style={{ borderTop: "3px solid var(--accent)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
                <Briefcase size={16} style={{ color: "var(--accent)" }} />
                <h3>Recommended Jobs</h3>
              </div>
              <p style={{ fontSize: "0.875rem", color: "var(--text-3)", marginBottom: "1rem" }}>
                Based on your interview performance, here are some roles that match your skills.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: "0.875rem" }}>
                {analysis.jobs.map((job: any, i: number) => (
                  <div key={i} style={{
                    padding: "1rem 1.125rem", borderRadius: "var(--radius-md)",
                    background: "rgba(255,255,255,0.7)", border: "1px solid var(--border)",
                    display: "flex", flexDirection: "column", gap: "0.6rem"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <h4 style={{ fontSize: "0.9375rem", fontWeight: 700, color: "#154f67", margin: 0 }}>
                        {job.role}
                      </h4>
                      <div style={{
                        fontSize: "0.75rem", fontWeight: 800,
                        color: job.match >= 80 ? "var(--emerald)" : "var(--accent)",
                        background: job.match >= 80 ? "rgba(40, 92, 59, 0.1)" : "rgba(41, 110, 145, 0.1)",
                        padding: "0.15rem 0.45rem", borderRadius: "1rem", whiteSpace: "nowrap"
                      }}>
                        {job.match}% Match
                      </div>
                    </div>
                    <p style={{ fontSize: "0.8125rem", color: "var(--text-2)", margin: 0, lineHeight: 1.5, flexGrow: 1 }}>
                      {job.explanation}
                    </p>
                    <a className="btn btn-ghost" href={job.url} target="_blank" rel="noopener noreferrer" style={{
                      display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.35rem",
                      padding: "0.4rem 0.85rem", fontSize: "0.8125rem", fontWeight: 600
                    }}>
                      <span>Search on LinkedIn</span>
                      <ExternalLink size={12} />
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
        <h2 style={{ marginBottom: "1rem" }}>Full Transcript</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {(data.segments || []).map((t: any) => (
            <div key={t.id} style={{ display: "flex", flexDirection: "column", gap: "0.3rem", alignSelf: t.speaker === "user" ? "flex-end" : "flex-start", maxWidth: "85%" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-3)", alignSelf: t.speaker === "user" ? "flex-end" : "flex-start", padding: "0 0.25rem", textTransform: "uppercase" }}>
                {t.speaker === "ai" ? "Coach" : "You"}
              </div>
              <div className={t.speaker === "user" ? "bubble-user" : "bubble-ai"} style={{ padding: "0.75rem 1rem", fontSize: "0.9375rem", lineHeight: 1.55 }}>
                {t.text}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer Navigation */}
      <div className="action-row" style={{ display: "flex", justifyContent: "center", gap: "0.875rem", marginTop: "0.5rem" }}>
        <Link href="/history" className="btn btn-ghost">
          <ArrowLeft size={14} />
          <span>Back to History</span>
        </Link>
        <Link href="/session" className="btn btn-primary">
          <RotateCcw size={14} />
          <span>Start New Session</span>
        </Link>
      </div>
    </div>
  );
}
