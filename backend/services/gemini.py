"""
Gemini Live WebSocket session manager.
Port of services/geminiLive.ts.

Opens a persistent WebSocket to the Gemini BidiGenerateContent endpoint,
buffers outgoing messages until the setup handshake completes, and
routes incoming events to caller-supplied handlers.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Awaitable, Callable, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from services.context import StructuredContext, format_context_for_prompt
from services.scenarios import (
    SCENARIO_CONFIG,
    get_persona,
    get_pressure_modifier,
    normalize_scenario,
)
from utils.logger import logger

# ── Constants ──────────────────────────────────────────────────────────────────

GEMINI_LIVE_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)


def _live_model() -> str:
    return os.environ.get("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")


# ── System instruction builder ─────────────────────────────────────────────────

def build_system_instruction(
    scenario: str,
    context: Optional[StructuredContext] = None,
    persona_id: Optional[str] = None,
    pressure_level: Optional[int] = None,
) -> str:
    norm_scenario = normalize_scenario(scenario)
    config = SCENARIO_CONFIG[norm_scenario]
    persona = get_persona(persona_id)
    pressure_modifier = get_pressure_modifier(pressure_level)

    persona_block = f"\n\n{persona.modifier}" if persona.modifier else ""
    pressure_block = f"\n\n{pressure_modifier}" if pressure_modifier else ""

    return (
        f"You are a {config.ai_role} running a realistic {config.label.lower()} simulation.\n"
        "- Keep responses concise.\n"
        "- Ask one question at a time.\n"
        "- Adapt dynamically based on the user's last answer.\n"
        "- Use the session context when relevant, but do not mention that you have it.\n"
        "- Avoid being judgmental; sound professional.\n"
        f"- Opening behavior: {config.opening_prompt}\n"
        f"- Live goals: {'; '.join(config.live_goals)}.\n"
        f"- Evaluate for: {', '.join(config.evaluation_focus)}."
        f"{persona_block}{pressure_block}{format_context_for_prompt(context)}"
    )


def _setup_message(
    scenario: str,
    context: Optional[StructuredContext],
    persona_id: Optional[str],
    pressure_level: Optional[int],
) -> dict:
    return {
        "setup": {
            "model": f"models/{_live_model()}",
            "generation_config": {"response_modalities": ["AUDIO"]},
            "system_instruction": {
                "parts": [{"text": build_system_instruction(scenario, context, persona_id, pressure_level)}]
            },
        }
    }


# ── Response parsing helpers ────────────────────────────────────────────────────

def _extract_text(response: dict) -> str:
    server_content = response.get("serverContent", {})
    parts = server_content.get("modelTurn", {}).get("parts", [])
    model_text = "".join(p.get("text", "") for p in parts if isinstance(p.get("text"), str))
    transcription = server_content.get("outputTranscription", {}).get("text", "")
    return model_text or (transcription if isinstance(transcription, str) else "")


def _extract_input_text(response: dict) -> str:
    transcription = response.get("serverContent", {}).get("inputTranscription", {}).get("text", "")
    return transcription if isinstance(transcription, str) else ""


def _extract_audio(response: dict) -> list[dict]:
    parts = response.get("serverContent", {}).get("modelTurn", {}).get("parts", [])
    results = []
    for part in parts:
        inline = part.get("inlineData")
        if inline and isinstance(inline.get("data"), str):
            results.append({
                "data": inline["data"],
                "mimeType": inline.get("mimeType", "audio/pcm;rate=24000"),
            })
    return results


# ── GeminiLiveSession class ────────────────────────────────────────────────────

class GeminiLiveSession:
    """
    Wraps a long-lived WebSocket connection to Gemini Live.
    All send methods are thread-safe (they schedule work on the event loop).
    """

    def __init__(
        self,
        scenario: str,
        context: Optional[StructuredContext],
        on_text: Callable[[str], Awaitable[None] | None],
        on_input_text: Optional[Callable[[str], Awaitable[None] | None]] = None,
        on_audio: Optional[Callable[[dict], Awaitable[None] | None]] = None,
        on_turn_complete: Optional[Callable[[], Awaitable[None] | None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        persona_id: Optional[str] = None,
        pressure_level: Optional[int] = None,
    ) -> None:
        self._scenario = scenario
        self._context = context
        self._persona_id = persona_id
        self._pressure_level = pressure_level

        self._on_text = on_text
        self._on_input_text = on_input_text
        self._on_audio = on_audio
        self._on_turn_complete = on_turn_complete
        self._on_error = on_error

        self._ws: Optional[ClientConnection] = None
        self._setup_complete = False
        self._pending: list[str] = []
        self._closed = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Open the upstream WebSocket and begin the receive loop."""
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini Live sessions")

        url = f"{GEMINI_LIVE_ENDPOINT}?key={key}"
        self._ws = await websockets.connect(url)

        # Send setup immediately
        await self._ws.send(json.dumps(_setup_message(
            self._scenario, self._context, self._persona_id, self._pressure_level
        )))

        # Start the receive loop as a background task
        self._task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    response = json.loads(raw)
                except json.JSONDecodeError:
                    logger.error("[gemini-live] failed to parse message")
                    continue

                if response.get("setupComplete"):
                    self._setup_complete = True
                    for msg in self._pending:
                        await self._ws.send(msg)
                    self._pending.clear()
                    continue

                text = _extract_text(response)
                if text:
                    result = self._on_text(text)
                    if asyncio.iscoroutine(result):
                        await result

                input_text = _extract_input_text(response)
                if input_text and self._on_input_text:
                    result = self._on_input_text(input_text)
                    if asyncio.iscoroutine(result):
                        await result

                for audio in _extract_audio(response):
                    if self._on_audio:
                        result = self._on_audio(audio)
                        if asyncio.iscoroutine(result):
                            await result

                if response.get("serverContent", {}).get("turnComplete") and self._on_turn_complete:
                    result = self._on_turn_complete()
                    if asyncio.iscoroutine(result):
                        await result

        except websockets.exceptions.ConnectionClosedError as e:
            if not self._closed and self._on_error:
                self._on_error(f"gemini_live_closed:{e.code}:{e.reason}")
        except Exception as e:
            logger.error("[gemini-live] receive loop error", str(e))
            if self._on_error:
                self._on_error("gemini_live_message_failed")

    async def _send_json(self, payload: dict) -> None:
        msg = json.dumps(payload)
        if self._ws and self._setup_complete:
            await self._ws.send(msg)
        else:
            self._pending.append(msg)

    async def send_text(self, text: str) -> None:
        await self._send_json({
            "clientContent": {
                "turns": [{"role": "user", "parts": [{"text": text}]}],
                "turnComplete": True,
            }
        })

    async def send_audio(self, data: str, mime_type: str = "audio/pcm;rate=16000") -> None:
        await self._send_json({
            "realtimeInput": {"audio": {"data": data, "mimeType": mime_type}}
        })

    async def send_video(self, data: str, mime_type: str = "image/jpeg") -> None:
        await self._send_json({
            "realtimeInput": {"video": {"data": data, "mimeType": mime_type}}
        })

    async def end_audio(self) -> None:
        # Signal end of audio stream if the protocol supports it
        pass

    async def close(self) -> None:
        self._closed = True
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()


async def create_gemini_live_session(
    scenario: str,
    context: Optional[StructuredContext],
    on_text: Callable[[str], Awaitable[None] | None],
    on_input_text: Optional[Callable[[str], Awaitable[None] | None]] = None,
    on_audio: Optional[Callable[[dict], Awaitable[None] | None]] = None,
    on_turn_complete: Optional[Callable[[], Awaitable[None] | None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    persona_id: Optional[str] = None,
    pressure_level: Optional[int] = None,
) -> GeminiLiveSession:
    """Factory: creates and starts a GeminiLiveSession."""
    session = GeminiLiveSession(
        scenario=scenario,
        context=context,
        on_text=on_text,
        on_input_text=on_input_text,
        on_audio=on_audio,
        on_turn_complete=on_turn_complete,
        on_error=on_error,
        persona_id=persona_id,
        pressure_level=pressure_level,
    )
    await session.start()
    return session
