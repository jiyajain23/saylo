"use client";

import Link from "next/link";
import { useState } from "react";
import type { SessionListItem } from "@/lib/api";
import {
  Briefcase,
  Presentation,
  Users,
  Inbox,
  ArrowRight,
  Calendar,
  Clock,
  Filter
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
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Filter bar */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "0.5rem 0.75rem", alignItems: "center",
        padding: "0.75rem 1rem", background: "rgba(255, 255, 255, 0.75)",
        border: "1px solid var(--border)", borderRadius: "var(--radius-md)"
      }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8125rem", color: "var(--text-2)", fontWeight: 600 }}>
          <Filter size={13} />
          <span>Scenario:</span>
        </div>
        {(["ALL", "INTERVIEW", "PITCH", "MEETING"] as FilterScenario[]).map((s) => (
          <button key={s} aria-pressed={scenarioFilter === s} onClick={() => setScenarioFilter(s)}
            className="btn btn-ghost filter-button"
            style={{ padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}>
            {s !== "ALL" && SCENARIO_ICON[s]}
            <span>{s === "ALL" ? "All" : SCENARIO_LABEL[s]}</span>
          </button>
        ))}

        <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8125rem", color: "var(--text-2)", fontWeight: 600, marginLeft: "0.5rem" }}>
          <span>Status:</span>
        </div>
        {(["ALL", "READY", "ANALYZING", "FAILED"] as FilterStatus[]).map((s) => (
          <button key={s} aria-pressed={statusFilter === s} onClick={() => setStatusFilter(s)}
            className="btn btn-ghost filter-button"
            style={{ padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}>
            <span>{s === "ALL" ? "All" : s}</span>
          </button>
        ))}

        <span style={{ fontSize: "0.8125rem", color: "var(--text-3)", marginLeft: "auto", fontWeight: 500 }}>
          {filtered.length} session{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Cards */}
      {filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem 0", color: "var(--text-3)" }}>
          <div style={{ width: "3.5rem", height: "3.5rem", borderRadius: "50%", background: "rgba(41, 110, 145, 0.1)", display: "grid", placeItems: "center", margin: "0 auto 0.75rem" }}>
            <Inbox size={26} style={{ color: "var(--muted)" }} />
          </div>
          <p style={{ fontWeight: 600, color: "var(--ink)" }}>No sessions match your filters</p>
          <p style={{ fontSize: "0.8125rem", color: "var(--muted)", marginTop: "0.25rem" }}>Try adjusting your filters or start a new practice session</p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 300px), 1fr))", gap: "1rem" }}>
          {filtered.map((s) => (
            <Link key={s.id} href={`/insights?sessionId=${encodeURIComponent(s.id)}`} style={{ textDecoration: "none" }}>
              <div className="card" style={{
                cursor: "pointer", height: "100%", display: "flex", flexDirection: "column",
                transition: "all 0.15s ease"
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className={`badge ${SCENARIO_COLOR[s.scenario]}`}>
                    {SCENARIO_ICON[s.scenario]}
                    <span>{SCENARIO_LABEL[s.scenario]}</span>
                  </span>
                  <span className={`badge ${s.status === "READY" ? "badge-emerald" : s.status === "FAILED" ? "badge-rose" : "badge-slate"}`}>
                    {s.status}
                  </span>
                </div>
                <div style={{ marginTop: "0.75rem", fontWeight: 700, fontSize: "0.9375rem", color: "#154f67", flex: 1 }}>
                  {s.title || `${SCENARIO_LABEL[s.scenario]} session`}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-3)" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                    <Calendar size={11} />
                    {new Date(s.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                  <span>·</span>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                    <Clock size={11} />
                    {new Date(s.createdAt).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", marginTop: "0.75rem", fontSize: "0.8125rem", fontWeight: 600, color: "var(--accent)" }}>
                  <span>View insights</span>
                  <ArrowRight size={13} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
