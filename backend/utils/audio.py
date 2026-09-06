"""
In-memory store for raw audio chunks during a live session.
Chunks are stored as Base64 strings (as received from the client) and
concatenated at the byte level when popped for analysis.
"""

import base64
from typing import Optional

from utils.logger import logger


class AudioBufferStore:
    def __init__(self) -> None:
        self._buffers: dict[str, list[str]] = {}

    def append(self, session_id: str, b64_chunk: str) -> None:
        if session_id not in self._buffers:
            self._buffers[session_id] = []
        self._buffers[session_id].append(b64_chunk)

    def pop(self, session_id: str) -> Optional[str]:
        """
        Concatenates all chunks for a session into a single Base64 string.
        Assumes chunks are valid PCM data that can be concatenated at byte level.
        Returns None if no data or session is unknown.
        """
        if not session_id:
            return None
        chunks = self._buffers.pop(session_id, None)
        if not chunks:
            return None

        try:
            raw = b"".join(base64.b64decode(c) for c in chunks)
            return base64.b64encode(raw).decode("ascii")
        except Exception as err:
            logger.error("[audio-store] failed to concatenate chunks", {"session_id": session_id, "err": str(err)})
            return None

    def clear(self, session_id: str) -> None:
        self._buffers.pop(session_id, None)


# Singleton used across the app
audio_buffer_store = AudioBufferStore()
