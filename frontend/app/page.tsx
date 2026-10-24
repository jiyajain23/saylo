import Link from "next/link";
import Image from "next/image";
import { getProgress, listSessions } from "@/lib/api";
import type { SessionListItem } from "@/lib/api";
import { DashboardView, type ProgressData } from "@/components/DashboardView";
import {
  CheckCircle2,
  ArrowRight,
  Sparkles,
  ChevronDown,
  LayoutDashboard,
  Briefcase,
  Presentation,
  Users
} from "lucide-react";

export const metadata = {
  title: "saylo – Communication Coach",
  description: "AI-powered speech coaching for interviews, pitches, and meetings"
};

export default async function HomePage() {
  const [{ sessions }, progress] = await Promise.all([
    listSessions().catch(() => ({ sessions: [] as SessionListItem[] })),
    getProgress().catch(() => null)
  ]);

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column" }}>
      {/* ── Big Full-Viewport Hero Section ─────────────────────────────────── */}
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">
            <Sparkles size={14} />
            <span>Your space to grow</span>
          </p>
          <h1 id="hero-title">
            Find your voice.<br />
            Build your confidence.
          </h1>
          <p className="hero-lead">
            A fresh start for every conversation. Practice interviews, pitches, and meetings with your AI communication coach.
          </p>
          <p style={{ color: "var(--ink)", fontSize: "0.875rem", opacity: 0.9 }}>
            Welcome back · {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
          </p>

          <div className="hero-meta">
            <span><CheckCircle2 size={16} style={{ color: "var(--success)" }} /> Practice at your pace</span>
            <span><CheckCircle2 size={16} style={{ color: "var(--success)" }} /> Learn with every session</span>
            <span><CheckCircle2 size={16} style={{ color: "var(--success)" }} /> Real-time cues</span>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.875rem", marginTop: "1rem" }}>
            <Link href="/session" className="btn btn-primary" style={{ padding: "0.75rem 1.75rem", fontSize: "0.9375rem" }}>
              <span>Start Live Session</span>
              <ArrowRight size={16} />
            </Link>
            <Link href="/dashboard" className="btn btn-ghost" style={{ padding: "0.75rem 1.5rem", fontSize: "0.9375rem" }}>
              <LayoutDashboard size={16} />
              <span>Open Dashboard</span>
            </Link>
          </div>
        </div>

        <div className="project-card">
          <Image
            src="/assets/clear-horizon.png"
            className="style-artwork"
            alt="Clear Horizon coaching art"
            width={1536}
            height={1024}
            sizes="(max-width: 960px) 100vw, 600px"
            priority
          />
          <h2>A little practice. A new perspective.</h2>
          <p>
            Step into a live session with thoughtful feedback on the way you speak, connect, and present yourself.
          </p>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1.25rem" }}>
            <Link href="/session" className="badge badge-indigo" style={{ padding: "0.35rem 0.65rem", fontSize: "0.75rem", textDecoration: "none" }}>
              <Briefcase size={12} />
              <span>Interview</span>
            </Link>
            <Link href="/session" className="badge badge-violet" style={{ padding: "0.35rem 0.65rem", fontSize: "0.75rem", textDecoration: "none" }}>
              <Presentation size={12} />
              <span>Pitch</span>
            </Link>
            <Link href="/session" className="badge badge-emerald" style={{ padding: "0.35rem 0.65rem", fontSize: "0.75rem", textDecoration: "none" }}>
              <Users size={12} />
              <span>Meeting</span>
            </Link>
          </div>

          <Link href="/session" className="btn btn-primary" style={{ width: "100%", justifyContent: "center", padding: "0.65rem 1.25rem" }}>
            <span>Start practice</span>
            <ArrowRight size={15} />
          </Link>
          <span className="workspace-footnote">Interviews · Pitches · Meetings</span>
        </div>
      </section>

      {/* ── Scroll Indicator ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "center", margin: "-1rem 0 2.5rem" }}>
        <a href="#dashboard-overview" style={{
          display: "inline-flex", flexDirection: "column", alignItems: "center", gap: "0.25rem",
          color: "var(--accent)", textDecoration: "none", padding: "0.5rem 1rem",
          borderRadius: "2rem", background: "rgba(255, 255, 255, 0.7)", border: "1px solid var(--border)",
          boxShadow: "0 2px 8px rgba(39, 115, 146, 0.1)", transition: "all 0.2s ease"
        }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Performance Overview
          </span>
          <ChevronDown size={16} />
        </a>
      </div>

      {/* ── Dashboard Metrics Below Scroll ─────────────────────────────────── */}
      <div id="dashboard-overview" style={{ scrollMarginTop: "2rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(116, 152, 166, 0.3)", paddingBottom: "0.75rem" }}>
          <div>
            <h2 style={{ fontSize: "1.125rem", fontWeight: 700 }}>Performance Overview</h2>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-3)", marginTop: "0.15rem" }}>
              Your latest communication metrics and practice analytics
            </p>
          </div>
          <Link href="/dashboard" className="btn btn-ghost" style={{ padding: "0.35rem 0.85rem", fontSize: "0.8125rem" }}>
            <LayoutDashboard size={14} />
            <span>Dedicated Dashboard</span>
          </Link>
        </div>

        <DashboardView sessions={sessions} progress={progress as ProgressData | null} />
      </div>
    </div>
  );
}
