"""Integration tests for `POST /run` and `POST /interrupt`.

These exercise the real commit boundary end-to-end: HTTP request -> engine
running on a fresh AsyncSession -> single commit -> REST read-back. The run
router's role-clients builder is overridden so the engine talks to a
`RoleClients` of `FakeLLMClient`s scripted for a tiny one-node run instead of a
real provider.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from kodoku.api.run import RoleClientsBuilder, get_role_clients_builder
from kodoku.db.session import get_db
from kodoku.engine.runner import runner
from kodoku.llm.factory import RoleClients
from kodoku.llm.fake import FakeLLMClient
from kodoku.main import create_app

# branching_factor=1, max_depth=1: expand root -> 1 candidate, evaluate it,
# decide at depth(1) == max_depth(1) -> expand=[], loop ends. Then synthesize
# streams over the single kept/pruned node before session.done.
_EXPAND_JSON = {"candidates": [{"title": "Idea A", "content": "Idea A content"}]}
_EVALUATE_JSON = {
    "score": 8.0,
    "critique": "Solid idea.",
    "dimensions": {"feasibility": 8, "novelty": 7},
}
_SYNTH_CHUNKS = ["Final ", "recommendation."]


def _make_fake_client() -> FakeLLMClient:
    fake = FakeLLMClient.from_json([_EXPAND_JSON, _EVALUATE_JSON])
    fake.chunks = list(_SYNTH_CHUNKS)
    return fake


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine,
    truncate_all: None,
) -> AsyncIterator[AsyncClient]:
    """HTTP client whose `get_db`/`get_llm_factory` deps point at the test
    engine and a scripted `FakeLLMClient`, respectively."""
    sessionmaker = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def _override_role_clients_builder() -> RoleClientsBuilder:
        async def _build(_s: AsyncSession) -> RoleClients:
            fake = _make_fake_client()
            return RoleClients(expand=fake, evaluate=fake, synthesize=fake)

        return _build

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_role_clients_builder] = _override_role_clients_builder
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_session(client: AsyncClient) -> str:
    created = (await client.post(
        "/sessions",
        json={
            "goal": "Brainstorm side-project ideas combining AI and music.",
            "config": {"branching_factor": 1, "max_depth": 1},
        },
    )).json()
    return created["session_id"]


@pytest.mark.asyncio
async def test_run_completes_and_persists_via_rest(client: AsyncClient) -> None:
    sid = await _make_session(client)

    response = await client.post(f"/sessions/{sid}/run")
    assert response.status_code == 202
    assert response.json() == {"status": "running"}

    await runner.join(UUID(sid))

    detail = (await client.get(f"/sessions/{sid}")).json()
    assert detail["status"] == "done"
    candidates = [n for n in detail["nodes"] if n["kind"] == "candidate"]
    assert len(candidates) >= 1

    replay = (await client.get(f"/sessions/{sid}/events")).json()
    types = [e["type"] for e in replay]
    assert types  # non-empty
    assert types[0] == "session.started"
    assert types[-1] == "session.done"
    ids = [e["id"] for e in replay]
    assert ids == sorted(ids)  # ordered


@pytest.mark.asyncio
async def test_run_on_running_session_returns_409(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    sid = await _make_session(client)

    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE sessions SET status='running' WHERE id = :id"),
            {"id": sid},
        )

    response = await client.post(f"/sessions/{sid}/run")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_run_while_in_process_task_running_returns_409(client: AsyncClient) -> None:
    """A second `/run` while the first task is still tracked in-process must
    be rejected even though the DB status hasn't been committed as
    'running' yet (the engine only commits at the end of the run)."""
    sid = await _make_session(client)
    session_id = UUID(sid)
    release = asyncio.Event()

    async def _never_finishes() -> None:
        await release.wait()

    runner.start(session_id, _never_finishes())
    try:
        assert runner.is_running(session_id) is True

        response = await client.post(f"/sessions/{sid}/run")
        assert response.status_code == 409
    finally:
        release.set()
        await runner.join(session_id)


@pytest.mark.asyncio
async def test_run_on_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.post(f"/sessions/{uuid4()}/run")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_interrupt_returns_202_with_bool(client: AsyncClient) -> None:
    sid = await _make_session(client)

    response = await client.post(f"/sessions/{sid}/interrupt")
    assert response.status_code == 202
    body = response.json()
    assert isinstance(body["interrupted"], bool)


# --- /resume ----------------------------------------------------------------
# branching_factor=2, max_depth=1: expand root -> 2 candidates (A, B), both
# evaluated. every_branch pauses for human review instead of deciding. After
# resume keeps one (A) and prunes the other (B), depth(1) is not < max_depth(1)
# so the frontier is empty post-resume -> straight to synthesis -> DONE.
_PAUSE_EXPAND_JSON = {
    "candidates": [
        {"title": "Idea A", "content": "Idea A content"},
        {"title": "Idea B", "content": "Idea B content"},
    ]
}
_EVAL_A_JSON = {"score": 8.0, "critique": "Strong.", "dimensions": {"feasibility": 8}}
_EVAL_B_JSON = {"score": 3.0, "critique": "Weak.", "dimensions": {"feasibility": 3}}


def _make_pause_client() -> FakeLLMClient:
    fake = FakeLLMClient.from_json([_PAUSE_EXPAND_JSON, _EVAL_A_JSON, _EVAL_B_JSON])
    fake.chunks = list(_SYNTH_CHUNKS)
    return fake


@pytest_asyncio.fixture
async def hitl_client(
    db_engine: AsyncEngine,
    truncate_all: None,
) -> AsyncIterator[AsyncClient]:
    """Like `client`, but the fake LLM is scripted for the every_branch pause
    script above (2 candidates, then a synthesis stream after resume)."""
    sessionmaker = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def _override_role_clients_builder() -> RoleClientsBuilder:
        async def _build(_s: AsyncSession) -> RoleClients:
            fake = _make_pause_client()
            return RoleClients(expand=fake, evaluate=fake, synthesize=fake)

        return _build

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_role_clients_builder] = _override_role_clients_builder
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_hitl_session(client: AsyncClient) -> str:
    created = (await client.post(
        "/sessions",
        json={
            "goal": "Brainstorm side-project ideas combining AI and music.",
            "config": {"branching_factor": 2, "max_depth": 1, "hitl_mode": "every_branch"},
        },
    )).json()
    return created["session_id"]


async def _run_to_checkpoint(client: AsyncClient, sid: str) -> dict:
    response = await client.post(f"/sessions/{sid}/run")
    assert response.status_code == 202
    await runner.join(UUID(sid))

    detail = (await client.get(f"/sessions/{sid}")).json()
    assert detail["status"] == "awaiting_human"
    checkpoints = detail["checkpoints"]
    assert len(checkpoints) == 1
    assert checkpoints[0]["resolved_at"] is None
    return checkpoints[0]


@pytest.mark.asyncio
async def test_resume_full_cycle_applies_decision_and_continues(
    hitl_client: AsyncClient,
) -> None:
    sid = await _make_hitl_session(hitl_client)
    checkpoint = await _run_to_checkpoint(hitl_client, sid)
    candidates = checkpoint["payload"]["candidates"]
    by_title = {c["title"]: c["id"] for c in candidates}
    keep_id = by_title["Idea A"]
    prune_id = by_title["Idea B"]

    response = await hitl_client.post(
        f"/sessions/{sid}/resume",
        json={
            "checkpoint_id": checkpoint["id"],
            "keep": [keep_id],
            "prune": [prune_id],
            "edits": {keep_id: {"title": "Idea A (edited)"}},
        },
    )
    assert response.status_code == 202

    await runner.join(UUID(sid))

    detail = (await hitl_client.get(f"/sessions/{sid}")).json()
    nodes_by_id = {n["id"]: n for n in detail["nodes"]}
    assert nodes_by_id[keep_id]["status"] == "kept"
    assert nodes_by_id[keep_id]["title"] == "Idea A (edited)"
    assert nodes_by_id[prune_id]["status"] == "pruned"
    assert nodes_by_id[prune_id]["title"] == "Idea B"

    resolved_checkpoint = next(
        c for c in detail["checkpoints"] if c["id"] == checkpoint["id"]
    )
    assert resolved_checkpoint["resolved_at"] is not None
    assert resolved_checkpoint["decision"]["keep"] == [keep_id]
    assert resolved_checkpoint["decision"]["prune"] == [prune_id]

    # Empty frontier post-resume (max_depth=1) -> straight to synthesis -> DONE.
    assert detail["status"] == "done"

    replay = (await hitl_client.get(f"/sessions/{sid}/events")).json()
    types = [e["type"] for e in replay]
    assert "checkpoint.reached" in types
    assert "checkpoint.resolved" in types
    reached_idx = types.index("checkpoint.reached")
    resolved_idx = types.index("checkpoint.resolved")
    assert reached_idx < resolved_idx
    assert types[-1] == "session.done"


@pytest.mark.asyncio
async def test_resume_with_wrong_checkpoint_id_returns_409(hitl_client: AsyncClient) -> None:
    sid = await _make_hitl_session(hitl_client)
    checkpoint = await _run_to_checkpoint(hitl_client, sid)
    candidates = checkpoint["payload"]["candidates"]
    keep_id = candidates[0]["id"]

    response = await hitl_client.post(
        f"/sessions/{sid}/resume",
        json={"checkpoint_id": str(uuid4()), "keep": [keep_id], "prune": []},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_resume_when_not_awaiting_human_returns_409(hitl_client: AsyncClient) -> None:
    sid = await _make_hitl_session(hitl_client)

    response = await hitl_client.post(
        f"/sessions/{sid}/resume",
        json={"checkpoint_id": str(uuid4()), "keep": [], "prune": []},
    )
    assert response.status_code == 409
