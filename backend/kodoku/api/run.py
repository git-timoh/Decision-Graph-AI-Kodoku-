"""`/run` and `/interrupt` endpoints: start/stop the DecisionEngine.

The engine never commits (it only `flush()`es) — this module owns the single
commit boundary for a run. `POST /run` starts the engine on a *fresh*
`AsyncSession` from `get_sessionmaker()`, not the request's `get_db` session,
because the HTTP request returns long before the background run finishes.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.engine import get_sessionmaker
from kodoku.db.session import get_db
from kodoku.domain.enums import SessionStatus
from kodoku.engine.events import make_db_emitter
from kodoku.engine.runner import runner
from kodoku.engine.state_machine import DecisionEngine
from kodoku.llm.base import LLMClient
from kodoku.llm.factory import get_llm_factory
from kodoku.repo.sessions import SessionNotFound, SessionRepository

router = APIRouter(prefix="/sessions/{session_id}", tags=["run"])

_RESUMABLE_STATUSES = frozenset({
    SessionStatus.DRAFT.value,
    SessionStatus.PAUSED.value,
    SessionStatus.ERROR.value,
})


class RunResponse(BaseModel):
    status: str


class InterruptResponse(BaseModel):
    interrupted: bool


async def _run_engine(
    session_id: UUID, make_client: Callable[[dict[str, Any]], LLMClient]
) -> None:
    """Run the engine on a fresh session; commit once, always, on exit."""
    async with get_sessionmaker()() as s:
        session = await SessionRepository(s).get(session_id)
        llm = make_client(session.config)
        engine = DecisionEngine(
            s,
            session,
            llm,
            make_db_emitter(s, session_id),
            should_stop=lambda: runner.should_stop(session_id),
        )
        try:
            await engine.run()
        finally:
            await s.commit()


@router.post("/run", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    make_client: Callable[[dict[str, Any]], LLMClient] = Depends(get_llm_factory),  # noqa: B008
) -> RunResponse:
    try:
        session = await SessionRepository(db).get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    if session.status not in _RESUMABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail=f"cannot start session in status {session.status!r}"
        )

    runner.start(session_id, _run_engine(session_id, make_client))
    return RunResponse(status="running")


@router.post(
    "/interrupt", response_model=InterruptResponse, status_code=status.HTTP_202_ACCEPTED
)
async def interrupt_run(session_id: UUID) -> InterruptResponse:
    return InterruptResponse(interrupted=runner.interrupt(session_id))
