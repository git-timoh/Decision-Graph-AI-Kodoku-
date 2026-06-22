"""`/run` and `/interrupt` endpoints: start/stop the DecisionEngine.

The engine never commits (it only `flush()`es) — this module owns the single
commit boundary for a run. `POST /run` starts the engine on a *fresh*
`AsyncSession` from `get_sessionmaker()`, not the request's `get_db` session,
because the HTTP request returns long before the background run finishes.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
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
from kodoku.llm.factory import RoleClients, make_role_clients
from kodoku.repo.sessions import SessionNotFound, SessionRepository
from kodoku.repo.settings import SettingsRepository

router = APIRouter(prefix="/sessions/{session_id}", tags=["run"])

#: Builds the per-role LLM clients for a run, given the run's DB session.
#: Overridden in tests to inject a `RoleClients` of fakes.
RoleClientsBuilder = Callable[[AsyncSession], Awaitable[RoleClients]]


async def _default_role_clients(s: AsyncSession) -> RoleClients:
    return await make_role_clients(SettingsRepository(s))


def get_role_clients_builder() -> RoleClientsBuilder:
    """FastAPI dependency: returns the production role-clients builder."""
    return _default_role_clients

_RESUMABLE_STATUSES = frozenset({
    SessionStatus.DRAFT.value,
    SessionStatus.PAUSED.value,
    SessionStatus.ERROR.value,
})


class RunResponse(BaseModel):
    status: str


class InterruptResponse(BaseModel):
    interrupted: bool


async def _run_engine(session_id: UUID, build_clients: RoleClientsBuilder) -> None:
    """Run the engine on a fresh session; commit once, always, on exit."""
    async with get_sessionmaker()() as s:
        session = await SessionRepository(s).get(session_id)
        clients = await build_clients(s)
        engine = DecisionEngine(
            s,
            session,
            clients,
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
    build_clients: RoleClientsBuilder = Depends(get_role_clients_builder),  # noqa: B008
) -> RunResponse:
    try:
        session = await SessionRepository(db).get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    if session.status not in _RESUMABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail=f"cannot start session in status {session.status!r}"
        )

    if runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="session is already running")

    runner.start(session_id, _run_engine(session_id, build_clients))
    return RunResponse(status="running")


@router.post(
    "/interrupt", response_model=InterruptResponse, status_code=status.HTTP_202_ACCEPTED
)
async def interrupt_run(session_id: UUID) -> InterruptResponse:
    return InterruptResponse(interrupted=runner.interrupt(session_id))
