"""`/run` and `/interrupt` endpoints: start/stop the DecisionEngine.

The engine never commits (it only `flush()`es) — this module owns the single
commit boundary for a run. `POST /run` starts the engine on a *fresh*
`AsyncSession` from `get_sessionmaker()`, not the request's `get_db` session,
because the HTTP request returns long before the background run finishes.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import ResumeRequest
from kodoku.db.engine import get_sessionmaker
from kodoku.db.models import Checkpoint, Node
from kodoku.db.session import get_db
from kodoku.domain.enums import NodeStatus, SessionStatus
from kodoku.engine.events import CHECKPOINT_RESOLVED, NODE_UPDATED, make_db_emitter
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


class ResumeResponse(BaseModel):
    status: str


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


async def _latest_unresolved_checkpoint(db: AsyncSession, session_id: UUID) -> Checkpoint | None:
    stmt = (
        select(Checkpoint)
        .where(Checkpoint.session_id == session_id, Checkpoint.resolved_at.is_(None))
        .order_by(Checkpoint.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().first()


async def _apply_resume(session_id: UUID, body: ResumeRequest) -> None:
    """Apply the human's keep/prune/edit decision and resolve the checkpoint.

    Runs on a fresh session, committed once at the end — mirrors `_run_engine`.
    """
    async with get_sessionmaker()() as s:
        emit = make_db_emitter(s, session_id)
        checkpoint = await _latest_unresolved_checkpoint(s, session_id)
        assert checkpoint is not None  # validated by the caller before scheduling

        keep_set = {str(nid) for nid in body.keep}
        candidate_ids = [c["id"] for c in checkpoint.payload["candidates"]]

        node_rows = (
            (
                await s.execute(
                    select(Node).where(Node.id.in_([UUID(cid) for cid in candidate_ids]))
                )
            )
            .scalars()
            .all()
        )
        nodes_by_id = {str(n.id): n for n in node_rows}

        for cid in candidate_ids:
            node = nodes_by_id[cid]
            new_status = NodeStatus.KEPT if cid in keep_set else NodeStatus.PRUNED
            changed = node.status != new_status.value
            node.status = new_status.value

            edit = body.edits.get(UUID(cid))
            if edit is not None:
                if edit.title is not None and edit.title != node.title:
                    node.title = edit.title
                    changed = True
                if edit.content is not None and edit.content != node.content:
                    node.content = edit.content
                    changed = True

            if changed:
                await s.flush()
                await emit(
                    NODE_UPDATED,
                    {"id": str(node.id), "status": node.status, "title": node.title,
                     "content": node.content},
                )

        decision = {
            "keep": [str(nid) for nid in body.keep],
            "prune": [str(nid) for nid in body.prune],
            "edits": {str(nid): edit.model_dump() for nid, edit in body.edits.items()},
        }
        checkpoint.decision = decision
        checkpoint.resolved_at = datetime.now(UTC)
        await s.flush()
        await emit(
            CHECKPOINT_RESOLVED,
            {"checkpoint_id": str(checkpoint.id), "decision": decision},
        )
        await s.commit()


@router.post("/resume", response_model=ResumeResponse, status_code=status.HTTP_202_ACCEPTED)
async def resume_run(
    session_id: UUID,
    body: ResumeRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    build_clients: RoleClientsBuilder = Depends(get_role_clients_builder),  # noqa: B008
) -> ResumeResponse:
    try:
        session = await SessionRepository(db).get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    if session.status != SessionStatus.AWAITING_HUMAN.value:
        raise HTTPException(
            status_code=409, detail=f"cannot resume session in status {session.status!r}"
        )

    if runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="session is already running")

    checkpoint = await _latest_unresolved_checkpoint(db, session_id)
    if checkpoint is None or checkpoint.id != body.checkpoint_id:
        raise HTTPException(status_code=409, detail="checkpoint_id does not match the "
                             "session's latest unresolved checkpoint")

    candidate_ids = {UUID(c["id"]) for c in checkpoint.payload["candidates"]}
    submitted_ids = set(body.keep) | set(body.prune)
    if not submitted_ids <= candidate_ids:
        raise HTTPException(
            status_code=422,
            detail="keep/prune ids must be a subset of the checkpoint's candidate ids",
        )

    await _apply_resume(session_id, body)

    runner.start(session_id, _run_engine(session_id, build_clients))
    return ResumeResponse(status="running")


@router.post(
    "/interrupt", response_model=InterruptResponse, status_code=status.HTTP_202_ACCEPTED
)
async def interrupt_run(session_id: UUID) -> InterruptResponse:
    return InterruptResponse(interrupted=runner.interrupt(session_id))
