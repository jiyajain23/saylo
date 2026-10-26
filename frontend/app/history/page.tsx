import { PrivateHistory } from "@/components/PrivateDataViews";

export const metadata = { title: "Session History · saylo" };

export default function HistoryPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }} className="animate-fade-in">
      <div className="page-heading">
        <h1>Session History</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9375rem" }}>
          Review transcripts and insights from all your past practice sessions.
        </p>
      </div>
      <PrivateHistory />
    </div>
  );
}
