import { z } from "zod";
import type { WebSocket, WebSocketServer } from "ws";
import { prisma } from "../db.js";
import { createGeminiLiveSession, type GeminiLiveSession } from "../services/geminiLive.js";
import { normalizePersona, normalizePressureLevel } from "../services/scenarios.js";
import { logger } from "../utils/logger.js";
import { audioBufferStore } from "../utils/audioStore.js";

// ── Message schemas (Zod) ───────────────────────────────────────────────────────
// All inbound WebSocket messages are validated at runtime before any field access.

const HelloSchema = z.object({ type: z.literal("hello"), sessionId: z.string().cuid() });
const UserTextSchema = z.object({ type: z.literal("user_text"), sessionId: z.string().cuid(), text: z.string().min(1).max(4000) });
const AudioChunkSchema = z.object({ type: z.literal("audio_chunk"), sessionId: z.string().cuid(), data: z.string().min(1), mimeType: z.string().optional() });
const AudioEndSchema = z.object({ type: z.literal("audio_end"), sessionId: z.string().cuid() });
const VideoFrameSchema = z.object({ type: z.literal("video_frame"), sessionId: z.string().cuid(), data: z.string().min(1), mimeType: z.string().optional() });

const ClientMsgSchema = z.discriminatedUnion("type", [
  HelloSchema,
  UserTextSchema,
  AudioChunkSchema,
  AudioEndSchema,
  VideoFrameSchema
]);

type ClientMsg = z.infer<typeof ClientMsgSchema>;

type ServerMsg =
  | { type: "ready" }
  | { type: "user_text"; text: string }
  | { type: "ai_text"; text: string }
  | { type: "ai_audio"; data: string; mimeType: string }
  | { type: "nudge"; level: "info" | "warn"; message: string }
  | { type: "error"; message: string };

type LiveStats = {
  startedAt: number;
  words: number;
};

// ── Utilities ───────────────────────────────────────────────────────────────────

function safeJsonParse(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function send(ws: WebSocket, msg: ServerMsg) {
  if (ws.readyState === ws.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

function sendLiveNudges(ws: WebSocket, text: string, stats: LiveStats) {
  const fillers = (text.match(/\b(um+|uh+|like|you know)\b/gi) || []).length;
  if (fillers >= 3) {
    send(ws, {
      type: "nudge",
      level: "info",
      message: "Quick nudge: try pausing instead of filler words."
    });
  }

  stats.words += text.split(/\s+/).filter(Boolean).length;
  const minutes = (Date.now() - stats.startedAt) / 60000;
  if (minutes <= 0.6) return;

  const wpm = stats.words / minutes;
  if (wpm > 175) {
    send(ws, { type: "nudge", level: "warn", message: "You're speaking a bit fast - slow down slightly." });
  } else if (wpm < 105) {
    send(ws, { type: "nudge", level: "info", message: "You can speed up slightly to sound more confident." });
  }
}

function transcriptDelta(current: string, next: string) {
  if (!current) return next;
  if (!next || next === current || current.endsWith(next)) return "";
  if (next.startsWith(current)) return next.slice(current.length);

  const maxOverlap = Math.min(current.length, next.length);
  for (let length = maxOverlap; length > 0; length -= 1) {
    if (current.endsWith(next.slice(0, length))) {
      return next.slice(length);
    }
  }

  return next;
}

function cleanTranscript(text: string) {
  // 1. Collapse whitespace and deduplicate adjacent identical words.
  const rawWords = text.replace(/\s+/g, " ").trim().split(" ");
  let cleaned: string[] = [];
  for (const word of rawWords) {
    const previous = cleaned[cleaned.length - 1];
    if (previous && previous.toLowerCase() === word.toLowerCase()) continue;
    cleaned.push(word);
  }

  // 2. Collapse repeated n-gram phrases (phrase-level deduplication).
  for (let size = 6; size >= 2; size -= 1) {
    const compacted: string[] = [];
    for (let i = 0; i < cleaned.length; i += 1) {
      const prev = compacted.slice(-size).join(" ").toLowerCase();
      const curr = cleaned.slice(i, i + size).join(" ").toLowerCase();
      if (prev && prev === curr) {
        i += size - 1;
      } else {
        compacted.push(cleaned[i]);
      }
    }
    cleaned = compacted;
  }

  return cleaned.join(" ");
}

// ── Main export ─────────────────────────────────────────────────────────────────

export function registerLiveWs(wss: WebSocketServer) {
  wss.on("connection", (ws) => {
    const stats: LiveStats = { startedAt: Date.now(), words: 0 };
    let liveSession: GeminiLiveSession | null = null;

    /**
     * The sessionId is set once when the client sends `hello`.
     * All subsequent messages MUST carry the same sessionId; mismatches are rejected.
     * This prevents a rogue client from hijacking another session.
     */
    let boundSessionId: string | null = null;

    let aiTextBuffer = "";
    let userAudioTextBuffer = "";

    send(ws, { type: "ready" });

    async function closeLiveSession() {
      liveSession?.close();
      liveSession = null;
      aiTextBuffer = "";
      userAudioTextBuffer = "";
    }

    async function ensureLiveSession(sessionId: string): Promise<GeminiLiveSession | null> {
      if (liveSession && boundSessionId === sessionId) return liveSession;
      await closeLiveSession();

      const session = await prisma.session.findUnique({
        where: { id: sessionId },
        select: { contextJson: true, scenario: true, persona: true, pressureLevel: true }
      });
      if (!session) return null;

      const personaId = normalizePersona(session.persona);
      const pressureLevel = normalizePressureLevel(session.pressureLevel);

      boundSessionId = sessionId;
      liveSession = createGeminiLiveSession(
        session.scenario,
        (session.contextJson as Record<string, unknown>) ?? null,
        {
        onInputText: (text) => {
          userAudioTextBuffer += transcriptDelta(userAudioTextBuffer, text);
        },
        onText: (text) => {
          aiTextBuffer += transcriptDelta(aiTextBuffer, text);
        },
        onAudio: (audio) => {
          send(ws, { type: "ai_audio", data: audio.data, mimeType: audio.mimeType });
        },
        onTurnComplete: async () => {
          const userAudioText = userAudioTextBuffer.trim();
          userAudioTextBuffer = "";
          if (userAudioText && boundSessionId) {
            const cleanUserText = cleanTranscript(userAudioText);
            await prisma.transcriptSegment.create({
              data: { sessionId: boundSessionId, speaker: "user", text: cleanUserText }
            });
            sendLiveNudges(ws, userAudioText, stats);
            send(ws, { type: "user_text", text: cleanUserText });
          }

          const text = aiTextBuffer.trim();
          aiTextBuffer = "";
          if (!text || !boundSessionId) return;

          const cleanText = cleanTranscript(text);
          await prisma.transcriptSegment.create({
            data: { sessionId: boundSessionId, speaker: "ai", text: cleanText }
          });
          send(ws, { type: "ai_text", text: cleanText });
        },
        onError: (message) => send(ws, { type: "error", message })
      }, personaId, pressureLevel);

      return liveSession;
    }

    ws.on("message", async (data) => {
      try {
        const raw = typeof data === "string" ? data : data.toString("utf8");
        const rawParsed = safeJsonParse(raw);

        if (!rawParsed || typeof rawParsed !== "object") {
          return send(ws, { type: "error", message: "invalid_json" });
        }

        // Validate the message shape with Zod.
        const result = ClientMsgSchema.safeParse(rawParsed);
        if (!result.success) {
          return send(ws, { type: "error", message: "invalid_message" });
        }
        const parsed: ClientMsg = result.data;

        // ── hello: bind the session to this connection ──
        if (parsed.type === "hello") {
          boundSessionId = parsed.sessionId;
          return;
        }

        // ── Guard: sessionId must match the bound session ──
        if (boundSessionId && parsed.sessionId !== boundSessionId) {
          logger.warn("[ws] sessionId mismatch", { bound: boundSessionId, received: parsed.sessionId });
          return send(ws, { type: "error", message: "session_id_mismatch" });
        }

        const session = await ensureLiveSession(parsed.sessionId);
        if (!session) return send(ws, { type: "error", message: "session_not_found" });

        if (parsed.type === "audio_chunk") {
          audioBufferStore.append(parsed.sessionId, parsed.data);
          session.sendAudio({ data: parsed.data, mimeType: parsed.mimeType ?? "audio/pcm;rate=16000" });
          return;
        }

        if (parsed.type === "audio_end") {
          session.endAudio();
          return;
        }

        if (parsed.type === "video_frame") {
          session.sendVideo({ data: parsed.data, mimeType: parsed.mimeType ?? "image/jpeg" });
          return;
        }

        // parsed.type === "user_text" (narrowed by discriminatedUnion)
        sendLiveNudges(ws, parsed.text, stats);
        await prisma.transcriptSegment.create({
          data: { sessionId: parsed.sessionId, speaker: "user", text: parsed.text }
        });
        session.sendText(parsed.text);
      } catch (e) {
        logger.error("[ws] message handler error", e instanceof Error ? e.message : e);
        send(ws, { type: "error", message: "live_session_failed" });
      }
    });

    ws.on("close", () => {
      void closeLiveSession();
    });
  });
}
