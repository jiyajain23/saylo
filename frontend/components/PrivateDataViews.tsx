"use client";

import { useEffect, useState } from "react";
import { listSessions, getProgress, type SessionListItem } from "@/lib/api";
import { HistoryClient } from "./HistoryClient";
import { DashboardView } from "./DashboardView";
import { RoadmapView } from "./RoadmapView";
import { useAuth } from "./AuthProvider";

export function HomeDashboard() {
  const { session, loading } = useAuth();
  if (loading) return <div role="status" className="state-message">Loading…</div>;
  if (!session) return <DashboardView sessions={[]} progress={null} />;
  return <PrivateDashboard key={session.user.id} />;
}

export function PrivateRoadmap() {
  const [progress, setProgress] = useState<Awaited<ReturnType<typeof getProgress>> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void getProgress().then(result => { if (alive) setProgress(result); })
      .catch(() => { if (alive) setError("Could not load your roadmap. Please reload or sign in again."); });
    return () => { alive = false; };
  }, []);
  if (error) return <div role="alert" className="state-message">{error}</div>;
  if (!progress) return <div role="status" className="state-message">Loading your roadmap…</div>;
  return <RoadmapView progress={progress} />;
}

export function PrivateHistory() {
  const [sessions, setSessions] = useState<SessionListItem[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void listSessions().then(result => { if (alive) setSessions(result.sessions); })
      .catch(() => { if (alive) setError("Could not load your history. Please reload or sign in again."); });
    return () => { alive = false; };
  }, []);
  if (error) return <div role="alert" className="state-message">{error}</div>;
  if (!sessions) return <div role="status" className="state-message">Loading your history…</div>;
  return <HistoryClient sessions={sessions} />;
}

export function PrivateDashboard() {
  const [data, setData] = useState<{ sessions: SessionListItem[]; progress: Awaited<ReturnType<typeof getProgress>> } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void Promise.all([listSessions(), getProgress()]).then(([listing, progress]) => {
      if (alive) setData({ sessions: listing.sessions, progress });
    }).catch(() => { if (alive) setError("Could not load your dashboard. Please reload or sign in again."); });
    return () => { alive = false; };
  }, []);
  if (error) return <div role="alert" className="state-message">{error}</div>;
  if (!data) return <div role="status" className="state-message">Loading your dashboard…</div>;
  return <DashboardView sessions={data.sessions} progress={data.progress} />;
}
