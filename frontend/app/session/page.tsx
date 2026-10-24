"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createSession, endSession, type Scenario } from "../../lib/api";
import { openLiveSocket } from "../../lib/socket";
import { useVisionMetrics, type VisionMetrics } from "../../hooks/useVisionMetrics";
import {
  Mic,
  Square,
  Video,
  VideoOff,
  Send,
  X,
  Smile,
  Eye,
  Activity,
  Move,
  Sun,
  MicOff,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Briefcase,
  Presentation,
  Users
} from "lucide-react";

type Turn = { speaker: "user" | "ai"; text: string };
type AudioPlayback = { context: AudioContext; nextTime: number };
type MicCapture = { stream: MediaStream; context: AudioContext; source: MediaStreamAudioSourceNode; processor: ScriptProcessorNode; silentGain: GainNode };
type VideoCapture = { stream: MediaStream; frameTimer: ReturnType<typeof setInterval> };
type PurposeMode = "practice" | "evaluate";

const SCENARIOS: { id: Scenario; label: string; desc: string; contextLabel: string; starter: string; icon: React.ReactNode }[] = [
  { id: "INTERVIEW", label: "Interview", desc: "Adaptive mock interview with follow-up questions", contextLabel: "Resume + job description", starter: "Hi, I'm ready for the interview.", icon: <Briefcase size={20} /> },
  { id: "PITCH", label: "Pitch", desc: "Pitch practice with critical investor-style probing", contextLabel: "Pitch topic + audience notes", starter: "Hi, I'm ready to practice my pitch.", icon: <Presentation size={20} /> },
  { id: "MEETING", label: "Meeting", desc: "Meeting simulation with stakeholder dynamics", contextLabel: "Meeting goal + stakeholder notes", starter: "Hi, I'm ready for the meeting simulation.", icon: <Users size={20} /> }
];

const PERSONAS = [
  { id: "DEFAULT", label: "Standard", desc: "Balanced, professional coach" },
  { id: "THE_SKEPTIC", label: "The Skeptic", desc: "Challenges every claim" },
  { id: "THE_FRIENDLY", label: "The Mentor", desc: "Supportive and encouraging" },
  { id: "THE_RUSHED", label: "The Rushed Manager", desc: "Demands concise updates" },
  { id: "THE_PANEL", label: "The Tough Panel", desc: "Rapid-fire questions" },
  { id: "THE_CONFUSED", label: "The Confused Stakeholder", desc: "Needs simple explanations" }
];

const PRESSURE_LEVELS = [
  { level: 0, label: "None" },
  { level: 1, label: "Mild" },
  { level: 2, label: "Moderate" },
  { level: 3, label: "High" }
];

function ArcGauge({ value, label, color = "#296e91" }: { value: number; label: string; color?: string }) {
  const r = 22, circ = Math.PI * r;
  const fill = circ * (1 - Math.min(value, 1));
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.25rem" }}>
      <svg className="chart" role="img" aria-label={`${label}: ${Math.round(value * 100)}%`} width="56" height="34" viewBox="0 0 56 34">
        <path d="M6,30 A22,22 0 0,1 50,30" fill="none" stroke="#dce8ec" strokeWidth="5" strokeLinecap="round" />
        <path d="M6,30 A22,22 0 0,1 50,30" fill="none" stroke={color}
          strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${circ}`} strokeDashoffset={fill} />
        <text x="28" y="30" textAnchor="middle" fontSize="10" fontWeight="700" fill="#28495a">
          {Math.round(value * 100)}%
        </text>
      </svg>
      <span style={{ fontSize: "0.8125rem", color: "var(--text-3)" }}>{label}</span>
    </div>
  );
}

export default function LiveSessionPage() {
  const [scenario, setScenario] = useState<Scenario>("INTERVIEW");
  const [persona, setPersona] = useState<string>("DEFAULT");
  const [pressureLevel, setPressureLevel] = useState<number>(0);
  const [title, setTitle] = useState("Mock interview");
  const [purposeMode, setPurposeMode] = useState<PurposeMode>("practice");
  const [resumeText, setResumeText] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [topicNotes, setTopicNotes] = useState("");
  const [freeText, setFreeText] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [nudges, setNudges] = useState<{ id: number; level: "info" | "warn" | "success"; category: string; message: string; ts: number }[]>([]);
  const nudgeIdRef = useRef(0);
  const nudgeCooldownRef = useRef<Record<string, number>>({});  // category → last-fired timestamp
  const [status, setStatus] = useState<"setup" | "live" | "ending">("setup");
  const [isStreamingMic, setIsStreamingMic] = useState(false);
  const [isStreamingVideo, setIsStreamingVideo] = useState(false);
  const [visionMetrics, setVisionMetrics] = useState<VisionMetrics | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const socketRef = useRef<ReturnType<typeof openLiveSocket> | null>(null);
  const audioPlaybackRef = useRef<AudioPlayback | null>(null);
  const micCaptureRef = useRef<MicCapture | null>(null);
  const videoCaptureRef = useRef<VideoCapture | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const isAnalyzingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  const { analyze: analyzeVision } = useVisionMetrics(videoRef);
  const canUseMic = useMemo(() => typeof window !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia), []);

  useEffect(() => () => {
    socketRef.current?.close();
    void audioPlaybackRef.current?.context.close();
    stopMicStream(); stopVideoStream();
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  function chooseScenario(s: Scenario) {
    setScenario(s);
    const defaultTitles = ["Mock interview", "Pitch practice", "Meeting simulation"];
    setTitle((t) => defaultTitles.includes(t) ? SCENARIOS.find((x) => x.id === s)!.label + (s === "INTERVIEW" ? " practice" : s === "PITCH" ? " practice" : " simulation") : t);
  }

  function ensureAudioPlayback() {
    if (!audioPlaybackRef.current) {
      const Ctx = window.AudioContext || (window as never as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioPlaybackRef.current = { context: new Ctx(), nextTime: 0 };
    }
    void audioPlaybackRef.current.context.resume();
    return audioPlaybackRef.current;
  }

  function playPcmAudio(data: string, mimeType: string) {
    const playback = ensureAudioPlayback();
    const binary = window.atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const view = new DataView(bytes.buffer);
    const match = mimeType.match(/rate=(\d+)/i);
    const rate = match ? Number(match[1]) : 24000;
    const frameCount = Math.floor(bytes.byteLength / 2);
    const buf = playback.context.createBuffer(1, frameCount, rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < frameCount; i++) ch[i] = view.getInt16(i * 2, true) / 32768;
    const src = playback.context.createBufferSource();
    src.buffer = buf; src.connect(playback.context.destination);
    const at = Math.max(playback.context.currentTime + 0.02, playback.nextTime);
    src.start(at); playback.nextTime = at + buf.duration;
  }

  function floatTo16BitPcmBase64(input: Float32Array, inputSampleRate: number) {
    const targetSampleRate = 16000;
    const ratio = inputSampleRate / targetSampleRate;
    const newLength = Math.floor(input.length / ratio);
    const pcmBuffer = new Int16Array(newLength);

    for (let i = 0; i < newLength; i++) {
      const offset = Math.floor(i * ratio);
      // Clamp to [-1, 1] then scale to 16-bit range
      const sample = Math.max(-1, Math.min(1, input[offset] ?? 0));
      pcmBuffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
    }

    // Convert Int16Array to base64
    const bytes = new Uint8Array(pcmBuffer.buffer);
    let binary = "";
    const chunk = 8192;
    for (let i = 0; i < bytes.length; i += chunk) {
      const slice = bytes.subarray(i, i + chunk);
      binary += String.fromCharCode.apply(null, slice as any);
    }
    return window.btoa(binary);
  }

  async function startMicStream() {
    if (micCaptureRef.current || !socketRef.current) return;
    try {
      const Ctx = window.AudioContext || (window as any).webkitAudioContext;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      const context = new Ctx();

      // IMPORTANT: Context starts suspended in most browsers; must resume on user gesture.
      await context.resume();

      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silentGain = context.createGain();
      silentGain.gain.value = 0;

      processor.onaudioprocess = (e) => {
        if (!socketRef.current) return;
        const inputData = e.inputBuffer.getChannelData(0);
        const pcmData = floatTo16BitPcmBase64(inputData, context.sampleRate);
        socketRef.current.sendAudioChunk(pcmData);
      };

      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(context.destination);

      micCaptureRef.current = { stream, context, source, processor, silentGain };
      setIsStreamingMic(true);
    } catch (err) {
      console.error("[mic] failed to start stream", err);
      setNudges((x) => [{ id: ++nudgeIdRef.current, level: "warn" as const, category: "mic", message: "Could not access microphone.", ts: Date.now() }, ...x].slice(0, 6));
    }
  }

  function stopMicStream() {
    const c = micCaptureRef.current; if (!c) return;
    c.processor.disconnect(); c.silentGain.disconnect(); c.source.disconnect();
    c.stream.getTracks().forEach((t) => t.stop()); void c.context.close();
    micCaptureRef.current = null; socketRef.current?.endAudio(); setIsStreamingMic(false);
  }

  /** Push a nudge with per-category cooldown and auto-expiry. */
  function pushNudge(level: "info" | "warn" | "success", category: string, message: string, cooldownMs = 8000) {
    const now = Date.now();
    const last = nudgeCooldownRef.current[category] ?? 0;
    if (now - last < cooldownMs) return;  // still cooling down
    nudgeCooldownRef.current[category] = now;
    const id = ++nudgeIdRef.current;
    setNudges(prev => [{ id, level, category, message, ts: now }, ...prev].slice(0, 6));
    // Auto-remove after 12 s
    setTimeout(() => setNudges(prev => prev.filter(n => n.id !== id)), 12000);
  }

  /** Estimate average luma from current canvas frame (0-255). */
  function estimateLuma(): number {
    const canvas = canvasRef.current;
    if (!canvas) return 128;
    try {
      const ctx = canvas.getContext("2d");
      if (!ctx) return 128;
      const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
      let sum = 0;
      for (let i = 0; i < data.length; i += 16) {  // sample every 4th pixel
        sum += 0.299 * data[i]! + 0.587 * data[i + 1]! + 0.114 * data[i + 2]!;
      }
      return sum / (data.length / 16);
    } catch { return 128; }
  }

  async function captureVideoFrame() {
    const video = videoRef.current, canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2 || !socketRef.current) return;
    const w = 320, h = Math.max(1, Math.round((video.videoHeight / Math.max(1, video.videoWidth)) * w));
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    ctx.drawImage(video, 0, 0, w, h);
    const [, data] = canvas.toDataURL("image/jpeg", 0.55).split(",");
    if (data) socketRef.current.sendVideoFrame(data, "image/jpeg");

    // ── Lighting check (on canvas, no ML needed) ───────────────────────────
    const luma = estimateLuma();
    if (luma < 55) pushNudge("warn", "lighting", "Too dark — move to a brighter spot or turn on a light.");
    else if (luma > 230) pushNudge("warn", "lighting", "Overexposed — try reducing the light behind you.");

    if (isAnalyzingRef.current) return;
    isAnalyzingRef.current = true;
    try {
      const m = await analyzeVision();
      setVisionMetrics(m);

      // ── Face presence ─────────────────────────────────────────────────────
      if (!m.face_present) {
        pushNudge("warn", "face", "Move into frame — camera can't detect your face.");
        return;  // rest of metrics are unreliable without a face
      }

      // ── Eye contact ───────────────────────────────────────────────────────
      if (m.eye_contact < 0.30) {
        pushNudge("warn", "eye", "Look directly at the camera — strong eye contact builds trust.");
      } else if (m.eye_contact < 0.55) {
        pushNudge("info", "eye", "Try to keep your gaze closer to the camera lens.");
      } else if (m.eye_contact > 0.80) {
        pushNudge("success", "eye", "Great eye contact — keep it up.", 20000);
      }

      // ── Posture ───────────────────────────────────────────────────────────
      if (m.posture === "needs_work") {
        pushNudge("warn", "posture", "Square your shoulders and sit taller — posture signals confidence.");
      } else if (m.posture === "good") {
        pushNudge("success", "posture", "Posture looks solid.", 30000);
      }

      // ── Head movement ─────────────────────────────────────────────────────
      if (m.movement > 0.65) {
        pushNudge("warn", "movement", "Reduce head movement — steadiness projects composure.");
      } else if (m.movement > 0.40) {
        pushNudge("info", "movement", "Slight head movement detected — stay a bit steadier.");
      }
    } catch { /* ignore */ } finally { isAnalyzingRef.current = false; }
  }

  async function startVideoStream() {
    if (videoCaptureRef.current || !socketRef.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" } });
    if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
    const frameTimer = setInterval(() => void captureVideoFrame(), 1000);
    videoCaptureRef.current = { stream, frameTimer }; setIsStreamingVideo(true);
    pushNudge("info", "system", "Camera on. Keep your face centred and well lit.", 0);
    void captureVideoFrame();
  }

  function stopVideoStream() {
    const c = videoCaptureRef.current; if (!c) return;
    clearInterval(c.frameTimer); c.stream.getTracks().forEach((t) => t.stop());
    if (videoRef.current) videoRef.current.srcObject = null;
    videoCaptureRef.current = null; setVisionMetrics(null); setIsStreamingVideo(false);
  }

  async function start() {
    try {
      const sc = SCENARIOS.find((x) => x.id === scenario)!;
      const { session } = await createSession({
        scenario, title, persona, pressureLevel,
        resumeText: resumeText || undefined, jobDescription: jobDescription || undefined,
        topicNotes: topicNotes || undefined,
        freeText: (freeText || "") + (purposeMode === "evaluate" ? "\n\nMode: Evaluate — score the user strictly, highlight every weakness explicitly." : "")
      });
      setSessionId(session.id); setTurns([]); setNudges([]); nudgeCooldownRef.current = {}; setStatus("live");
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000)), 1000);
      ensureAudioPlayback();
      const socket = openLiveSocket({
        sessionId: session.id,
        onAi: (text) => setTurns((t) => [...t, { speaker: "ai", text }]),
        onUserTranscript: (text) => setTurns((t) => [...t, { speaker: "user", text }]),
        onAiAudio: (audio) => playPcmAudio(audio.data, audio.mimeType),
      onNudge: (n: any) => { const id = ++nudgeIdRef.current; setNudges(x => [{ id, level: n.level ?? "info", category: n.category ?? "system", message: n.message ?? "", ts: Date.now() }, ...x].slice(0, 6)); setTimeout(() => setNudges(p => p.filter(x => x.id !== id)), 12000); },
      onError: (msg: string) => { const id = ++nudgeIdRef.current; setNudges(x => [{ id, level: "warn" as const, category: "error", message: msg, ts: Date.now() }, ...x].slice(0, 6)); setTimeout(() => setNudges(p => p.filter(x => x.id !== id)), 12000); }
      });
    socketRef.current = socket; socket.sendUserText(sc.starter);
    // Welcome nudge after a short delay
    setTimeout(() => pushNudge("info", "system", "Session live. Keep your face centred and speak clearly.", 0), 1500);
    } catch (e) {
      const id = ++nudgeIdRef.current;
      setNudges([{ id, level: "warn" as const, category: "error", message: e instanceof Error ? e.message : "Failed to start session.", ts: Date.now() }]);
      setStatus("setup");
    }
  }

  function send() {
    const text = draft.trim(); if (!text || !sessionId) return;
    setTurns((t) => [...t, { speaker: "user", text }]);
    socketRef.current?.sendUserText(text); setDraft("");
  }

  async function finish() {
    if (!sessionId) return; setStatus("ending");
    stopMicStream(); stopVideoStream(); socketRef.current?.close();
    if (timerRef.current) clearInterval(timerRef.current);
    try { await endSession(sessionId); window.location.href = `/insights?sessionId=${encodeURIComponent(sessionId)}`; }
    catch (e) {
      setNudges((x) => [{ id: ++nudgeIdRef.current, level: "warn" as const, category: "error", message: e instanceof Error ? e.message : "Failed to end session.", ts: Date.now() }, ...x].slice(0, 5));
      setStatus("live");
    }
  }

  const fmtTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const sc = SCENARIOS.find((x) => x.id === scenario)!;

  // ── Setup screen ──────────────────────────────────────────────────────────
  if (status === "setup") return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className="page-heading">
        <h1>Live Session</h1>
        <p style={{ color: "var(--text-2)", marginTop: "0.35rem", fontSize: "0.9375rem" }}>
          Choose your scenario, set your context, then practice with live AI coaching.
        </p>
      </div>

      {/* Scenario tabs */}
      <div className="scenario-grid" role="group" aria-label="Practice scenario">
        {SCENARIOS.map((s) => (
          <button key={s.id} className="choice-button" aria-pressed={scenario === s.id} onClick={() => chooseScenario(s.id)} style={{
            background: scenario === s.id ? "rgba(41,110,145,0.12)" : "rgba(255,255,255,0.8)",
            border: `1.5px solid ${scenario === s.id ? "var(--accent)" : "var(--border)"}`,
            borderRadius: "var(--radius-lg)", padding: "1.1rem", cursor: "pointer",
            color: "inherit", textAlign: "left", transition: "all 0.15s ease",
            display: "flex", flexDirection: "column", gap: "0.35rem"
          }}>
            <div style={{ color: scenario === s.id ? "var(--accent)" : "var(--muted)" }}>{s.icon}</div>
            <div style={{ fontWeight: 700, fontSize: "0.9375rem", marginTop: "0.2rem", color: scenario === s.id ? "#154f67" : "var(--text-1)" }}>{s.label}</div>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-3)", lineHeight: 1.4 }}>{s.desc}</div>
          </button>
        ))}
      </div>

      {/* Purpose mode */}
      <div className="card">
        <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-1)", marginBottom: "0.6rem" }}>Purpose Mode</div>
        <div className="selection-row" role="group" aria-label="Purpose mode">
          {(["practice", "evaluate"] as PurposeMode[]).map((m) => (
            <button key={m} className="choice-button" aria-pressed={purposeMode === m} onClick={() => setPurposeMode(m)} style={{
              padding: "0.4rem 1rem", borderRadius: "var(--radius-md)", cursor: "pointer",
              fontSize: "0.875rem", fontWeight: 600, border: "none",
              textTransform: "capitalize",
              transition: "all 0.15s ease"
            }}>
              {m}
            </button>
          ))}
        </div>
        <p style={{ fontSize: "0.8125rem", color: "var(--text-3)", marginTop: "0.5rem" }}>
          {purposeMode === "practice" ? "AI guides you with hints and encouragement." : "AI scores strictly and highlights every weakness explicitly."}
        </p>
      </div>

      <div className="two-column">
        {/* Persona */}
        <div className="card">
          <label htmlFor="persona" style={{ display: "block", marginBottom: "0.4rem", fontSize: "0.875rem", fontWeight: 700 }}>AI Persona</label>
          <select id="persona"
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="input"
            style={{ width: "100%", cursor: "pointer" }}
          >
            {PERSONAS.map(p => (
              <option key={p.id} value={p.id}>{p.label} - {p.desc}</option>
            ))}
          </select>
        </div>

        {/* Pressure Mode */}
        <div className="card">
          <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-1)", marginBottom: "0.6rem" }}>Pressure Level</div>
          <div className="selection-row" role="group" aria-label="Pressure level">
            {PRESSURE_LEVELS.map((p) => {
              const colors = ["#ffd63382", "#fb923c77", "#ff734d7d", "#fc060676"];
              const activeColor = colors[p.level];
              const isActive = pressureLevel === p.level;

              return (
                <button key={p.level} className="choice-button" aria-pressed={pressureLevel === p.level} onClick={() => setPressureLevel(p.level)} style={{
                  flex: 1, padding: "0.4rem 0", borderRadius: "var(--radius-md)", cursor: "pointer",
                  fontSize: "0.8125rem", fontWeight: 600, border: "none",
                  background: isActive ? activeColor : "rgba(255,255,255,0.7)",
                  color: isActive ? "#000" : "var(--text-2)",
                  boxShadow: isActive ? `0 0 12px ${activeColor}44` : "none",
                  transition: "all 0.15s ease",
                  opacity: isActive ? 1 : 0.8
                }}>
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {nudges.length > 0 && <div className="state-message error-message" role="alert">{nudges.map(n => <p key={n.id}>{n.message}</p>)}</div>}
      {/* Context form */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--ink)" }}>Session Context ({sc.contextLabel})</div>
        <div>
          <label htmlFor="title" style={{ fontSize: "0.8125rem", color: "var(--text-3)", display: "block", marginBottom: "0.3rem" }}>Session title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} className="input" />
        </div>
        <div className="two-column">
          <div>
            <label htmlFor="resumeText" style={{ fontSize: "0.8125rem", color: "var(--text-3)", display: "block", marginBottom: "0.3rem" }}>Resume / background</label>
            <textarea id="resumeText" value={resumeText} onChange={(e) => setResumeText(e.target.value)} rows={4} placeholder="Experience, skills, projects..." className="input" />
          </div>
          <div>
            <label htmlFor="jobDescription" style={{ fontSize: "0.8125rem", color: "var(--text-3)", display: "block", marginBottom: "0.3rem" }}>Role / audience / topic</label>
            <textarea id="jobDescription" value={jobDescription} onChange={(e) => setJobDescription(e.target.value)} rows={4} placeholder="Job description, pitch audience, stakeholders..." className="input" />
          </div>
          <div>
            <label htmlFor="topicNotes" style={{ fontSize: "0.8125rem", color: "var(--text-3)", display: "block", marginBottom: "0.3rem" }}>Topic notes</label>
            <textarea id="topicNotes" value={topicNotes} onChange={(e) => setTopicNotes(e.target.value)} rows={3} placeholder="Agenda, key points..." className="input" />
          </div>
          <div>
            <label htmlFor="freeText" style={{ fontSize: "0.8125rem", color: "var(--text-3)", display: "block", marginBottom: "0.3rem" }}>Extra instructions</label>
            <textarea id="freeText" value={freeText} onChange={(e) => setFreeText(e.target.value)} rows={3} placeholder="Anything extra for the AI to know..." className="input" />
          </div>
        </div>
        <div>
          <button onClick={start} className="btn btn-primary" style={{ padding: "0.6rem 1.4rem" }}>
            <span>Start {sc.label} Practice</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );

  // ── Live screen ──────────────────────────────────────────────────────────
  return (
    <div className="live-workspace">
      {/* Chat panel */}
      <div className="card live-chat" style={{ display: "flex", flexDirection: "column", padding: "1.25rem" }}>
        {/* Header */}
        <div className="live-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span className="animate-live" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#9a2540", display: "inline-block" }} />
              <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: "#9a2540", letterSpacing: "0.08em" }}>LIVE</span>
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{title}</div>
              <div style={{ fontSize: "0.8125rem", color: "var(--text-3)" }}>{sc.label} · {purposeMode}</div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>{fmtTime(elapsed)}</span>
            <button onClick={finish} disabled={status === "ending"} className="btn btn-danger" style={{ padding: "0.35rem 0.85rem", fontSize: "0.8125rem" }}>
              <CheckCircle2 size={14} />
              <span>{status === "ending" ? "Ending…" : "End & Analyze"}</span>
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="transcript" role="log" aria-label="Live transcript" aria-live="polite" tabIndex={0} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.75rem", paddingRight: "0.25rem" }}>
          {turns.length === 0 && (
            <div style={{ textAlign: "center", padding: "2.5rem 0", color: "var(--text-3)", fontSize: "0.875rem" }}>
              Connecting to AI coach…
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`animate-slide-up ${t.speaker === "user" ? "bubble-user" : "bubble-ai"}`}
              style={{ maxWidth: "85%", padding: "0.75rem 1rem", alignSelf: t.speaker === "user" ? "flex-end" : "flex-start" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-3)", marginBottom: "0.25rem", fontWeight: 700, textTransform: "uppercase" }}>
                {t.speaker === "ai" ? "Coach" : "You"}
              </div>
              <div style={{ fontSize: "0.9375rem", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{t.text}</div>
            </div>
          ))}
        </div>

        {/* Input */}
        <label htmlFor="response-draft" style={{ fontSize: "0.8125rem", fontWeight: 600, marginTop: "0.5rem", display: "block" }}>Your response</label>
        <div className="composer" style={{ display: "flex", gap: "0.5rem", marginTop: "0.35rem", flexShrink: 0 }}>
          <input id="response-draft" value={draft} onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Type a response or speak with mic…" className="input" style={{ flex: 1 }} />
          {canUseMic && (
            <button onClick={() => isStreamingMic ? stopMicStream() : void startMicStream()}
              className={`btn ${isStreamingMic ? "btn-danger" : "btn-ghost"}`} style={{ padding: "0.45rem 0.85rem" }}
              aria-label={isStreamingMic ? "Stop microphone" : "Start microphone"} aria-pressed={isStreamingMic} title="Microphone">
              {isStreamingMic ? <Square size={15} /> : <Mic size={15} />}
            </button>
          )}
          <button onClick={send} className="btn btn-primary" style={{ padding: "0.45rem 1rem" }}>
            <span>Send</span>
            <Send size={13} />
          </button>
        </div>
      </div>

      {/* Sidebar */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        {/* Camera */}
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-2)", marginBottom: "0.6rem" }}>Camera</div>
          <div style={{ borderRadius: "var(--radius-md)", overflow: "hidden", background: "#000", aspectRatio: "4/3" }}>
            <video aria-label="Your camera preview" ref={videoRef} muted playsInline style={{ width: "100%", height: "100%", objectFit: "cover", opacity: isStreamingVideo ? 1 : 0.2 }} />
            <canvas ref={canvasRef} style={{ display: "none" }} />
          </div>
          <button aria-pressed={isStreamingVideo} onClick={() => isStreamingVideo ? stopVideoStream() : void startVideoStream()}
            className={`btn ${isStreamingVideo ? "btn-danger" : "btn-ghost"}`}
            style={{ marginTop: "0.6rem", width: "100%", justifyContent: "center", fontSize: "0.8125rem", padding: "0.45rem 1rem" }}>
            {isStreamingVideo ? <VideoOff size={14} /> : <Video size={14} />}
            <span>{isStreamingVideo ? "Stop camera" : "Start camera"}</span>
          </button>

          {/* Arc gauges */}
          {visionMetrics && (
            <div style={{ display: "flex", justifyContent: "space-around", marginTop: "0.75rem" }}>
              <ArcGauge value={visionMetrics.eye_contact} label="Eye" color="#296e91" />
              <ArcGauge value={visionMetrics.posture === "good" ? 1 : visionMetrics.posture === "ok" ? 0.6 : 0.3} label="Posture" color="#285c3b" />
              <ArcGauge value={Math.max(0, 1 - visionMetrics.movement)} label="Steady" color="#735200" />
            </div>
          )}
        </div>

        {/* Nudges */}
        <div className="card" style={{ flex: 1, padding: "1rem", overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-2)", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#9a2540", display: "inline-block", boxShadow: "0 0 6px #9a2540" }} />
            Live Nudges
          </div>
          <style>{`
            @keyframes nudgeIn {
              from { opacity: 0; transform: translateY(-6px); }
              to   { opacity: 1; transform: translateY(0); }
            }
          `}</style>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", overflowY: "auto", flex: 1 }}>
            {nudges.length === 0 && (
              <div style={{ fontSize: "0.8125rem", color: "var(--text-3)", lineHeight: 1.5 }}>
                Vision signals and coaching cues will appear here as you speak.
              </div>
            )}
            {nudges.map((n) => {
              const isWarn = n.level === "warn";
              const isSuccess = n.level === "success";
              const ICON_MAP: Record<string, React.ReactNode> = {
                face: <Smile size={14} />,
                eye: <Eye size={14} />,
                posture: <Activity size={14} />,
                movement: <Move size={14} />,
                lighting: <Sun size={14} />,
                mic: <MicOff size={14} />,
                error: <AlertCircle size={14} />,
                system: <ArrowRight size={14} />
              };
              const color = isWarn ? "#735200" : isSuccess ? "#285c3b" : "var(--primary-lt)";
              const bg = isWarn ? "rgba(251,191,36,0.1)" : isSuccess ? "rgba(52,211,153,0.1)" : "rgba(255,255,255,0.7)";
              const border = isWarn ? "rgba(251,191,36,0.3)" : isSuccess ? "rgba(52,211,153,0.3)" : "var(--border)";
              return (
                <div key={n.id} style={{
                  padding: "0.5rem 0.75rem", borderRadius: "var(--radius-md)",
                  fontSize: "0.8125rem", lineHeight: 1.45,
                  background: bg, border: `1px solid ${border}`, color: "var(--ink)",
                  display: "flex", gap: "0.5rem", alignItems: "flex-start",
                  animation: "nudgeIn 0.25s ease",
                }}>
                  <span style={{ color, flexShrink: 0, marginTop: "0.15rem" }}>
                    {ICON_MAP[n.category] ?? <AlertCircle size={14} />}
                  </span>
                  <span style={{ flex: 1 }}>{n.message}</span>
                  <button onClick={() => setNudges(p => p.filter(x => x.id !== n.id))}
                    style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer",
                      color: "var(--text-3)", padding: "0.1rem", flexShrink: 0, display: "inline-flex", alignItems: "center" }}
                    aria-label="Dismiss coaching cue" title="Dismiss">
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
