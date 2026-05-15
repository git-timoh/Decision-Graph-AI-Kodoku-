"""Async repository for the `sessions` aggregate.

The engine is the only writer for nodes, evaluations, and checkpoints — except
for the root node, which is created atomically with the session at
`POST /sessions` time. That single carve-out lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kodoku.api.dtos import SessionConfig, SessionCreate, SessionUpdate
from kodoku.db.models import (
    Checkpoint,
    Evaluation,
    Node,
)
from kodoku.db.models import (
    Session as SessionModel,
)
from kodoku.domain.enums import NodeKind, NodeStatus, SessionStatus


class SessionNotFound(LookupError):
    """Raised when a session id does not exist."""


class SessionMutationNotAllowed(RuntimeError):
    """Raised when a session is in a state that disallows the requested mutation."""


@dataclass(slots=True)
class SessionBundle:
    session: SessionModel
    nodes: list[Node]
    evaluations: list[Evaluation]
    checkpoints: list[Checkpoint]


_MUTABLE_STATUSES = frozenset({
    SessionStatus.DRAFT.value,
    SessionStatus.DONE.value,
    SessionStatus.ERROR.value,
    SessionStatus.PAUSED.value,
})


def _derive_title(goal: str) -> str:
    head = goal.strip().splitlines()[0]
    if len(head) <= 60:
        return head
    return head[:57].rstrip() + "…"


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, payload: SessionCreate) -> SessionModel:
        config = (payload.config or SessionConfig()).model_dump()
        title = payload.title or _derive_title(payload.goal)

        session = SessionModel(
            title=title,
            goal=payload.goal,
            status=SessionStatus.DRAFT.value,
            config=config,
            current_step=None,
            final_synthesis=None,
        )
        self._db.add(session)
        await self._db.flush()

        root = Node(
            session_id=session.id,
            parent_id=None,
            depth=0,
            kind=NodeKind.ROOT.value,
            title=title,
            content=payload.goal,
            status=NodeStatus.ACTIVE.value,
        )
        self._db.add(root)
        await self._db.flush()
        return session

    async def list_summaries(self) -> list[SessionModel]:
        stmt = select(SessionModel).order_by(SessionModel.updated_at.desc())
        return list((await self._db.execute(stmt)).scalars().all())

    async def get(self, session_id: UUID) -> SessionModel:
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        try:
            return (await self._db.execute(stmt)).scalar_one()
        except NoResultFound as exc:
            raise SessionNotFound(str(session_id)) from exc

    async def list_nodes(self, session_id: UUID) -> list[Node]:
        stmt = (
            select(Node)
            .where(Node.session_id == session_id)
            .order_by(Node.depth.asc(), Node.created_at.asc())
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_bundle(self, session_id: UUID) -> SessionBundle:
        stmt = (
            select(SessionModel)
            .where(SessionModel.id == session_id)
            .options(
                selectinload(SessionModel.nodes).selectinload(Node.evaluations),
                selectinload(SessionModel.checkpoints),
            )
        )
        result = (await self._db.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise SessionNotFound(str(session_id))
        nodes = sorted(result.nodes, key=lambda n: (n.depth, n.created_at))
        evaluations = [e for n in nodes for e in n.evaluations]
        checkpoints = sorted(result.checkpoints, key=lambda c: c.created_at)
        return SessionBundle(
            session=result,
            nodes=nodes,
            evaluations=evaluations,
            checkpoints=checkpoints,
        )

    async def update(self, session_id: UUID, payload: SessionUpdate) -> SessionModel:
        session = await self.get(session_id)
        if session.status not in _MUTABLE_STATUSES:
            raise SessionMutationNotAllowed(
                f"cannot edit session in status {session.status!r}"
            )
        if payload.title is not None:
            session.title = payload.title
        if payload.config is not None:
            session.config = payload.config.model_dump()
        await self._db.flush()
        return session

    async def delete(self, session_id: UUID) -> None:
        session = await self.get(session_id)
        await self._db.delete(session)
        await self._db.flush()
