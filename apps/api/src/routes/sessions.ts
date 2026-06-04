import { Router } from "express";
import type { NextFunction, Request, Response } from "express";
import { z } from "zod";
import { Prisma } from "@prisma/client";
import { prisma } from "../db.js";
import { buildStructuredContext } from "../services/contextEngine.js";
import { runAnalysis } from "../services/analysisClient.js";
import { SCENARIOS, normalizeScenario, normalizePersona, normalizePressureLevel } from "../services/scenarios.js";
import { logger } from "../utils/logger.js";
import { audioBufferStore } from "../utils/audioStore.js";
import { SESSION_LIST_LIMIT } from "../utils/constants.js";

export const sessionsRouter = Router();

// ── Helpers ────────────────────────────────────────────────────────────────────

/**
 * Strip ASCII control characters (except tab/newline/carriage-return) from
 * a string to prevent prompt-injection or log-injection payloads.
 */
function sanitizeText(value: string): string {
  // eslint-disable-next-line no-control-regex
  return value.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "").trim();
}

/** Zod refinement: sanitize a string field in place. */
const safeText = (max: number) =>
  z
    .string()
    .trim()
    .max(max)
    .transform(sanitizeText);

// ── Routes ─────────────────────────────────────────────────────────────────────

sessionsRouter.get("/", async (_req, res, next) => {
  try {
    const sessions = await prisma.session.findMany({
      orderBy: { createdAt: "desc" },
      take: SESSION_LIST_LIMIT,
      select: {
        id: true,
        createdAt: true,
        updatedAt: true,
        status: true,
        scenario: true,
        title: true
      }
    });
    res.json({ sessions });
  } catch (e) {
    next(e);
  }
});

sessionsRouter.get("/progress", async (_req, res, next) => {
  try {
    const sessions = await prisma.session.findMany({
      orderBy: { createdAt: "asc" },
      include: { analysis: true }
    });

    const ready = sessions.filter((s) => s.analysis?.confidence != null);
    const confidenceTrend = ready.map((s) => ({
      sessionId: s.id,
      title: s.title,
      scenario: s.scenario,
      createdAt: s.createdAt,
      confidence: s.analysis?.confidence ?? null
    }));

    const issueCounts = new Map<string, number>();
    for (const s of ready) {
      const weaknesses = Array.isArray(s.analysis?.weaknesses) ? s.analysis.weaknesses : [];
      for (const w of weaknesses) {
        if (typeof w !== "string") continue;
        issueCounts.set(w, (issueCounts.get(w) ?? 0) + 1);
      }
    }

    const byScenario = SCENARIOS.map((scenario) => {
      const scenarioSessions = ready.filter((s) => s.scenario === scenario);
      const avgConfidence =
        scenarioSessions.reduce((sum, s) => sum + (s.analysis?.confidence ?? 0), 0) /
        Math.max(1, scenarioSessions.length);

      return {
        scenario,
        sessions: sessions.filter((s) => s.scenario === scenario).length,
        analyzed: scenarioSessions.length,
        avgConfidence: scenarioSessions.length ? Number(avgConfidence.toFixed(3)) : null
      };
    });

    // ── Per-skill trend for the Skill Progression Tracker ──────────────────
    const skillTrend = ready.slice(-20).map((s) => {
      const nlp = s.analysis?.nlpMetrics as Record<string, number> | null ?? {};
      const speech = s.analysis?.speechMetrics as Record<string, number> | null ?? {};
      return {
        sessionId: s.id,
        title: s.title,
        scenario: s.scenario,
        createdAt: s.createdAt,
        confidence: s.analysis?.confidence ?? null,
        clarity: nlp["clarity"] ?? null,
        structure: nlp["structure"] ?? null,
        relevance: nlp["relevance"] ?? null,
        speechScore: speech["score"] ?? null
      };
    });

    res.json({
      totalSessions: sessions.length,
      analyzedSessions: ready.length,
      avgConfidence: ready.length
        ? Number(
            (
              ready.reduce((sum, s) => sum + (s.analysis?.confidence ?? 0), 0) / ready.length
            ).toFixed(3)
          )
        : null,
      confidenceTrend,
      skillTrend,
      repeatedIssues: Array.from(issueCounts.entries())
        .map(([issue, count]) => ({ issue, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 5),
      byScenario
    });
  } catch (e) {
    next(e);
  }
});

sessionsRouter.post("/", async (req, res, next) => {
  try {
    const body = z
      .object({
        scenario: z.enum(SCENARIOS).default("INTERVIEW"),
        persona: z.string().optional().default("DEFAULT"),
        pressureLevel: z.number().int().min(0).max(3).optional().default(0),
        title: z.string().trim().min(1).max(120).optional().transform((v) => (v ? sanitizeText(v) : v)),
        contextText: safeText(30_000).optional(),
        resumeText: safeText(30_000).optional(),
        jobDescription: safeText(30_000).optional(),
        topicNotes: safeText(30_000).optional(),
        freeText: safeText(30_000).optional()
      })
      .parse(req.body);

    const context = buildStructuredContext({
      scenario: body.scenario,
      resumeText: body.resumeText,
      jobDescription: body.jobDescription,
      topicNotes: body.topicNotes,
      freeText: body.freeText || body.contextText
    });
    const hasContext = Boolean(context.contextRaw.trim());

    const session = await prisma.session.create({
      data: {
        scenario: normalizeScenario(body.scenario),
        persona: normalizePersona(body.persona),
        pressureLevel: normalizePressureLevel(body.pressureLevel),
        title: body.title,
        contextRaw: hasContext ? context.contextRaw : undefined,
        contextJson: hasContext ? (context.contextJson as object) : undefined
      },
      select: { id: true, status: true, scenario: true, createdAt: true, title: true, persona: true, pressureLevel: true }
    });

    res.status(201).json({ session });
  } catch (e) {
    next(e);
  }
});

sessionsRouter.get("/:id", async (req, res, next) => {
  try {
    const id = z.string().cuid().parse(req.params.id);
    const session = await prisma.session.findUnique({
      where: { id },
      include: {
        segments: { orderBy: { createdAt: "asc" } },
        analysis: true
      }
    });
    if (!session) return res.status(404).json({ error: "not_found" });
    res.json({ session });
  } catch (e) {
    next(e);
  }
});

sessionsRouter.post("/:id/segments", async (req, res, next) => {
  try {
    const id = z.string().cuid().parse(req.params.id);
    const body = z
      .object({
        speaker: z.enum(["user", "ai"]),
        text: safeText(4000).pipe(z.string().min(1))
      })
      .parse(req.body);

    const session = await prisma.session.findUnique({
      where: { id },
      select: { id: true }
    });
    if (!session) return res.status(404).json({ error: "not_found" });

    const seg = await prisma.transcriptSegment.create({
      data: { sessionId: id, speaker: body.speaker, text: body.text }
    });
    res.status(201).json({ segment: seg });
  } catch (e) {
    next(e);
  }
});

sessionsRouter.post("/:id/end", async (req, res, next) => {
  try {
    const id = z.string().cuid().parse(req.params.id);

    const session = await prisma.session.findUnique({
      where: { id },
      include: { segments: { orderBy: { createdAt: "asc" } } }
    });
    if (!session) return res.status(404).json({ error: "not_found" });

    await prisma.session.update({ where: { id }, data: { status: "ANALYZING" } });

    // Fire-and-forget: run analysis asynchronously so the HTTP response returns immediately.
    void (async () => {
      try {
        // ── Trim transcript for analysis to avoid overloading the service on long sessions ──
        // Cap per-segment text and limit total segments sent.
        const MAX_ANALYSIS_SEGMENTS = 120;  // ~15-20 minutes of conversation
        const MAX_SEGMENT_CHARS = 2000;     // guard against individual runaway turns
        const trimmedTranscript = session.segments
          .slice(-MAX_ANALYSIS_SEGMENTS)
          .map((s) => ({
            speaker: s.speaker,
            text: s.text.length > MAX_SEGMENT_CHARS ? s.text.slice(0, MAX_SEGMENT_CHARS) : s.text,
            ts: s.createdAt.toISOString()
          }));

        const result = await runAnalysis({
          scenario: session.scenario,
          context: (session.contextJson as Record<string, unknown>) ?? {},
          transcript: trimmedTranscript,
          audio_b64: audioBufferStore.pop(id)
        });

        // Prisma Json fields require InputJsonValue.
        // Casting through `as Prisma.InputJsonValue` is safe because our typed
        // structs are fully JSON-serialisable.
        const toJson = <T>(v: T): Prisma.InputJsonValue => v as unknown as Prisma.InputJsonValue;

        await prisma.analysisResult.upsert({
          where: { sessionId: id },
          create: {
            sessionId: id,
            speechMetrics: toJson(result.speech),
            nlpMetrics: toJson(result.nlp),
            alignment: toJson(result.alignment),
            confidence: result.confidence,
            highlights: toJson(result.insights.highlights),
            strengths: toJson(result.insights.strengths),
            weaknesses: toJson(result.insights.weaknesses),
            suggestions: toJson(result.insights.suggestions)
          },
          update: {
            speechMetrics: toJson(result.speech),
            nlpMetrics: toJson(result.nlp),
            alignment: toJson(result.alignment),
            confidence: result.confidence,
            highlights: toJson(result.insights.highlights),
            strengths: toJson(result.insights.strengths),
            weaknesses: toJson(result.insights.weaknesses),
            suggestions: toJson(result.insights.suggestions)
          }
        });

        await prisma.session.update({ where: { id }, data: { status: "READY" } });
        logger.info("[analysis] completed", { sessionId: id, confidence: result.confidence });
      } catch (e) {
        const errorDetails = e instanceof Error ? { message: e.message, stack: e.stack, name: e.name } : String(e);
        logger.error("[analysis] failed", { sessionId: id, error: errorDetails });
        await prisma.session.update({ where: { id }, data: { status: "FAILED" } }).catch(() => {});
      }
    })();

    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

// ── Route-level error handler ──────────────────────────────────────────────────

sessionsRouter.use((err: unknown, _req: Request, res: Response, next: NextFunction) => {
  if (err instanceof z.ZodError) {
    return res.status(400).json({
      error: "validation_failed",
      issues: err.issues.map((issue) => ({
        path: issue.path.join("."),
        message: issue.message
      }))
    });
  }
  return next(err);
});
