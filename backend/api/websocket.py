"""
WebSocket handler for Gemini Live sessions.
Port of websocket/live.ts.

Endpoint: ws://host/ws
Message protocol:
  Inbound:  hello | user_text | audio_chunk | audio_end | video_frame
  Outbound: ready | user_text | ai_text | ai_audio | nudge | error
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update, func

from db import AsyncSessionLocal
from models.schemas import Session, TranscriptSegment
from services.gemini import GeminiLiveSession, create_gemini_live_session
from services.scenarios import normalize_persona, normalize_pressure_level
from services import completion
from services.auth import verify_access_token
from services.origins import allowed_origins
from services.limits import SESSION_SECONDS, MAX_WS_BYTES, MAX_TRANSCRIPT_CHARS
from services.storage import AudioStorage
from datetime import datetime
from utils.audio import audio_buffer_store
from utils.logger import logger
from cuid2 import cuid_wrapper

cuid_generate = cuid_wrapper()


# ── Utilities ──────────────────────────────────────────────────────────────────

async def _send(ws: WebSocket, msg: dict) -> None:
    try:
        await ws.send_text(json.dumps(msg))
    except Exception:
        pass


def _transcript_delta(current: str, next_text: str) -> str:
    """
    Return only the new portion of next_text not already present in current.
    Mirrors transcriptDelta() in live.ts.
    """
    if not current:
        return next_text
    if not next_text or next_text == current or current.endswith(next_text):
        return ""
    if next_text.startswith(current):
        return next_text[len(current):]

    max_overlap = min(len(current), len(next_text))
    for length in range(max_overlap, 0, -1):
        if current.endswith(next_text[:length]):
            return next_text[length:]

    return next_text


def _clean_transcript(text: str) -> str:
    """
    Normalize display whitespace without changing the words being evaluated.
    """
    # Repetition is part of speech delivery (including repeated filler words).
    # Removing words here would bias the downstream speech metrics.
    return " ".join(text.split())


def _send_live_nudges_sync(text: str, stats: dict, duration_seconds: Optional[float] = None) -> Optional[dict]:
    """
    Check for filler words and WPM; return a nudge message if one should be sent.
    Returns the nudge dict or None. (Async send is done by the caller.)
    """
    fillers = len(re.findall(r"\b(um+|uh+|like|you know)\b", text, re.IGNORECASE))
    if fillers >= 3:
        return {"type": "nudge", "level": "info", "message": "Quick nudge: try pausing instead of filler words."}

    # Wall-clock session time includes AI replies and waiting. It is not the
    # user's speaking duration. Typed/untimed turns only receive filler nudges.
    if duration_seconds is None or duration_seconds <= 0:
        return None
    stats["words"] += len(text.split())
    stats["speech_seconds"] = stats.get("speech_seconds", 0) + duration_seconds
    if stats["speech_seconds"] < 10:
        return None
    wpm = stats["words"] / (stats["speech_seconds"] / 60)
    if wpm > 175:
        return {"type": "nudge", "level": "warn", "message": "You're speaking a bit fast — slow down slightly."}
    elif wpm < 105:
        return {"type": "nudge", "level": "info", "message": "You can speed up slightly to sound more confident."}
    return None


# ── Main WebSocket handler ─────────────────────────────────────────────────────

async def websocket_endpoint(ws: WebSocket) -> None:
    if ws.headers.get("origin") not in allowed_origins():
        await ws.close(code=1008)
        return
    await ws.accept()

    # Authenticate and check ownership before binding, media, Gemini calls, or
    # completion registration. Tokens are never put in URLs or logs.
    try:
        raw_hello = await asyncio.wait_for(ws.receive_text(), timeout=10)
        if len(raw_hello) > 16384:
            raise ValueError()
        hello = json.loads(raw_hello)
        if not isinstance(hello, dict) or hello.get("type") != "hello" or not hello.get("accessToken"):
            raise ValueError()
        principal = await verify_access_token(hello["accessToken"])
        if principal.expires_at <= time.time():
            raise ValueError()
        session_id = hello.get("sessionId")
        if not isinstance(session_id, str):
            raise ValueError()
        async with AsyncSessionLocal() as db:
            owned = await db.scalar(select(Session).where(Session.id == session_id, Session.userId == principal.id))
        if not owned or owned.status != "LIVE":
            raise ValueError()
    except (TimeoutError, ValueError, HTTPException, WebSocketDisconnect, TypeError) as auth_err:
        logger.warn(f"[ws] handshake failed: {type(auth_err).__name__}: {auth_err}")
        await _send(ws, {"type": "error", "message": "authentication_failed"})
        await ws.close(code=1008)
        return

    deadline = time.monotonic() + max(0, SESSION_SECONDS - (datetime.utcnow() - owned.createdAt).total_seconds())
    last_heartbeat = 0.0
    storage_ready = False
    rate_start, audio_rate_count, control_rate_count = time.monotonic(), 0, 0
    total_text = 0
    async with AsyncSessionLocal() as db:
        total_text = await db.scalar(select(func.coalesce(func.sum(func.length(TranscriptSegment.text)), 0))
                                     .where(TranscriptSegment.sessionId == session_id))
    if not completion.bind(session_id):
        await _send(ws, {"type": "error", "message": "live_connection_limit"})
        await ws.close(code=1008)
        return

    stats: dict = {"start": time.time(), "words": 0}
    live_session: Optional[GeminiLiveSession] = None
    bound_session_id: Optional[str] = session_id
    ai_text_buffer: str = ""
    user_audio_text_buffer: str = ""
    timing_intervals: list[tuple[float, float]] = []
    timing_complete = True
    finishing = False
    finished = False
    finish_lock = asyncio.Lock()
    transcript_lock = asyncio.Lock()
    flush_transcript = None
    transcript_failed = False

    def reserve_text(text):
        nonlocal total_text, transcript_failed
        if total_text + len(text) > MAX_TRANSCRIPT_CHARS:
            transcript_failed = True
            raise ValueError("transcript_limit")
        total_text += len(text)

    async def finish_connection() -> None:
        nonlocal finishing, finished
        async with finish_lock:
            if finished:
                return
            finishing = True
            started_at = time.monotonic()
            logger.info("[ws] finalization started", {"sessionId": bound_session_id})
            try:
                if transcript_failed:
                    raise RuntimeError("transcript_limit")
                if live_session:
                    await live_session.finish_input()
                if transcript_failed:
                    raise RuntimeError("transcript_limit")
                if flush_transcript:
                    await flush_transcript()
                finished = True
                logger.info("[ws] finalization completed", {
                    "sessionId": bound_session_id,
                    "durationMs": round((time.monotonic() - started_at) * 1000),
                })
            except BaseException as exc:
                finishing = False
                logger.warn("[ws] finalization failed", {
                    "sessionId": bound_session_id,
                    "durationMs": round((time.monotonic() - started_at) * 1000),
                    "errorType": type(exc).__name__,
                })
                raise

    await _send(ws, {"type": "ready"})
    completion.register(session_id, finish_connection)

    async def close_live_session() -> None:
        nonlocal live_session, ai_text_buffer, user_audio_text_buffer
        if live_session:
            await live_session.close()
            live_session = None
        ai_text_buffer = ""
        user_audio_text_buffer = ""

    async def ensure_live_session(session_id: str) -> Optional[GeminiLiveSession]:
        nonlocal live_session, bound_session_id, ai_text_buffer, user_audio_text_buffer, flush_transcript

        if live_session and bound_session_id == session_id:
            return live_session

        await close_live_session()

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Session).where(Session.id == session_id, Session.userId == principal.id))
            session = result.scalar_one_or_none()

        if not session or session.status != "LIVE":
            return None

        persona_id = normalize_persona(session.persona)
        pressure_level = normalize_pressure_level(session.pressureLevel)
        ctx = session.contextJson or None
        scenario = session.scenario
        bound_session_id = session_id
        completion.register(session_id, finish_connection)

        # ── Handlers ──

        def on_input_text(text: str) -> None:
            nonlocal user_audio_text_buffer
            reserve_text(text)
            user_audio_text_buffer += text

        def on_input_timing(timing: dict) -> None:
            nonlocal timing_complete
            start, end = timing.get("start"), timing.get("end")
            if start is None or end is None or end <= start:
                timing_complete = False
            else:
                timing_intervals.append((start, end))

        def on_text(text: str) -> None:
            nonlocal ai_text_buffer
            delta = _transcript_delta(ai_text_buffer, text)
            reserve_text(delta)
            ai_text_buffer += delta

        async def on_audio(audio: dict) -> None:
            await _send(ws, {"type": "ai_audio", "data": audio["data"], "mimeType": audio["mimeType"]})

        async def on_turn_complete() -> None:
            nonlocal user_audio_text_buffer, ai_text_buffer, timing_complete
            async with transcript_lock:
                user_snapshot, ai_snapshot = user_audio_text_buffer, ai_text_buffer
                if not bound_session_id or not (user_snapshot.strip() or ai_snapshot.strip()):
                    return
                timings = list(timing_intervals)
                rows = []
                for speaker, text in (("user", user_snapshot), ("ai", ai_snapshot)):
                    if text.strip():
                        rows.append(TranscriptSegment(
                            id=cuid_generate(), sessionId=bound_session_id, speaker=speaker,
                            text=_clean_transcript(text), createdAt=datetime.utcnow(),
                            audioStartSeconds=min(s for s, _ in timings) if speaker == "user" and timing_complete and timings else None,
                            audioEndSeconds=max(e for _, e in timings) if speaker == "user" and timing_complete and timings else None))
                async with AsyncSessionLocal() as db:
                    db.add_all(rows)
                    await db.commit()
                user_audio_text_buffer = user_audio_text_buffer[len(user_snapshot):]
                ai_text_buffer = ai_text_buffer[len(ai_snapshot):]
                del timing_intervals[:len(timings)]
                timing_complete = True
                for row in rows:
                    await _send(ws, {"type": f"{row.speaker}_text", "text": row.text})
                    if row.speaker == "user":
                        duration = row.audioEndSeconds - row.audioStartSeconds if row.audioStartSeconds is not None else None
                        nudge = _send_live_nudges_sync(row.text, stats, duration)
                        if nudge:
                            await _send(ws, nudge)

        flush_transcript = on_turn_complete

        def on_error(message: str) -> None:
            asyncio.create_task(_send(ws, {"type": "error", "message": message}))

        live_session = await create_gemini_live_session(
            scenario=scenario,
            context=ctx,
            on_text=on_text,
            on_input_text=on_input_text,
            on_audio=on_audio,
            on_turn_complete=on_turn_complete,
            on_error=on_error,
            persona_id=persona_id,
            pressure_level=pressure_level,
            on_input_timing=on_input_timing,
        )
        return live_session

    # ── Receive loop ──

    try:
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                async with AsyncSessionLocal() as db:
                    await db.execute(update(Session).where(Session.id == bound_session_id, Session.userId == principal.id,
                        Session.status == "LIVE").values(liveHeartbeatAt=datetime.utcnow()))
                    await db.commit()
                last_heartbeat = now
            if now >= deadline and not finished:
                # End the same way as the button; do not silently cut off final ASR.
                await finish_connection()
                from api.sessions import end_session
                async with AsyncSessionLocal() as db:
                    await end_session(bound_session_id, db, principal)
                await _send(ws, {"type": "session_ended"})
                await ws.close(code=1000)
                break
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=max(.01, min(15, principal.expires_at - time.time(),
                    deadline - time.monotonic() if not finished else 15)))
            except WebSocketDisconnect:
                break
            except TimeoutError:
                if principal.expires_at <= time.time():
                    await _send(ws, {"type": "error", "message": "access_token_expired"})
                    await ws.close(code=1008)
                    break
                if finished and time.monotonic() > deadline + 120:
                    break
                continue
            if principal.expires_at <= time.time():
                await ws.close(code=1008)
                break
            if len(raw.encode("utf-8")) > MAX_WS_BYTES:
                await _send(ws, {"type": "error", "message": "payload_too_large"})
                await ws.close(code=1009)
                break
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, {"type": "error", "message": "invalid_json"})
                continue

            if not isinstance(parsed, dict) or "type" not in parsed:
                await _send(ws, {"type": "error", "message": "invalid_message"})
                continue

            msg_type = parsed.get("type")
            session_id = parsed.get("sessionId", "")

            # AudioWorklet/ScriptProcessor cadence varies by browser and can
            # exceed 100 messages/sec. Bound media and control traffic
            # separately; the audio byte cap remains the primary resource limit.
            if time.monotonic() - rate_start >= 1:
                rate_start, audio_rate_count, control_rate_count = time.monotonic(), 0, 0
            if msg_type == "audio_chunk":
                audio_rate_count += 1
                if audio_rate_count > 600:
                    await _send(ws, {"type": "error", "message": "message_rate_limit"})
                    await ws.close(code=1008)
                    break
            else:
                control_rate_count += 1
                if control_rate_count > 40:
                    await _send(ws, {"type": "error", "message": "message_rate_limit"})
                    await ws.close(code=1008)
                    break

            # ── hello: bind session ──
            if msg_type == "hello":
                await _send(ws, {"type": "error", "message": "already_authenticated"})
                await ws.close(code=1008)
                break

            # ── Guard: session hijacking prevention ──
            if bound_session_id and session_id != bound_session_id:
                logger.warn("[ws] sessionId mismatch", {"bound": bound_session_id, "received": session_id})
                await _send(ws, {"type": "error", "message": "session_id_mismatch"})
                continue

            if not session_id:
                await _send(ws, {"type": "error", "message": "missing_session_id"})
                continue

            try:
                if msg_type == "audio_end" and parsed.get("final"):
                    try:
                        await finish_connection()
                        await _send(ws, {"type": "audio_ended", "requestId": parsed.get("requestId"), "ok": True})
                    except (TimeoutError, RuntimeError):
                        await _send(ws, {"type": "audio_ended", "requestId": parsed.get("requestId"), "ok": False,
                                         "message": "final_turn_not_confirmed"})
                    continue
                if finishing or finished:
                    await _send(ws, {"type": "error", "message": "session_finishing"})
                    continue
                session = await ensure_live_session(session_id)
                if not session:
                    await _send(ws, {"type": "error", "message": "session_not_found"})
                    continue

                if msg_type == "audio_chunk":
                    data = parsed.get("data", "")
                    mime = parsed.get("mimeType", "audio/pcm;rate=16000")
                    if mime != "audio/pcm;rate=16000":
                        raise ValueError("unsupported_audio_format")
                    if not storage_ready:
                        await AudioStorage().check_private()
                        storage_ready = True
                    first_audio = audio_buffer_store.size(session_id) == 0
                    size = audio_buffer_store.append(session_id, data)
                    if first_audio:
                        # Durable marker prevents text-only success after a crash
                        # loses the gateway's temporary recording.
                        async with AsyncSessionLocal() as db:
                            await db.execute(update(Session).where(Session.id == session_id, Session.userId == principal.id)
                                             .values(audioBytes=size))
                            await db.commit()
                    await session.send_audio(data, mime)

                elif msg_type == "audio_end":
                    await session.end_audio()

                elif msg_type == "video_frame":
                    data = parsed.get("data", "")
                    mime = parsed.get("mimeType", "image/jpeg")
                    await session.send_video(data, mime)

                elif msg_type == "user_text":
                    text = str(parsed.get("text", ""))[:4000]
                    if not text:
                        continue
                    # The UI's opening instruction is control input, not a
                    # candidate answer. Legacy messages still default to answers.
                    if not parsed.get("isControl", False):
                        reserve_text(text)
                        nudge = _send_live_nudges_sync(text, stats)
                        if nudge:
                            await _send(ws, nudge)
                        async with AsyncSessionLocal() as db:
                            seg = TranscriptSegment(
                                id=cuid_generate(), sessionId=session_id, speaker="user",
                                text=text, createdAt=datetime.utcnow())
                            db.add(seg)
                            await db.commit()
                    await session.send_text(text)

            except Exception as e:
                logger.error(f"[ws] message handler error: {type(e).__name__}: {e}")
                err_msg = str(e) if str(e) else type(e).__name__
                await _send(ws, {"type": "error", "message": f"live_session_failed: {err_msg}"})
                await ws.close(code=1011)
                break

    finally:
        async with finish_lock:
            # Cancel upstream reads before flushing any already-received partial
            # transcript on abrupt disconnect. Do not discard buffered words.
            if live_session:
                await live_session.close()
            try:
                if flush_transcript:
                    await flush_transcript()
            finally:
                if bound_session_id:
                    completion.unregister(bound_session_id, finish_connection)
                    completion.release(bound_session_id)
                    async with AsyncSessionLocal() as db:
                        await db.execute(update(Session).where(Session.id == bound_session_id, Session.userId == principal.id,
                            Session.status == "LIVE").values(status="ENDED" if finished else "FAILED",
                            failureCode=None if finished else "live_connection_interrupted"))
                        await db.commit()
                    if finished:
                        audio_buffer_store.seal(bound_session_id)
                    else:
                        audio_buffer_store.clear(bound_session_id)
