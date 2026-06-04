import cors from "cors";
import express from "express";
import rateLimit from "express-rate-limit";
import { sessionsRouter } from "./routes/sessions.js";
import { JSON_BODY_LIMIT, RATE_LIMIT_WINDOW_MS, RATE_LIMIT_CREATE_SESSION } from "./utils/constants.js";
import { logger } from "./utils/logger.js";

/**
 * Build and return the Express application.
 * Configures CORS, body parsing, rate limiting, and routes.
 */
export function createApp() {
  const app = express();

  // ── CORS ────────────────────────────────────────────────────────────────────
  // Parse allowed origins from env (comma-separated list), fall back to
  // localhost:3000 in development. In production, set ALLOWED_ORIGINS explicitly.
  const rawOrigins = process.env.ALLOWED_ORIGINS ?? "http://localhost:3000";
  const allowedOrigins = rawOrigins
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);

  app.use(
    cors({
      origin(origin, callback) {
        // Allow server-to-server requests (no Origin header) and whitelisted origins.
        if (!origin || allowedOrigins.includes(origin)) {
          callback(null, true);
        } else {
          logger.warn("[cors] rejected origin", { origin });
          callback(new Error("Not allowed by CORS"));
        }
      },
      methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
      allowedHeaders: ["Content-Type", "Authorization"],
      credentials: true
    })
  );

  // ── Body parsing ────────────────────────────────────────────────────────────
  app.use(express.json({ limit: JSON_BODY_LIMIT }));

  // ── Rate limiting ───────────────────────────────────────────────────────────
  // Global rate limit: generous ceiling to catch abuse, not normal usage.
  app.use(
    rateLimit({
      windowMs: RATE_LIMIT_WINDOW_MS,
      max: 300,
      standardHeaders: true,
      legacyHeaders: false,
      message: { error: "too_many_requests" }
    })
  );

  // Stricter limit on session creation (expensive: creates DB row + Gemini session).
  const sessionCreateLimiter = rateLimit({
    windowMs: RATE_LIMIT_WINDOW_MS,
    max: RATE_LIMIT_CREATE_SESSION,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: "too_many_sessions" }
  });

  // ── Routes ──────────────────────────────────────────────────────────────────
  app.get("/health", (_req, res) => res.json({ ok: true }));
  app.use("/sessions", sessionsRouter);
  app.post("/sessions", sessionCreateLimiter); // apply after router so it only targets POST

  // ── Global error handler ────────────────────────────────────────────────────
  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    logger.error("[app] unhandled error", err instanceof Error ? err.message : err);
    res.status(500).json({ error: "internal_server_error" });
  });

  return app;
}
