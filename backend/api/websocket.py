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

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from db import AsyncSessionLocal
from models.schemas import Session, TranscriptSegment
from services.gemini import GeminiLiveSession, create_gemini_live_session
from services.scenarios import normalize_persona, normalize_pressure_level
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
    1. Collapse whitespace and deduplicate adjacent identical words.
    2. Collapse repeated n-gram phrases.
    Mirrors cleanTranscript() in live.ts.
    """
    raw_words = text.split()
    cleaned: list[str] = []
    for word in raw_words:
        if cleaned and cleaned[-1].lower() == word.lower():
            continue
        cleaned.append(word)

    # N-gram deduplication
    for size in range(6, 1, -1):
        compacted: list[str] = []
        i = 0
        while i < len(cleaned):
            prev = " ".join(compacted[-size:]).lower() if len(compacted) >= size else ""
            curr = " ".join(cleaned[i:i + size]).lower() if i + size <= len(cleaned) else ""
            if prev and prev == curr:
                i += size
            else:
                compacted.append(cleaned[i])
                i += 1
        cleaned = compacted

    return " ".join(cleaned)


def _send_live_nudges_sync(text: str, stats: dict) -> Optional[dict]:
    """
    Check for filler words and WPM; return a nudge message if one should be sent.
    Returns the nudge dict or None. (Async send is done by the caller.)
    """
    fillers = len(re.findall(r"\b(um+|uh+|like|you know)\b", text, re.IGNORECASE))
    if fillers >= 3:
        return {"type": "nudge", "level": "info", "message": "Quick nudge: try pausing instead of filler words."}

    stats["words"] += len(text.split())
    minutes = (time.time() - stats["start"]) / 60
    if minutes <= 0.6:
        return None

    wpm = stats["words"] / minutes
    if wpm > 175:
        return {"type": "nudge", "level": "warn", "message": "You're speaking a bit fast — slow down slightly."}
    elif wpm < 105:
        return {"type": "nudge", "level": "info", "message": "You can speed up slightly to sound more confident."}
    return None


# ── Main WebSocket handler ─────────────────────────────────────────────────────

async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    stats: dict = {"start": time.time(), "words": 0}
    live_session: Optional[GeminiLiveSession] = None
    bound_session_id: Optional[str] = None
    ai_text_buffer: str = ""
    user_audio_text_buffer: str = ""

    await _send(ws, {"type": "ready"})

    async def close_live_session() -> None:
        nonlocal live_session, ai_text_buffer, user_audio_text_buffer
        if live_session:
            await live_session.close()
            live_session = None
        ai_text_buffer = ""
        user_audio_text_buffer = ""

    async def ensure_live_session(session_id: str) -> Optional[GeminiLiveSession]:
        nonlocal live_session, bound_session_id, ai_text_buffer, user_audio_text_buffer

        if live_session and bound_session_id == session_id:
            return live_session

        await close_live_session()

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

        if not session:
            return None

        persona_id = normalize_persona(session.persona)
        pressure_level = normalize_pressure_level(session.pressureLevel)
        ctx = session.contextJson or None
        scenario = session.scenario
        bound_session_id = session_id

        # ── Handlers ──

        def on_input_text(text: str) -> None:
            nonlocal user_audio_text_buffer
            user_audio_text_buffer += _transcript_delta(user_audio_text_buffer, text)

        def on_text(text: str) -> None:
            nonlocal ai_text_buffer
            ai_text_buffer += _transcript_delta(ai_text_buffer, text)

        async def on_audio(audio: dict) -> None:
            await _send(ws, {"type": "ai_audio", "data": audio["data"], "mimeType": audio["mimeType"]})

        async def on_turn_complete() -> None:
            nonlocal user_audio_text_buffer, ai_text_buffer

            user_audio_text = user_audio_text_buffer.strip()
            user_audio_text_buffer = ""
            if user_audio_text and bound_session_id:
                clean_user = _clean_transcript(user_audio_text)
                async with AsyncSessionLocal() as db:
                    seg = TranscriptSegment(
                        id=cuid_generate(),
                        sessionId=bound_session_id,
                        speaker="user",
                        text=clean_user,
                    )
                    db.add(seg)
                    await db.commit()
                nudge = _send_live_nudges_sync(user_audio_text, stats)
                if nudge:
                    await _send(ws, nudge)
                await _send(ws, {"type": "user_text", "text": clean_user})

            ai_text = ai_text_buffer.strip()
            ai_text_buffer = ""
            if not ai_text or not bound_session_id:
                return

            clean_ai = _clean_transcript(ai_text)
            async with AsyncSessionLocal() as db:
                seg = TranscriptSegment(
                    id=cuid_generate(),
                    sessionId=bound_session_id,
                    speaker="ai",
                    text=clean_ai,
                )
                db.add(seg)
                await db.commit()
            await _send(ws, {"type": "ai_text", "text": clean_ai})

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
        )
        return live_session

    # ── Receive loop ──

    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
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

            # ── hello: bind session ──
            if msg_type == "hello":
                if not session_id:
                    await _send(ws, {"type": "error", "message": "missing_session_id"})
                    continue
                bound_session_id = session_id
                logger.info(f"[ws] received hello for session: {session_id}")
                continue

            # ── Guard: session hijacking prevention ──
            if bound_session_id and session_id != bound_session_id:
                logger.warn("[ws] sessionId mismatch", {"bound": bound_session_id, "received": session_id})
                await _send(ws, {"type": "error", "message": "session_id_mismatch"})
                continue

            if not session_id:
                await _send(ws, {"type": "error", "message": "missing_session_id"})
                continue

            try:
                session = await ensure_live_session(session_id)
                if not session:
                    await _send(ws, {"type": "error", "message": "session_not_found"})
                    continue

                if msg_type == "audio_chunk":
                    data = parsed.get("data", "")
                    mime = parsed.get("mimeType", "audio/pcm;rate=16000")
                    audio_buffer_store.append(session_id, data)
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
                    nudge = _send_live_nudges_sync(text, stats)
                    if nudge:
                        await _send(ws, nudge)
                    async with AsyncSessionLocal() as db:
                        seg = TranscriptSegment(
                            id=cuid_generate(),
                            sessionId=session_id,
                            speaker="user",
                            text=text,
                        )
                        db.add(seg)
                        await db.commit()
                    await session.send_text(text)

            except Exception as e:
                logger.error("[ws] message handler error", str(e))
                await _send(ws, {"type": "error", "message": "live_session_failed"})

    finally:
        await close_live_session()
