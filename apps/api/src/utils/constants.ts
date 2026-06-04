/** Shared constants for the API server. */

/** Default port if PORT env var is not set. */
export const DEFAULT_PORT = 5000;

/** Maximum allowed body size for JSON requests. (50MB supports ~20m of raw audio) */
export const JSON_BODY_LIMIT = "50mb";

/** Maximum number of sessions returned in a list query. */
export const SESSION_LIST_LIMIT = 100;

/** Maximum number of recent transcript segments returned per session. */
export const SEGMENT_LIST_LIMIT = 500;

/** Rate limit window in milliseconds (15 minutes). */
export const RATE_LIMIT_WINDOW_MS = 15 * 60 * 1000;

/** Max session-creation requests per window per IP. */
export const RATE_LIMIT_CREATE_SESSION = 30;
