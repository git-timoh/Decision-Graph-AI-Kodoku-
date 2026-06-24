"""Tests for `rebuild_frontier`: DB-driven frontier reconstruction.

Covers the selection rule directly (fresh session, mixed statuses/depths,
already-expanded exclusion) and the dup-node regression: re-running `run()`
after a session is DONE must not re-expand already-expanded parents.
"""
from __future__ import annotations

import json
from collections import deque

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import SessionConfig, SessionCreate
from kodoku.db.models import Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import NodeKind, NodeStatus
from kodoku.engine.frontier import rebuild_frontier
from kodoku.engine.state_machine import DecisionEngine
from kodoku.llm.factory import RoleClients
from kodoku.llm.fake import FakeLLMClient
from kodoku.repo.sessions import SessionRepository


def _roles(llm: FakeLLMClient) -> RoleClients:
    return RoleClients(expand=llm, evaluate=llm, synthesize=llm)


class _Recorder:
    async def __call__(self, type_: str, payload: dict[str, object]) -> None:
        pass


async def _make_session(
    db: AsyncSession, *, branching_factor: int = 2, max_depth: int = 2
) -> SessionModel:
    repo = SessionRepository(db)
    payload = SessionCreate(
        goal="Brainstorm side-project ideas combining AI and music creatively.",
        config=SessionConfig(branching_factor=branching_factor, max_depth=max_depth),
    )
    return await repo.create(payload)


async def _root(db: AsyncSession, session: SessionModel) -> Node:
    stmt = select(Node).where(
        Node.session_id == session.id, Node.kind == NodeKind.ROOT.value
    )
    return (await db.execute(stmt)).scalar_one()


async def test_fresh_draft_session_frontier_is_root_only(db_session: AsyncSession) -> None:
    session = await _make_session(db_session)
    root = await _root(db_session, session)

    frontier = await rebuild_frontier(db_session, session)

    assert frontier == deque([root.id])


async def test_kept_unexpanded_candidates_form_frontier(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, max_depth=2)
    root = await _root(db_session, session)
    root.status = NodeStatus.EXPANDED.value

    a = Node(
        session_id=session.id,
        parent_id=root.id,
        depth=1,
        kind=NodeKind.CANDIDATE.value,
        title="A",
        content="A content",
        status=NodeStatus.KEPT.value,
    )
    b = Node(
        session_id=session.id,
        parent_id=root.id,
        depth=1,
        kind=NodeKind.CANDIDATE.value,
        title="B",
        content="B content",
        status=NodeStatus.KEPT.value,
    )
    db_session.add_all([a, b])
    await db_session.flush()

    frontier = await rebuild_frontier(db_session, session)

    assert frontier == deque([a.id, b.id])


async def test_candidate_at_max_depth_excluded(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, max_depth=1)
    root = await _root(db_session, session)
    root.status = NodeStatus.EXPANDED.value

    # depth == max_depth (1) must be excluded even though status is KEPT.
    leaf = Node(
        session_id=session.id,
        parent_id=root.id,
        depth=1,
        kind=NodeKind.CANDIDATE.value,
        title="Leaf",
        content="Leaf content",
        status=NodeStatus.KEPT.value,
    )
    db_session.add(leaf)
    await db_session.flush()

    frontier = await rebuild_frontier(db_session, session)

    assert frontier == deque()


async def test_expanded_node_excluded(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, max_depth=3)
    root = await _root(db_session, session)
    root.status = NodeStatus.EXPANDED.value

    parent = Node(
        session_id=session.id,
        parent_id=root.id,
        depth=1,
        kind=NodeKind.CANDIDATE.value,
        title="Parent",
        content="Parent content",
        status=NodeStatus.EXPANDED.value,
    )
    db_session.add(parent)
    await db_session.flush()

    child = Node(
        session_id=session.id,
        parent_id=parent.id,
        depth=2,
        kind=NodeKind.CANDIDATE.value,
        title="Child",
        content="Child content",
        status=NodeStatus.KEPT.value,
    )
    db_session.add(child)
    await db_session.flush()

    frontier = await rebuild_frontier(db_session, session)

    # `parent` is EXPANDED (excluded) and has a child (excluded via the
    # no-children rule too); only the unexpanded, childless `child` remains.
    assert frontier == deque([child.id])


def _expand(*titles: str) -> dict[str, object]:
    return {"candidates": [{"title": t, "content": f"{t} content"} for t in titles]}


def _eval(score: float) -> dict[str, object]:
    return {"score": score, "critique": "ok", "dimensions": {"feasibility": score}}


# branching_factor=2, max_depth=2: root -> A (kept), B (pruned);
# A -> A1 (kept), A2 (pruned); depth 2 == max_depth so no further expansion.
_FULL_RUN_SCRIPT = [
    _expand("A", "B"),
    _eval(8.0),
    _eval(3.0),
    _expand("A1", "A2"),
    _eval(7.0),
    _eval(2.0),
]


async def test_rerun_after_done_does_not_duplicate_nodes(db_session: AsyncSession) -> None:
    """Dup-node regression (RED against the old hardcoded `[root]` seed).

    Run an autopilot session to DONE, then invoke `run()` again. With the old
    seed (`deque([root_id])`) the engine would re-expand the already-EXPANDED
    root, creating duplicate candidate nodes. With `rebuild_frontier`, the
    rebuilt frontier is empty (root is EXPANDED, A is EXPANDED, A1/A2 are at
    max depth) so the second run goes straight to re-synthesis with no new
    nodes.
    """
    session = await _make_session(db_session, branching_factor=2, max_depth=2)
    llm = FakeLLMClient(
        completions=[json.dumps(o) for o in _FULL_RUN_SCRIPT],
        chunks=["Final ", "answer."],
    )
    engine = DecisionEngine(db_session, session, _roles(llm), _Recorder())
    await engine.run()
    assert session.status == "done"

    nodes_before = (
        (await db_session.execute(select(Node).where(Node.session_id == session.id)))
        .scalars()
        .all()
    )
    count_before = len(nodes_before)
    candidates_before = {n.id for n in nodes_before if n.kind == NodeKind.CANDIDATE.value}

    # Re-run with a fresh fake LLM client (no scripted responses needed if the
    # frontier is correctly empty — any call would raise "exhausted").
    llm2 = FakeLLMClient(completions=[], chunks=["Resynth."])
    engine2 = DecisionEngine(db_session, session, _roles(llm2), _Recorder())
    await engine2.run()

    assert session.status == "done"

    nodes_after = (
        (await db_session.execute(select(Node).where(Node.session_id == session.id)))
        .scalars()
        .all()
    )
    candidates_after = {n.id for n in nodes_after if n.kind == NodeKind.CANDIDATE.value}

    assert len(nodes_after) == count_before
    assert candidates_after == candidates_before
