from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import SessionConfig, SessionCreate, SessionUpdate
from kodoku.db.models import Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import NodeKind, NodeStatus, SessionStatus
from kodoku.repo.sessions import (
    SessionMutationNotAllowed,
    SessionNotFound,
    SessionRepository,
)


@pytest.mark.asyncio
async def test_create_session_atomically_creates_root_node(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    payload = SessionCreate(goal="Brainstorm side-project ideas combining AI and music.")
    session = await repo.create(payload)

    assert session.status == SessionStatus.DRAFT.value
    assert session.user_id == "local"
    assert session.title.startswith("Brainstorm side-project")
    assert session.config["model"] == "anthropic/claude-sonnet-4-6"

    nodes = await repo.list_nodes(session.id)
    assert len(nodes) == 1
    root = nodes[0]
    assert root.kind == NodeKind.ROOT.value
    assert root.parent_id is None
    assert root.depth == 0
    assert root.status == NodeStatus.ACTIVE.value
    assert root.content == payload.goal


@pytest.mark.asyncio
async def test_create_session_with_custom_title_and_config(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    payload = SessionCreate(
        goal="Plan a six-week sabbatical that builds my portfolio.",
        title="Sabbatical plan",
        config=SessionConfig(branching_factor=5, max_depth=2, temperature=0.5),
    )
    session = await repo.create(payload)

    assert session.title == "Sabbatical plan"
    assert session.config["branching_factor"] == 5
    assert session.config["max_depth"] == 2
    assert session.config["temperature"] == 0.5


@pytest.mark.asyncio
async def test_list_returns_all_sessions(db_session: AsyncSession) -> None:
    """Repo-level test only verifies the listing returns every session.

    Postgres `now()` returns transaction-start time, so multiple rows created
    within the per-test transaction share `updated_at` and ordering between
    them is non-deterministic. The recency-ordering contract is verified by
    `test_sessions_api.py::test_list_returns_summary_rows_in_recency_order`,
    where each HTTP request runs in its own transaction.
    """
    repo = SessionRepository(db_session)
    a = await repo.create(SessionCreate(goal="First goal goal goal."))
    b = await repo.create(SessionCreate(goal="Second goal goal goal."))
    c = await repo.create(SessionCreate(goal="Third goal goal goal."))

    listed = await repo.list_summaries()
    assert {s.id for s in listed} == {a.id, b.id, c.id}


@pytest.mark.asyncio
async def test_get_bundle_returns_session_with_relations(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Bundle goal goal goal."))

    bundle = await repo.get_bundle(created.id)
    assert bundle.session.id == created.id
    assert len(bundle.nodes) == 1
    assert bundle.evaluations == []
    assert bundle.checkpoints == []


@pytest.mark.asyncio
async def test_get_bundle_raises_for_missing(db_session: AsyncSession) -> None:
    import uuid

    repo = SessionRepository(db_session)
    with pytest.raises(SessionNotFound):
        await repo.get_bundle(uuid.uuid4())


@pytest.mark.asyncio
async def test_rename_updates_title(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Rename goal goal goal."))

    updated = await repo.update(created.id, SessionUpdate(title="New title"))
    assert updated.title == "New title"


@pytest.mark.asyncio
async def test_update_blocked_when_running(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Running goal goal goal."))
    created.status = SessionStatus.RUNNING.value
    await db_session.flush()

    with pytest.raises(SessionMutationNotAllowed):
        await repo.update(created.id, SessionUpdate(title="nope"))


@pytest.mark.asyncio
async def test_delete_cascades_nodes(db_session: AsyncSession) -> None:
    from sqlalchemy import select

    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Delete goal goal goal."))

    await repo.delete(created.id)

    remaining_sessions = (await db_session.execute(select(SessionModel))).scalars().all()
    remaining_nodes = (await db_session.execute(select(Node))).scalars().all()
    assert remaining_sessions == []
    assert remaining_nodes == []


@pytest.mark.asyncio
async def test_delete_raises_for_missing(db_session: AsyncSession) -> None:
    import uuid

    repo = SessionRepository(db_session)
    with pytest.raises(SessionNotFound):
        await repo.delete(uuid.uuid4())
