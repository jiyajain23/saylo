import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { NavActive } from "@/components/NavActive";
import { LayoutDashboard, Video, History, TrendingUp, Sparkles } from "lucide-react";

export const metadata: Metadata = {
  title: "saylo – Communication Coach",
  description: "AI-powered speech coaching for interviews, pitches, and meetings"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="design">
      <body>
        <a href="#main-content" className="skip-link">Skip to content</a>
        <div className="app-shell">
          <header className="site-header">
            <Link href="/" className="brand" aria-label="saylo home">
              <span className="brand-mark" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" x2="12" y1="19" y2="22" />
                </svg>
              </span>
              <span>say<span className="brand-accent">lo</span></span>
            </Link>
            <nav className="main-nav" aria-label="Main navigation">
              <NavActive href="/dashboard" label="Dashboard" icon={<LayoutDashboard size={16} />} />
              <NavActive href="/session" label="Live Session" icon={<Video size={16} />} />
              <NavActive href="/history" label="History" icon={<History size={16} />} />
              <NavActive href="/roadmap" label="Roadmap" icon={<TrendingUp size={16} />} />
              <NavActive href="/speech" label="Speech Support" icon={<Sparkles size={16} />} />
            </nav>
          </header>
          <main id="main-content" tabIndex={-1}>{children}</main>
          <footer className="site-footer">
            <span className="footer-brand">saylo <span>•</span> A little practice. A clearer voice.</span>
            <span>Communication coach · v0.1</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
