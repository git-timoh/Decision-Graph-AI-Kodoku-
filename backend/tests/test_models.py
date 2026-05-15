from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.models import (
    Checkpoint,
    Evaluation,
    Event,
    Node,
)
from kodoku.db.models import (
    Session as SessionModel,
)
from kodoku.domain.enums import (
    CheckpointKind,
    NodeKind,
    NodeStatus,
    SessionStatus,
)


@pytest.mark.asyncio
async def test_session_round_trip(db_session: AsyncSession) -> None:
    s = SessionModel(
        title="Side projects in AI + music",
        goal="Brainstorm side projects combining AI and music",
        status=SessionStatus.DRAFT.value,
        config={
            "model": "anthropic/claude-sonnet-4-6",
            "branching_factor": 3,
            "max_depth": 3,
            "temperature": 0.7,
        },
    )
    db_session.add(s)
    await db_session.flush()

    fetched = (
        await db_session.execute(
            select(SessionModel).where(SessionModel.id == s.id)
        )
    ).scalar_one()
    assert fetched.user_id == "local"
    assert fetched.title == "Side projects in AI + music"
    assert fetched.status == "draft"
    assert fetched.config["model"] == "anthropic/claude-sonnet-4-6"
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_node_cascade_delete(db_session: AsyncSession) -> None:
    s = SessionModel(
        title="t", goal="goal goal goal", status=SessionStatus.DRAFT.value, config={}
    )
    db_session.add(s)
    await db_session.flush()

    root = Node(
        session_id=s.id, parent_id=None, depth=0,
        kind=NodeKind.ROOT.value, title="t", content="goal goal goal",
        status=NodeStatus.ACTIVE.value,
    )
    db_session.add(root)
    await db_session.flush()

    child = Node(
        session_id=s.id, parent_id=root.id, depth=1,
        kind=NodeKind.CANDIDATE.value, title="c", content="content content",
        status=NodeStatus.PENDING.value,
    )
    db_session.add(child)
    await db_session.flush()

    await db_session.delete(s)
    await db_session.flush()

    remaining = (await db_session.execute(select(Node))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_evaluation_round_trip(db_session: AsyncSession) -> None:
    s = SessionModel(title="t", goal="goal goal goal", status="draft", config={})
    db_session.add(s)
    await db_session.flush()
    n = Node(
        session_id=s.id, parent_id=None, depth=0,
        kind="candidate", title="c", content="x x x", status="pending",
    )
    db_session.add(n)
    await db_session.flush()

    e = Evaluation(
        node_id=n.id,
        score=Decimal("7.50"),
        critique="solid",
        dimensions={"feasibility": 8, "novelty": 7, "impact": 7, "effort": 5, "fit": 8},
        model="anthropic/claude-sonnet-4-6",
    )
    db_session.add(e)
    await db_session.flush()

    fetched = (await db_session.execute(select(Evaluation))).scalar_one()
    assert fetched.score == Decimal("7.50")
    assert fetched.dimensions["feasibility"] == 8


@pytest.mark.asyncio
async def test_checkpoint_and_event(db_session: AsyncSession) -> None:
    s = SessionModel(title="t", goal="goal goal goal", status="awaiting_human", config={})
    db_session.add(s)
    await db_session.flush()

    cp = Checkpoint(
        session_id=s.id,
        kind=CheckpointKind.POST_EVALUATE.value,
        payload={"prune": [], "expand": [], "keep": []},
        decision=None,
    )
    ev = Event(
        session_id=s.id,
        type="checkpoint.reached",
        payload={"checkpoint_id": "00000000-0000-0000-0000-000000000000"},
    )
    db_session.add_all([cp, ev])
    await db_session.flush()

    assert cp.id is not None
    assert isinstance(ev.id, int) and ev.id > 0
