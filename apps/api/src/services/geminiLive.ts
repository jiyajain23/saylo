import WebSocket from "ws";
import { formatContextForPrompt, type StructuredContext } from "./contextEngine.js";
import { normalizeScenario, scenarioConfig, getPersona, getPressureModifier, type Scenario, type PersonaId, type PressureLevel } from "./scenarios.js";
import { logger } from "../utils/logger.js";

const GEMINI_LIVE_ENDPOINT =
  "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent";

// ── Typed Gemini wire-format interfaces ────────────────────────────────────────

interface InlineData {
  data: string;
  mimeType: string;
}

interface Part {
  text?: string;
  inlineData?: InlineData;
}

interface ModelTurn {
  parts?: Part[];
}

interface Transcription {
  text?: string;
}

interface ServerContent {
  modelTurn?: ModelTurn;
  outputTranscription?: Transcription;
  inputTranscription?: Transcription;
  turnComplete?: boolean;
}

interface GeminiResponse {
  setupComplete?: boolean;
  serverContent?: ServerContent;
}

// ── Public types ───────────────────────────────────────────────────────────────

type GeminiLiveHandlers = {
  onInputText?: (text: string) => void | Promise<void>;
  onText: (text: string) => void | Promise<void>;
  onAudio?: (audio: { data: string; mimeType: string }) => void | Promise<void>;
  onTurnComplete?: () => void | Promise<void>;
  onError?: (message: string) => void;
};

export type GeminiLiveSession = {
  sendText: (text: string) => void;
  sendAudio: (audio: { data: string; mimeType: string }) => void;
  sendVideo: (video: { data: string; mimeType: string }) => void;
  endAudio: () => void;
  close: () => void;
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function liveModel() {
  return process.env.GEMINI_LIVE_MODEL || "gemini-2.0-flash-live-001";
}

function buildSystemInstruction(
  scenario: Scenario,
  context?: StructuredContext | null,
  personaId?: PersonaId | null,
  pressureLevel?: PressureLevel | null
) {
  const config = scenarioConfig[scenario];
  const persona = getPersona(personaId);
  const pressureModifier = getPressureModifier(pressureLevel);

  const personaBlock = persona.modifier ? `\n\n${persona.modifier}` : "";
  const pressureBlock = pressureModifier ? `\n\n${pressureModifier}` : "";

  return `You are a ${config.aiRole} running a realistic ${config.label.toLowerCase()} simulation.
- Keep responses concise.
- Ask one question at a time.
- Adapt dynamically based on the user's last answer.
- Use the session context when relevant, but do not mention that you have it.
- Avoid being judgmental; sound professional.
- Opening behavior: ${config.openingPrompt}
- Live goals: ${config.liveGoals.join("; ")}.
- Evaluate for: ${config.evaluationFocus.join(", ")}.${personaBlock}${pressureBlock}${formatContextForPrompt(context)}`;
}

function setupMessage(
  scenario: Scenario,
  context?: StructuredContext | null,
  personaId?: PersonaId | null,
  pressureLevel?: PressureLevel | null
) {
  return {
    setup: {
      model: `models/${liveModel()}`,
      generation_config: { response_modalities: ["AUDIO"] },
      system_instruction: {
        parts: [{ text: buildSystemInstruction(scenario, context, personaId, pressureLevel) }]
      }
    }
  };
}

function extractText(response: GeminiResponse): string {
  const parts = response.serverContent?.modelTurn?.parts ?? [];
  const modelText = parts
    .map((p) => p.text)
    .filter((t): t is string => typeof t === "string")
    .join("");
  const transcription = response.serverContent?.outputTranscription?.text;
  return modelText || (typeof transcription === "string" ? transcription : "");
}

function extractInputText(response: GeminiResponse): string {
  const transcription = response.serverContent?.inputTranscription?.text;
  return typeof transcription === "string" ? transcription : "";
}

function extractAudio(response: GeminiResponse): Array<{ data: string; mimeType: string }> {
  const parts = response.serverContent?.modelTurn?.parts ?? [];
  const results: Array<{ data: string; mimeType: string }> = [];
  for (const part of parts) {
    if (part.inlineData && typeof part.inlineData.data === "string") {
      results.push({
        data: part.inlineData.data,
        mimeType: typeof part.inlineData.mimeType === "string" ? part.inlineData.mimeType : "audio/pcm;rate=24000"
      });
    }
  }
  return results;
}

// ── Factory ────────────────────────────────────────────────────────────────────

export function createGeminiLiveSession(
  scenario: unknown,
  context: StructuredContext | Record<string, unknown> | null | undefined,
  handlers: GeminiLiveHandlers,
  personaId?: PersonaId | null,
  pressureLevel?: PressureLevel | null
): GeminiLiveSession {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    throw new Error("GEMINI_API_KEY is required for Gemini Live sessions");
  }

  const url = `${GEMINI_LIVE_ENDPOINT}?key=${encodeURIComponent(key)}`;
  const upstream = new WebSocket(url);
  const pending: string[] = [];
  let setupComplete = false;

  function sendJson(payload: unknown) {
    const msg = JSON.stringify(payload);
    if (upstream.readyState === WebSocket.OPEN && setupComplete) {
      upstream.send(msg);
    } else {
      pending.push(msg);
    }
  }

  upstream.on("open", () => {
    upstream.send(JSON.stringify(setupMessage(normalizeScenario(scenario), context as StructuredContext | null, personaId, pressureLevel)));
  });

  upstream.on("message", async (data) => {
    try {
      const response = JSON.parse(data.toString("utf8")) as GeminiResponse;

      if (response.setupComplete) {
        setupComplete = true;
        for (const msg of pending.splice(0, pending.length)) {
          upstream.send(msg);
        }
        return;
      }

      const text = extractText(response);
      if (text) await handlers.onText(text);

      const inputText = extractInputText(response);
      if (inputText) await handlers.onInputText?.(inputText);

      for (const audio of extractAudio(response)) {
        await handlers.onAudio?.(audio);
      }

      if (response.serverContent?.turnComplete) {
        await handlers.onTurnComplete?.();
      }
    } catch (e) {
      logger.error("[gemini-live] message parse error", e instanceof Error ? e.message : e);
      handlers.onError?.("gemini_live_message_failed");
    }
  });

  upstream.on("error", (e) => {
    logger.error("[gemini-live] connection error", e.message);
    handlers.onError?.("gemini_live_connection_failed");
  });

  upstream.on("close", (code, reason) => {
    if (code !== 1000) {
      const detail = reason.toString() || `closed_${code}`;
      handlers.onError?.(`gemini_live_closed:${detail}`);
    }
  });

  return {
    sendText(text: string) {
      sendJson({
        clientContent: {
          turns: [{ role: "user", parts: [{ text }] }],
          turnComplete: true
        }
      });
    },
    sendAudio(audio: { data: string; mimeType: string }) {
      sendJson({
        realtimeInput: {
          audio: { data: audio.data, mimeType: audio.mimeType }
        }
      });
    },
    sendVideo(video: { data: string; mimeType: string }) {
      sendJson({
        realtimeInput: {
          video: { data: video.data, mimeType: video.mimeType }
        }
      });
    },
    endAudio() {
      // Note: The protocol doesn't always have a direct 'audioStreamEnd' inside realtime_input
      // but some versions use it or just expect silence. We'll use a text signal or keep as is if supported.
      // For now, let's use the most common signal if any.
    },
    close() {
      upstream.terminate();
    }
  };
}
