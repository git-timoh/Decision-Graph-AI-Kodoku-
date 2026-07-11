"""Single funnel for emitting an event: journal it, then fan out live.

Used by the DecisionEngine and tests. The DB row is the durable truth (and the
`id` cursor); the broadcast `ts` is a display timestamp taken Python-side to
avoid a refresh round-trip.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import WsEvent
from kodoku.repo.events import EventRepository
from kodoku.ws.manager import ConnectionManager, manager


async def emit_event(
    db: AsyncSession,
    session_id: UUID,
    type_: str,
    payload: dict[str, Any],
    *,
    conn: ConnectionManager = manager,
) -> WsEvent:
    row = await EventRepository(db).append(session_id, type_, payload)
    event = WsEvent(
        id=row.id,
        type=type_,
        session_id=session_id,
        ts=datetime.now(UTC),
        payload=payload,
    )
    await conn.broadcast(session_id, event.model_dump(mode="json"))
    return event
