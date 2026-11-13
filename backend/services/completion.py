"""Coordinate REST completion with active sockets in this single gateway.

Durable, cross-process job coordination belongs to Phase 3. Database CAS remains
the final idempotency boundary; this registry only drains active live I/O.
"""
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

_connections: dict[str, set[Callable[[], Awaitable[None]]]] = {}
_bound: set[str] = set()
_end_locks = {}


@asynccontextmanager
async def end_lock(session_id):
    entry = _end_locks.setdefault(session_id, [asyncio.Lock(), 0])
    entry[1] += 1
    try:
        async with entry[0]:
            yield
    finally:
        entry[1] -= 1
        if not entry[1]: _end_locks.pop(session_id, None)


def bind(session_id: str) -> bool:
    from services.limits import MAX_LIVE_CONNECTIONS
    if session_id in _bound or len(_bound) >= MAX_LIVE_CONNECTIONS:
        return False
    _bound.add(session_id)
    return True


def release(session_id: str) -> None:
    _bound.discard(session_id)


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
