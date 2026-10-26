"""Coordinate REST completion with active sockets in this single gateway.

Durable, cross-process job coordination belongs to Phase 3. Database CAS remains
the final idempotency boundary; this registry only drains active live I/O.
"""
import asyncio
from collections.abc import Awaitable, Callable

_connections: dict[str, set[Callable[[], Awaitable[None]]]] = {}


def register(session_id: str, finish: Callable[[], Awaitable[None]]) -> None:
    _connections.setdefault(session_id, set()).add(finish)


def unregister(session_id: str, finish: Callable[[], Awaitable[None]]) -> None:
    connections = _connections.get(session_id)
    if connections is not None:
        connections.discard(finish)
        if not connections:
            _connections.pop(session_id, None)


async def drain(session_id: str) -> None:
    callbacks = list(_connections.get(session_id, ()))
    if callbacks:
        await asyncio.gather(*(callback() for callback in callbacks))
