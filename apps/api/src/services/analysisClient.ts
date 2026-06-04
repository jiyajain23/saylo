// ── Typed analysis result ──────────────────────────────────────────────────────

export interface SpeechHighlight {
  type: string;
  severity: "info" | "warn";
  message: string;
}

export interface SpeechMetrics {
  word_count: number;
  estimated_minutes: number;
  wpm_estimate: number;
  fillers: number;
  filler_per_100_words: number;
  avg_words_per_sentence: number;
  score: number;
  highlights: SpeechHighlight[];
}

export interface NlpMetrics {
  clarity: number;
  structure: number;
  relevance: number;
  score: number;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
}

export interface AlignmentMetrics {
  scenario: string;
  score: number;
  matchedSignals: string[];
  missingSignals: string[];
  notes: string[];
}

export interface AnalysisResponse {
  speech: SpeechMetrics;
  nlp: NlpMetrics;
  alignment: AlignmentMetrics;
  confidence: number;
  insights: {
    highlights: SpeechHighlight[];
    strengths: string[];
    weaknesses: string[];
    suggestions: string[];
  };
  jobs?: {
    role: string;
    match: number;
    explanation: string;
    url: string;
  }[];
}

// ── Client ─────────────────────────────────────────────────────────────────────

export async function runAnalysis(payload: {
  scenario: string;
  context: Record<string, unknown>;
  transcript: { speaker: string; text: string; ts?: string }[];
  audio_b64?: string | null;
}): Promise<AnalysisResponse> {
  const base = process.env.ANALYSIS_SERVICE_URL || "http://127.0.0.1:8000";
  const timeoutMs = Number(process.env.ANALYSIS_TIMEOUT_MS || 180_000);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${base}/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`analysis service failed: ${res.status} ${body}`);
    }
    return (await res.json()) as AnalysisResponse;
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error(`analysis service timed out after ${timeoutMs}ms`);
    }
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}
