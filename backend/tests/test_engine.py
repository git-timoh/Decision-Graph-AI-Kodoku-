"""Tests for the DecisionEngine state machine, emitter, and SessionRunner."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import SessionConfig, SessionCreate
from kodoku.db.models import Evaluation, Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import NodeKind, NodeStatus
from kodoku.engine.events import (
    EVALUATION_COMPLETED,
    NODE_CREATED,
    SESSION_DONE,
    SESSION_ERROR,
    SESSION_STARTED,
    SYNTHESIS_COMPLETED,
)
from kodoku.engine.runner import SessionRunner
from kodoku.engine.state_machine import DecisionEngine
from kodoku.llm.fake import FakeLLMClient
from kodoku.repo.sessions import SessionRepository


class _Recorder:
    """A recording `Emitter`: collects (type, payload) tuples."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, type_: str, payload: dict[str, Any]) -> None:
        self.events.append((type_, payload))

    def types(self) -> list[str]:
        return [t for t, _ in self.events]

    def count(self, type_: str) -> int:
        return sum(1 for t, _ in self.events if t == type_)


async def _make_session(
    db: AsyncSession, *, branching_factor: int = 2, max_depth: int = 2
) -> SessionModel:
    repo = SessionRepository(db)
    payload = SessionCreate(
        goal="Brainstorm side-project ideas combining AI and music creatively.",
        config=SessionConfig(branching_factor=branching_factor, max_depth=max_depth),
    )
    return await repo.create(payload)


def _expand(*titles: str) -> dict[str, Any]:
    return {"candidates": [{"title": t, "content": f"{t} content"} for t in titles]}


def _eval(score: float) -> dict[str, Any]:
    return {"score": score, "critique": "ok", "dimensions": {"feasibility": score}}


# Full run script for branching_factor=2, max_depth=2:
#   expand root -> A (kept), B (pruned)
#   expand A    -> A1 (kept), A2 (pruned); depth 2 => no further expansion
_FULL_RUN_SCRIPT = [
    _expand("A", "B"),
    _eval(8.0),  # A kept
    _eval(3.0),  # B pruned
    _expand("A1", "A2"),
    _eval(7.0),  # A1 kept
    _eval(2.0),  # A2 pruned
]


async def test_full_run_persists_and_completes(db_session: AsyncSession) -> None:
    session = await _make_session(db_session)
    llm = FakeLLMClient(
        completions=[json.dumps(o) for o in _FULL_RUN_SCRIPT],
        chunks=["Final ", "answer."],
    )
    rec = _Recorder()
    engine = DecisionEngine(db_session, session, llm, rec)

    await engine.run()

    assert session.status == "done"
    assert session.current_step is None
    assert session.final_synthesis == "Final answer."

    nodes = (
        (await db_session.execute(select(Node).where(Node.session_id == session.id)))
        .scalars()
        .all()
    )
    candidates = [n for n in nodes if n.kind == NodeKind.CANDIDATE.value]
    assert len(candidates) == 4  # A, B at depth 1; A1, A2 at depth 2
    depths = sorted(n.depth for n in candidates)
    assert depths == [1, 1, 2, 2]

    evals = (
        (await db_session.execute(select(Evaluation))).scalars().all()
    )
    assert len(evals) == 4
    assert all(e.model == session.config["model"] for e in evals)

    # Event sequence bookends + counts.
    assert rec.types()[0] == SESSION_STARTED
    assert rec.types()[-1] == SESSION_DONE
    assert rec.count(NODE_CREATED) == 4
    assert rec.count(EVALUATION_COMPLETED) == 4
    assert rec.count(SYNTHESIS_COMPLETED) == 1


async def test_pruning_reflected_in_node_statuses(db_session: AsyncSession) -> None:
    session = await _make_session(db_session)
    llm = FakeLLMClient(
        completions=[json.dumps(o) for o in _FULL_RUN_SCRIPT],
        chunks=["done"],
    )
    engine = DecisionEngine(db_session, session, llm, _Recorder())

    await engine.run()

    nodes = (
        (await db_session.execute(select(Node).where(Node.session_id == session.id)))
        .scalars()
        .all()
    )
    statuses = [n.status for n in nodes]
    assert NodeStatus.PRUNED.value in statuses  # B and A2 pruned
    assert NodeStatus.KEPT.value in statuses  # A1 kept
    # Parents (root + A) end expanded.
    assert statuses.count(NodeStatus.EXPANDED.value) == 2


async def test_error_path_sets_status_and_emits(db_session: AsyncSession) -> None:
    session = await _make_session(db_session)
    llm = FakeLLMClient(completions=[])  # first expand raises (exhausted)
    rec = _Recorder()
    engine = DecisionEngine(db_session, session, llm, rec)

    with pytest.raises(AssertionError):
        await engine.run()

    assert session.status == "error"
    assert SESSION_ERROR in rec.types()
    assert SESSION_DONE not in rec.types()


async def test_should_stop_from_start_pauses(db_session: AsyncSession) -> None:
    session = await _make_session(db_session)
    llm = FakeLLMClient(completions=[], chunks=["x"])
    rec = _Recorder()
    engine = DecisionEngine(db_session, session, llm, rec, should_stop=lambda: True)

    await engine.run()

    assert session.status == "paused"
    assert SESSION_DONE not in rec.types()
    assert SESSION_STARTED in rec.types()


async def test_runner_interrupt_and_should_stop() -> None:
    runner = SessionRunner()
    sid = uuid4()

    assert runner.should_stop(sid) is False
    # Unknown id: nothing running, returns False.
    assert runner.interrupt(sid) is False
    assert runner.should_stop(sid) is True


async def test_runner_start_tracks_and_interrupt_returns_true() -> None:
    runner = SessionRunner()
    sid = uuid4()
    started = asyncio.Event()
    release = asyncio.Event()

    async def _work() -> None:
        started.set()
        await release.wait()

    runner.start(sid, _work())
    await started.wait()
    assert runner.is_running(sid) is True
    assert runner.interrupt(sid) is True  # a task was running
    release.set()
    await runner.join(sid)
    assert runner.is_running(sid) is False
    # Cleanup callback also cleared the stop flag.
    assert runner.should_stop(sid) is False


def test_emitter_alias_importable() -> None:
    # make_db_emitter is exercised in integration; here just ensure import path.
    from kodoku.engine.events import Emitter, make_db_emitter  # noqa: F401

    assert callable(make_db_emitter)
