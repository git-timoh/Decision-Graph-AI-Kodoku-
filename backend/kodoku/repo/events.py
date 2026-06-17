"""Async repository for the durable `events` journal.

Every WebSocket message is appended here first, then fanned out to live
subscribers. Reconnecting clients replay via `list_since`. `events.id` is a
bigserial, so it doubles as the monotonic cursor.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.models import Event


class EventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def append(
        self, session_id: UUID, type_: str, payload: dict[str, Any]
    ) -> Event:
        event = Event(session_id=session_id, type=type_, payload=payload)
        self._db.add(event)
        await self._db.flush()  # assigns event.id
        return event

    async def list_since(self, session_id: UUID, since: int = 0) -> list[Event]:
        stmt = (
            select(Event)
            .where(Event.session_id == session_id, Event.id > since)
            .order_by(Event.id.asc())
        )
        return list((await self._db.execute(stmt)).scalars().all())
