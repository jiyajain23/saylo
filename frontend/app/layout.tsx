import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { NavActive } from "@/components/NavActive";

export const metadata: Metadata = {
  title: "SpeakEZ – Communication Coach",
  description: "AI-powered speech coaching for interviews, pitches, and meetings"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          {/* ── Sidebar (desktop) ──────────────────────────────────────────── */}
          <aside style={{
            width: "232px",
            flexShrink: 0,
            background: "var(--surface)",
            borderRight: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            padding: "1.5rem 1rem",
            position: "sticky",
            top: 0,
            height: "100vh",
            overflowY: "auto"
          }} className="sidebar-desktop">
            {/* Logo */}
            <Link href="/" style={{ textDecoration: "none", marginBottom: "2rem", display: "block" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                <div style={{
                  width: "32px", height: "32px", borderRadius: "10px",
                  background: "linear-gradient(135deg, var(--primary), var(--primary-lt))",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "16px", boxShadow: "0 0 20px rgba(83,216,251,0.3)"
                }}>🎤</div>
                <span style={{
                  fontWeight: 700, fontSize: "1.05rem",
                  background: "linear-gradient(135deg, var(--primary), var(--text-1))",
                  WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent"
                }}>SpeakEZ</span>
              </div>
            </Link>

            {/* Nav links */}
            <nav style={{ display: "flex", flexDirection: "column", gap: "0.25rem", flex: 1 }}>
              <NavActive href="/" exact label="Dashboard" icon="⊞" />
              <NavActive href="/session" label="Live Session" icon="🎙" />
              <NavActive href="/history" label="History" icon="📋" />
              <NavActive href="/roadmap" label="Roadmap" icon="🗺" />
              <NavActive href="/speech" label="Speech Support" icon="💬" />
            </nav>

            {/* Footer */}
            <div style={{ marginTop: "auto", paddingTop: "1rem", borderTop: "1px solid var(--border)" }}>
              <div style={{ fontSize: "0.7rem", color: "var(--text-3)", letterSpacing: "0.04em" }}>
                SPEAKEZ v0.1
              </div>
            </div>
          </aside>

          {/* ── Main content ───────────────────────────────────────────────── */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            {/* Mobile top bar */}
            <header className="mobile-header" style={{
              display: "none",
              padding: "0.75rem 1rem",
              borderBottom: "1px solid var(--border)",
              background: "rgba(255,255,255,0.9)",
              backdropFilter: "blur(12px)",
              position: "sticky", top: 0, zIndex: 10,
              alignItems: "center", justifyContent: "space-between"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div style={{
                  width: "28px", height: "28px", borderRadius: "8px",
                  background: "linear-gradient(135deg, #6366f1, #7c3aed)",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: "14px"
                }}>🎤</div>
                <span style={{
                  fontWeight: 700, fontSize: "0.95rem",
                  background: "linear-gradient(135deg, var(--primary), var(--text-1))",
                  WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent"
                }}>SpeakEZ</span>
              </div>
            </header>

            <main style={{ flex: 1, padding: "2rem", maxWidth: "1100px", width: "100%", margin: "0 auto" }}>
              {children}
            </main>

            {/* Mobile bottom nav */}
            <nav className="mobile-nav" style={{
              display: "none",
              borderTop: "1px solid var(--border)",
              background: "rgba(255,255,255,0.95)",
              backdropFilter: "blur(12px)",
              padding: "0.5rem 0",
              position: "sticky", bottom: 0, zIndex: 10
            }}>
              {[
                { href: "/",        icon: "⊞",  label: "Home" },
                { href: "/session", icon: "🎙", label: "Live" },
                { href: "/history", icon: "📋", label: "History" },
                { href: "/roadmap", icon: "🗺", label: "Roadmap" },
                { href: "/speech",  icon: "💬", label: "Speech" }
              ].map((item) => (
                <Link key={item.href} href={item.href} style={{
                  display: "flex", flexDirection: "column", alignItems: "center",
                  gap: "0.2rem", padding: "0.35rem 0.5rem", textDecoration: "none",
                  color: "var(--text-2)", fontSize: "0.65rem", fontWeight: 500, flex: 1
                }}>
                  <span style={{ fontSize: "1.2rem" }}>{item.icon}</span>
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </div>

        <style>{`
          @media (max-width: 768px) {
            .sidebar-desktop { display: none !important; }
            .mobile-header   { display: flex !important; }
            .mobile-nav      { display: flex !important; }
            main { padding: 1rem !important; }
          }
        `}</style>
      </body>
    </html>
  );
}
