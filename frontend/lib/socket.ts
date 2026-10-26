import { API_BASE } from "./api";

type ServerMsg =
  | { type: "ready" }
  | { type: "user_text"; text: string }
  | { type: "ai_text"; text: string }
  | { type: "ai_audio"; data: string; mimeType: string }
  | { type: "audio_ended"; requestId?: string; ok: boolean }
  | { type: "nudge"; level: "info" | "warn"; message: string }
  | { type: "error"; message: string };

export function openLiveSocket(args: {
  sessionId: string;
  accessToken: string;
  onAi: (text: string) => void;
  onUserTranscript?: (text: string) => void;
  onAiAudio?: (audio: { data: string; mimeType: string }) => void;
  onNudge: (n: { level: "info" | "warn"; message: string }) => void;
  onError: (message: string) => void;
}) {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";

  const ws = new WebSocket(url.toString());
  const pending: string[] = [];
  let finishSequence = 0;
  let completion: { id: string; resolve: () => void; reject: (error: Error) => void;
    timer: ReturnType<typeof setTimeout>; promise: Promise<void> } | null = null;

  function rejectCompletion(message: string) {
    if (!completion) return;
    clearTimeout(completion.timer);
    completion.reject(new Error(message));
    completion = null;
  }

  function sendRaw(payload: unknown) {
    const s = JSON.stringify(payload);
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(s);
    } else if (ws.readyState === WebSocket.CONNECTING) {
      pending.push(s);
    } else {
      return false;
    }
    return true;
  }

  ws.onopen = () => {
    sendRaw({ type: "hello", sessionId: args.sessionId, accessToken: args.accessToken });
    for (const msg of pending.splice(0, pending.length)) ws.send(msg);
  };

  ws.onmessage = (evt) => {
    let msg: ServerMsg;
    try {
      msg = JSON.parse(evt.data as string) as ServerMsg;
    } catch {
      // Malformed server message — log and ignore rather than crashing the handler.
      console.warn("[socket] received non-JSON message", evt.data);
      return;
    }

    if (msg.type === "audio_ended" && completion && msg.requestId === completion.id) {
      if (msg.ok) {
        clearTimeout(completion.timer);
        completion.resolve();
        completion = null;
      } else {
        rejectCompletion("Final speech was not confirmed. Please retry End & Analyze.");
      }
      return;
    }

    if (msg.type === "user_text") args.onUserTranscript?.(msg.text);
    if (msg.type === "ai_text") args.onAi(msg.text);
    if (msg.type === "ai_audio") args.onAiAudio?.({ data: msg.data, mimeType: msg.mimeType });
    if (msg.type === "nudge") args.onNudge({ level: msg.level, message: msg.message });
    if (msg.type === "error") args.onError(msg.message);
  };

  ws.onerror = (event) => {
    console.error("[socket] WebSocket error", event);
    args.onError("websocket_error");
    rejectCompletion("Live connection error. Your session has not been ended.");
  };
  ws.onclose = () => {
    pending.length = 0;
    rejectCompletion("Live connection closed. Your session has not been ended.");
  };

  return {
    sendUserText(text: string, isControl = false) {
      sendRaw({ type: "user_text", sessionId: args.sessionId, text, ...(isControl ? { isControl: true } : {}) });
    },
    sendAudioChunk(data: string, mimeType = "audio/pcm;rate=16000") {
      sendRaw({ type: "audio_chunk", sessionId: args.sessionId, data, mimeType });
    },
    endAudio() {
      sendRaw({ type: "audio_end", sessionId: args.sessionId });
    },
    finishAudio(timeoutMs = 35000): Promise<void> {
      if (completion) return completion.promise;
      const id = `${args.sessionId}:${++finishSequence}`;
      let resolve!: () => void;
      let reject!: (error: Error) => void;
      const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
      const timer = setTimeout(() => rejectCompletion("Final speech was not confirmed. Please retry End & Analyze."), timeoutMs);
      completion = { id, resolve, reject, timer, promise };
      try {
        if (!sendRaw({ type: "audio_end", sessionId: args.sessionId, final: true, requestId: id })) {
          rejectCompletion("Live connection closed. Your session has not been ended.");
        }
      } catch (error) {
        rejectCompletion(error instanceof Error ? error.message : "Live connection closed.");
      }
      return promise;
    },
    sendVideoFrame(data: string, mimeType = "image/jpeg") {
      sendRaw({ type: "video_frame", sessionId: args.sessionId, data, mimeType });
    },
    close() {
      ws.close();
    }
  };
}
