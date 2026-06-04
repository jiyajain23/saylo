/**
 * Minimal structured logger.
 * Uses console under the hood so no extra dependencies are needed.
 * Log level is controlled by the LOG_LEVEL env var (debug | info | warn | error).
 */

type Level = "debug" | "info" | "warn" | "error";

const LEVELS: Record<Level, number> = { debug: 0, info: 1, warn: 2, error: 3 };

const configured = (process.env.LOG_LEVEL ?? "info") as Level;
const minLevel = LEVELS[configured] ?? LEVELS.info;

function log(level: Level, message: string, meta?: unknown) {
  if (LEVELS[level] < minLevel) return;

  const entry = {
    ts: new Date().toISOString(),
    level,
    message,
    ...(meta !== undefined ? { meta } : {})
  };

  const line = JSON.stringify(entry);
  if (level === "error") {
    console.error(line);
  } else if (level === "warn") {
    console.warn(line);
  } else {
    console.log(line);
  }
}

export const logger = {
  debug: (msg: string, meta?: unknown) => log("debug", msg, meta),
  info: (msg: string, meta?: unknown) => log("info", msg, meta),
  warn: (msg: string, meta?: unknown) => log("warn", msg, meta),
  error: (msg: string, meta?: unknown) => log("error", msg, meta)
};
