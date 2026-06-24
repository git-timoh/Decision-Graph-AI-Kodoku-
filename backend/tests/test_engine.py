"""Tests for the DecisionEngine state machine, emitter, and SessionRunner."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Literal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import SessionConfig, SessionCreate
from kodoku.db.models import Checkpoint, Evaluation, Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import CheckpointKind, NodeKind, NodeStatus
from kodoku.engine.events import (
    CHECKPOINT_REACHED,
    EVALUATION_COMPLETED,
    NODE_CREATED,
    SESSION_DONE,
    SESSION_ERROR,
    SESSION_STARTED,
    SYNTHESIS_COMPLETED,
)
from kodoku.engine.runner import SessionRunner
from kodoku.engine.state_machine import DecisionEngine
from kodoku.llm.factory import RoleClients
from kodoku.llm.fake import FakeLLMClient
from kodoku.repo.sessions import SessionRepository


def _roles(llm: FakeLLMClient) -> RoleClients:
    """Use one scripted fake for all three roles (calls are FIFO-shared)."""
    return RoleClients(expand=llm, evaluate=llm, synthesize=llm)


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
    db: AsyncSession,
    *,
    branching_factor: int = 2,
    max_depth: int = 2,
    hitl_mode: Literal["autopilot", "every_branch"] = "autopilot",
) -> SessionModel:
    repo = SessionRepository(db)
    payload = SessionCreate(
        goal="Brainstorm side-project ideas combining AI and music creatively.",
        config=SessionConfig(
            branching_factor=branching_factor, max_depth=max_depth, hitl_mode=hitl_mode
        ),
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
    engine = DecisionEngine(db_session, session, _roles(llm), rec)

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
    assert all(e.model == llm.model for e in evals)

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
    engine = DecisionEngine(db_session, session, _roles(llm), _Recorder())

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
    engine = DecisionEngine(db_session, session, _roles(llm), rec)

    with pytest.raises(AssertionError):
        await engine.run()

    assert session.status == "error"
    assert SESSION_ERROR in rec.types()
    assert SESSION_DONE not in rec.types()


async def test_should_stop_from_start_pauses(db_session: AsyncSession) -> None:
    session = await _make_session(db_session)
    llm = FakeLLMClient(completions=[], chunks=["x"])
    rec = _Recorder()
    engine = DecisionEngine(db_session, session, _roles(llm), rec, should_stop=lambda: True)

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


async def test_run_with_braces_in_goal_completes(db_session: AsyncSession) -> None:
    """A goal containing `{`/`}` must not be parsed as a format string.

    `str.format` does not re-parse substituted values, so a brace-bearing goal
    alone never crashed; the real fragility was the templates' own literal JSON
    braces needing `{{ }}` escaping. `string.Template.safe_substitute` removes
    that footgun. This guards that `Compare {A, B} vs {C}` runs to completion.
    """
    repo = SessionRepository(db_session)
    payload = SessionCreate(
        goal="Compare {A, B} vs {C}",
        config=SessionConfig(branching_factor=2, max_depth=2),
    )
    session = await repo.create(payload)
    llm = FakeLLMClient(
        completions=[json.dumps(o) for o in _FULL_RUN_SCRIPT],
        chunks=["Final ", "answer."],
    )
    engine = DecisionEngine(db_session, session, _roles(llm), _Recorder())

    await engine.run()  # must not raise

    assert session.status == "done"
    assert session.final_synthesis == "Final answer."


class _ScoreByTitleClient:
    """Fake `LLMClient` whose evaluate score is derived from the candidate title.

    Out-of-order completion is forced (later children resolve first) to prove
    the engine persists evaluations/events in *child order*, not completion
    order.
    """

    model = "score-by-title"

    def __init__(self, expand_obj: dict[str, Any], chunks: list[str]) -> None:
        self._expand = json.dumps(expand_obj)
        self.chunks = chunks
        self._n = 0

    async def complete(self, *, system: str, prompt: str, json_object: bool = False) -> str:
        if '"candidates"' in prompt or "candidate next steps" in prompt:
            return self._expand
        # Evaluate: score by which title appears; reverse-delay so the last
        # child's call resolves first.
        order = ["C1", "C2", "C3"]
        idx = next((i for i, t in enumerate(order) if t in prompt), 0)
        await asyncio.sleep((len(order) - idx) * 0.01)
        score = float(idx + 1)  # C1 -> 1.0, C2 -> 2.0, C3 -> 3.0
        return json.dumps(
            {"score": score, "critique": f"crit-{idx}", "dimensions": {"feasibility": score}}
        )

    async def stream(self, *, system: str, prompt: str) -> Any:
        for chunk in self.chunks:
            yield chunk


async def test_parallel_evaluate_preserves_child_order(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, branching_factor=3, max_depth=1)
    expand_obj = {"candidates": [{"title": t, "content": f"{t} content"} for t in
                                 ("C1", "C2", "C3")]}
    llm = _ScoreByTitleClient(expand_obj, chunks=["done"])
    rec = _Recorder()
    engine = DecisionEngine(
        db_session, session, RoleClients(expand=llm, evaluate=llm, synthesize=llm), rec
    )

    await engine.run()

    # Child order is the node.created emission order (sequential, in child
    # order) — NOT created_at, which ties under Postgres func.now() (one
    # timestamp per transaction) and would order siblings non-deterministically.
    created = [
        p for t, p in rec.events
        if t == NODE_CREATED and p["kind"] == NodeKind.CANDIDATE.value
    ]
    child_ids = [p["id"] for p in created]
    assert [p["title"] for p in created] == ["C1", "C2", "C3"]

    # 3 Evaluation rows persisted; scores associate to the right child (1, 2, 3)
    # despite later children resolving first.
    evals = (await db_session.execute(select(Evaluation))).scalars().all()
    assert len(evals) == 3
    score_by_node = {str(e.node_id): float(e.score) for e in evals}
    assert [score_by_node[cid] for cid in child_ids] == [1.0, 2.0, 3.0]

    # evaluation.completed events emitted in child order despite reversed timing.
    ev_node_ids = [p["node_id"] for t, p in rec.events if t == EVALUATION_COMPLETED]
    assert ev_node_ids == child_ids


def test_emitter_alias_importable() -> None:
    # make_db_emitter is exercised in integration; here just ensure import path.
    from kodoku.engine.events import Emitter, make_db_emitter  # noqa: F401

    assert callable(make_db_emitter)


# expand root -> A, B; both evaluated, then the run must pause for human review
# before any keep/prune marking or further expansion happens.
_PAUSE_RUN_SCRIPT = [
    _expand("A", "B"),
    _eval(8.0),  # would-be kept
    _eval(3.0),  # would-be pruned
]


async def test_every_branch_mode_pauses_at_first_checkpoint(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, hitl_mode="every_branch")
    llm = FakeLLMClient(
        completions=[json.dumps(o) for o in _PAUSE_RUN_SCRIPT],
        chunks=["unused"],
    )
    rec = _Recorder()
    engine = DecisionEngine(db_session, session, _roles(llm), rec)

    await engine.run()

    assert session.status == "awaiting_human"
    assert session.current_step is None
    assert session.final_synthesis is None

    checkpoints = (
        (await db_session.execute(select(Checkpoint).where(Checkpoint.session_id == session.id)))
        .scalars()
        .all()
    )
    assert len(checkpoints) == 1
    checkpoint = checkpoints[0]
    assert checkpoint.kind == CheckpointKind.POST_EVALUATE.value
    assert checkpoint.resolved_at is None

    payload = checkpoint.payload
    assert sorted(payload.keys()) == ["candidates", "proposed_keep", "proposed_prune"]
    assert len(payload["candidates"]) == 2
    for cand in payload["candidates"]:
        assert sorted(cand.keys()) == [
            "content",
            "critique",
            "dimensions",
            "id",
            "score",
            "title",
        ]
    assert len(payload["proposed_keep"]) == 1
    assert len(payload["proposed_prune"]) == 1

    assert rec.count(CHECKPOINT_REACHED) == 1
    checkpoint_payloads = [p for t, p in rec.events if t == CHECKPOINT_REACHED]
    assert checkpoint_payloads[0]["checkpoint_id"] == str(checkpoint.id)
    assert checkpoint_payloads[0]["kind"] == CheckpointKind.POST_EVALUATE.value

    # The 2 candidates persisted and still ACTIVE — not marked kept/pruned.
    nodes = (
        (await db_session.execute(select(Node).where(Node.session_id == session.id)))
        .scalars()
        .all()
    )
    candidates = [n for n in nodes if n.kind == NodeKind.CANDIDATE.value]
    assert len(candidates) == 2
    assert all(n.status == NodeStatus.ACTIVE.value for n in candidates)

    # The parent (root) is marked EXPANDED so it isn't re-expanded later.
    root = next(n for n in nodes if n.kind == NodeKind.ROOT.value)
    assert root.status == NodeStatus.EXPANDED.value

    # No synthesis, no SESSION_DONE.
    assert SESSION_DONE not in rec.types()
    assert SYNTHESIS_COMPLETED not in rec.types()


async def test_autopilot_mode_unaffected_by_hitl_feature(db_session: AsyncSession) -> None:
    """Regression guard: autopilot must remain byte-for-byte unchanged."""
    session = await _make_session(db_session, hitl_mode="autopilot")
    llm = FakeLLMClient(
        completions=[json.dumps(o) for o in _FULL_RUN_SCRIPT],
        chunks=["Final ", "answer."],
    )
    rec = _Recorder()
    engine = DecisionEngine(db_session, session, _roles(llm), rec)

    await engine.run()

    assert session.status == "done"
    assert session.final_synthesis == "Final answer."

    checkpoints = (
        (await db_session.execute(select(Checkpoint).where(Checkpoint.session_id == session.id)))
        .scalars()
        .all()
    )
    assert checkpoints == []
    assert rec.count(CHECKPOINT_REACHED) == 0
    assert SESSION_DONE in rec.types()
