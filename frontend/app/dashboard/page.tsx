import { PrivateDashboard } from "@/components/PrivateDataViews";

export const metadata = {
  title: "Dashboard · saylo",
  description: "Track your speaking progress, confidence trends, and skill milestones across sessions."
};

export default function DashboardPage() {
  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="page-heading">
        <h1>Dashboard Overview</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9375rem" }}>
          Track your speaking progress, confidence trends, and personalized focus areas across sessions.
        </p>
      </div>

      <PrivateDashboard />
    </div>
  );
}
