"use client";

import Link from "next/link";
import { useState } from "react";
import type { SessionListItem } from "@/lib/api";

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
type FilterScenario = "ALL" | "INTERVIEW" | "PITCH" | "MEETING";
type FilterStatus   = "ALL" | "READY" | "ANALYZING" | "FAILED";

export function HistoryClient({ sessions }: { sessions: SessionListItem[] }) {
  const [scenarioFilter, setScenarioFilter] = useState<FilterScenario>("ALL");
  const [statusFilter, setStatusFilter]     = useState<FilterStatus>("ALL");

  const filtered = sessions.filter((s) => {
    if (scenarioFilter !== "ALL" && s.scenario !== scenarioFilter) return false;
    if (statusFilter !== "ALL" && s.status !== statusFilter) return false;
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
        <span style={{ fontSize: "0.78rem", color: "var(--text-3)", marginRight: "0.25rem" }}>Scenario:</span>
        {(["ALL", "INTERVIEW", "PITCH", "MEETING"] as FilterScenario[]).map((s) => (
          <button key={s} onClick={() => setScenarioFilter(s)}
            className="btn btn-ghost"
            style={{ padding: "0.3rem 0.75rem", fontSize: "0.78rem",
              ...(scenarioFilter === s ? { background: "rgba(83,216,251,0.1)", color: "var(--primary)", borderColor: "rgba(83,216,251,0.25)" } : {}) }}>
            {s === "ALL" ? "All" : SCENARIO_LABEL[s]}
          </button>
        ))}
        <span style={{ fontSize: "0.78rem", color: "var(--text-3)", marginLeft: "0.5rem" }}>Status:</span>
        {(["ALL", "READY", "ANALYZING", "FAILED"] as FilterStatus[]).map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className="btn btn-ghost"
            style={{ padding: "0.3rem 0.75rem", fontSize: "0.78rem",
              ...(statusFilter === s ? { background: "rgba(83,216,251,0.1)", color: "var(--primary)", borderColor: "rgba(83,216,251,0.25)" } : {}) }}>
            {s === "ALL" ? "All" : s}
          </button>
        ))}
        <span style={{ fontSize: "0.78rem", color: "var(--text-3)", marginLeft: "auto" }}>
          {filtered.length} session{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Cards */}
      {filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem 0", color: "var(--text-3)" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>📭</div>
          No sessions match your filters.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1rem" }}>
          {filtered.map((s) => (
            <Link key={s.id} href={`/insights?sessionId=${encodeURIComponent(s.id)}`} style={{ textDecoration: "none" }}>
              <div style={{
                background: "var(--card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                padding: "1.25rem",
                cursor: "pointer", height: "100%",
                transition: "border-color 0.15s, transform 0.15s"
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--primary)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.transform = "translateY(0)"; }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <span className={`badge ${SCENARIO_COLOR[s.scenario]}`}>{SCENARIO_LABEL[s.scenario]}</span>
                  <span className={`badge ${s.status === "READY" ? "badge-emerald" : s.status === "FAILED" ? "badge-rose" : "badge-slate"}`}>
                    {s.status}
                  </span>
                </div>
                <div style={{ marginTop: "0.85rem", fontWeight: 600, fontSize: "0.95rem", color: "var(--text-1)" }}>
                  {s.title || `${SCENARIO_LABEL[s.scenario]} session`}
                </div>
                <div style={{ marginTop: "0.4rem", fontSize: "0.78rem", color: "var(--text-3)" }}>
                  {new Date(s.createdAt).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
                  {" · "}
                  {new Date(s.createdAt).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                </div>
                <div style={{ marginTop: "0.85rem", fontSize: "0.8rem", color: "var(--primary)" }}>
                  View insights →
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
