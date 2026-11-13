"""Bounded PCM files. No full-session base64 list or decode/join copy."""
import base64
import tempfile
import time
from pathlib import Path


class AudioBufferStore:
    def __init__(self, directory=None, max_bytes=None):
        from services.limits import MAX_AUDIO_BYTES, MAX_LIVE_CONNECTIONS
        self.directory = Path(directory or (Path(tempfile.gettempdir()) / "saylo-audio"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes if max_bytes is not None else MAX_AUDIO_BYTES
        self.max_files = MAX_LIVE_CONNECTIONS
        self._files = {}

    def append(self, session_id, b64_chunk):
        if not isinstance(b64_chunk, str) or len(b64_chunk) > 65536:
            raise ValueError("audio_chunk_too_large")
        raw = base64.b64decode(b64_chunk, validate=True)
        if not raw or len(raw) % 2:
            raise ValueError("invalid_pcm")
        entry = self._files.get(session_id)
        size = entry[1] if entry else 0
        if size + len(raw) > self.max_bytes:
            raise ValueError("audio_duration_limit")
        if not entry:
            if len(self._files) >= self.max_files:
                raise ValueError("audio_capacity_reached")
            # NamedTemporaryFile securely creates only files owned by this store.
            handle = tempfile.NamedTemporaryFile(prefix="saylo-", suffix=".pcm", dir=self.directory, delete=False)
            entry = [Path(handle.name), 0, handle]
            self._files[session_id] = entry
        if entry[2] is None:
            raise ValueError("audio_already_sealed")
        entry[2].write(raw)
        entry[1] += len(raw)
        return entry[1]

    def size(self, session_id):
        entry = self._files.get(session_id)
        return entry[1] if entry else 0

    def seal(self, session_id):
        entry = self._files.get(session_id)
        if not entry:
            return None
        if entry[2] is not None:
            entry[2].close()
            entry[2] = None
        return entry[0]

    def clear(self, session_id):
        path = self.seal(session_id)
        if path:
            path.unlink(missing_ok=True)
        self._files.pop(session_id, None)

    def cleanup(self, age_seconds=3600):
        # Scan only this application's generated files; never follow symlinks.
        for session_id, entry in list(self._files.items()):
            if entry[2] is None and time.time() - entry[0].stat().st_mtime > age_seconds:
                self.clear(session_id)
        active = {entry[0] for entry in self._files.values()}
        for path in self.directory.glob("saylo-*.pcm"):
            if path.is_symlink() or path in active:
                continue
            if path.is_file() and time.time() - path.stat().st_mtime > age_seconds:
                path.unlink(missing_ok=True)


audio_buffer_store = AudioBufferStore()
