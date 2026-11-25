"""Server sent events from the events table. The web client uses EventSource."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Callable

from sqlalchemy.orm import Session, sessionmaker

from sendora_core.db import session_scope
from sendora_core.events import recent_events


def format_sse(event: str, data: dict, event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, default=str)}")
    return "\n".join(lines) + "\n\n"


async def event_stream(
    factory: sessionmaker[Session], after_id: int = 0, kind_prefix: str | None = None,
    poll_s: float = 1.0, max_idle_polls: int | None = None, is_disconnected: Callable[[], bool] | None = None,
) -> AsyncIterator[str]:
    """Yield new events as SSE frames. Sends a comment heartbeat when idle so proxies keep the connection."""
    idle = 0
    cursor = after_id
    while True:
        if is_disconnected:
            gone = is_disconnected()
            if inspect.isawaitable(gone):
                gone = await gone
            if gone:
                return
        with session_scope(factory) as s:
            rows = recent_events(s, cursor, kind_prefix=kind_prefix)
            frames = [format_sse(e.kind, {"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id, "payload": e.payload}, e.id) for e in rows]
            if rows:
                cursor = rows[-1].id
        if frames:
            idle = 0
            for f in frames:
                yield f
        else:
            idle += 1
            yield ": heartbeat\n\n"
            if max_idle_polls is not None and idle >= max_idle_polls:
                return
        await asyncio.sleep(poll_s)
