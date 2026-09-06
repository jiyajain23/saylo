"""
Minimal structured logger.
Uses Python's standard logging under the hood.
Log level is controlled by the LOG_LEVEL env var (debug | info | warn | error).
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_configured = os.environ.get("LOG_LEVEL", "info").lower()
_min_level = _LEVEL_MAP.get(_configured, logging.INFO)


def _log(level: str, message: str, meta=None) -> None:
    numeric = _LEVEL_MAP.get(level, logging.INFO)
    if numeric < _min_level:
        return

    entry: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    if meta is not None:
        entry["meta"] = meta

    line = json.dumps(entry, default=str)

    if level == "error":
        print(line, file=sys.stderr, flush=True)
    else:
        print(line, flush=True)


class _Logger:
    def debug(self, msg: str, meta=None) -> None:
        _log("debug", msg, meta)

    def info(self, msg: str, meta=None) -> None:
        _log("info", msg, meta)

    def warn(self, msg: str, meta=None) -> None:
        _log("warn", msg, meta)

    def error(self, msg: str, meta=None) -> None:
        _log("error", msg, meta)


logger = _Logger()
