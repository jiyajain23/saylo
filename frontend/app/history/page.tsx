import { listSessions } from "../../lib/api";
import { HistoryClient } from "@/components/HistoryClient";

export const metadata = { title: "Session History – SpeakEZ" };

export default async function HistoryPage() {
  const { sessions } = await listSessions().catch(() => ({ sessions: [] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }} className="animate-fade-in">
      <div>
        <h1 style={{ fontSize: "1.6rem", fontWeight: 800, margin: 0 }}>Session History</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9rem" }}>
          Review transcripts and insights from all your past practice sessions.
        </p>
      </div>
      <HistoryClient sessions={sessions} />
    </div>
  );
}
