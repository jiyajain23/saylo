export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:5000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {})
    },
    cache: "no-store"
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as T;
}

export type Scenario = "INTERVIEW" | "PITCH" | "MEETING";

export type SessionListItem = {
  id: string;
  createdAt: string;
  updatedAt: string;
  status: "LIVE" | "ENDED" | "ANALYZING" | "READY" | "FAILED";
  scenario: Scenario;
  title?: string | null;
};

export async function listSessions() {
  return req<{ sessions: SessionListItem[] }>("/sessions");
}

export async function getProgress() {
  return req<{
    totalSessions: number;
    analyzedSessions: number;
    avgConfidence: number | null;
    confidenceTrend: Array<{
      sessionId: string;
      title?: string | null;
      scenario: Scenario;
      createdAt: string;
      confidence: number | null;
    }>;
    skillTrend: Array<{
      sessionId: string;
      title?: string | null;
      scenario: Scenario;
      createdAt: string;
      confidence: number | null;
      clarity: number | null;
      structure: number | null;
      relevance: number | null;
      speechScore: number | null;
    }>;
    repeatedIssues: Array<{ issue: string; count: number }>;
    byScenario: Array<{ scenario: Scenario; sessions: number; analyzed: number; avgConfidence: number | null }>;
  }>("/sessions/progress");
}

export async function createSession(input: {
  scenario: Scenario;
  persona?: string;
  pressureLevel?: number;
  title?: string;
  resumeText?: string;
  jobDescription?: string;
  topicNotes?: string;
  freeText?: string;
}) {
  return req<{ session: { id: string } }>("/sessions", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function getSession(id: string) {
  return req<{ session: any }>(`/sessions/${id}`);
}

export async function endSession(id: string) {
  return req<{ ok: true }>(`/sessions/${id}/end`, { method: "POST", body: JSON.stringify({}) });
}

