"""Replay endpoint for cold reconnects."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import WsEvent
from kodoku.db.session import get_db
from kodoku.repo.events import EventRepository

router = APIRouter(prefix="/sessions/{session_id}", tags=["events"])


@router.get("/events", response_model=list[WsEvent])
async def replay_events(
    session_id: UUID,
    since: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WsEvent]:
    rows = await EventRepository(db).list_since(session_id, since)
    return [
        WsEvent(
            id=r.id,
            type=r.type,
            session_id=r.session_id,
            ts=r.created_at,
            payload=r.payload,
        )
        for r in rows
    ]
