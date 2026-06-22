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
