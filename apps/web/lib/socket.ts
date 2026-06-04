import { API_BASE } from "./api";

type ServerMsg =
  | { type: "ready" }
  | { type: "user_text"; text: string }
  | { type: "ai_text"; text: string }
  | { type: "ai_audio"; data: string; mimeType: string }
  | { type: "nudge"; level: "info" | "warn"; message: string }
  | { type: "error"; message: string };

export function openLiveSocket(args: {
  sessionId: string;
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

  function sendRaw(payload: unknown) {
    const s = JSON.stringify(payload);
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(s);
    } else {
      pending.push(s);
    }
  }

  ws.onopen = () => {
    sendRaw({ type: "hello", sessionId: args.sessionId });
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

    if (msg.type === "user_text") args.onUserTranscript?.(msg.text);
    if (msg.type === "ai_text") args.onAi(msg.text);
    if (msg.type === "ai_audio") args.onAiAudio?.({ data: msg.data, mimeType: msg.mimeType });
    if (msg.type === "nudge") args.onNudge({ level: msg.level, message: msg.message });
    if (msg.type === "error") args.onError(msg.message);
  };

  ws.onerror = (event) => {
    console.error("[socket] WebSocket error", event);
    args.onError("websocket_error");
  };

  return {
    sendUserText(text: string) {
      sendRaw({ type: "user_text", sessionId: args.sessionId, text });
    },
    sendAudioChunk(data: string, mimeType = "audio/pcm;rate=16000") {
      sendRaw({ type: "audio_chunk", sessionId: args.sessionId, data, mimeType });
    },
    endAudio() {
      sendRaw({ type: "audio_end", sessionId: args.sessionId });
    },
    sendVideoFrame(data: string, mimeType = "image/jpeg") {
      sendRaw({ type: "video_frame", sessionId: args.sessionId, data, mimeType });
    },
    close() {
      ws.close();
    }
  };
}
