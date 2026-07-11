from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from kodoku.db.session import get_db
from kodoku.main import create_app
from kodoku.ws.emit import emit_event
from kodoku.ws.manager import ConnectionManager


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine,
    truncate_all: None,
) -> AsyncIterator[AsyncClient]:
    sessionmaker = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_session(client: AsyncClient) -> str:
    created = (await client.post(
        "/sessions",
        json={"goal": "Side-project ideas combining AI and music."},
    )).json()
    return created["session_id"]


async def _emit_story(db_engine: AsyncEngine, session_id: str) -> None:
    sessionmaker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with sessionmaker() as session:
        sid = UUID(session_id)
        for type_, payload in [
            ("session.started", {}),
            ("node.created", {"id": str(uuid4()), "status": "active"}),
            ("session.done", {}),
        ]:
            await emit_event(session, sid, type_, payload)
        await session.commit()


@pytest.mark.asyncio
async def test_replay_returns_journaled_events_in_order(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    sid = await _make_session(client)
    await _emit_story(db_engine, sid)

    replay = (await client.get(f"/sessions/{sid}/events")).json()
    assert len(replay) == 3
    ids = [e["id"] for e in replay]
    assert ids == sorted(ids)  # monotonic order
    assert replay[0]["type"] == "session.started"
    assert replay[-1]["type"] == "session.done"


@pytest.mark.asyncio
async def test_replay_since_filters_by_cursor(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    sid = await _make_session(client)
    await _emit_story(db_engine, sid)

    full = (await client.get(f"/sessions/{sid}/events")).json()
    midpoint = full[len(full) // 2]["id"]

    tail = (await client.get(f"/sessions/{sid}/events?since={midpoint}")).json()
    assert [e["id"] for e in tail] == [e["id"] for e in full if e["id"] > midpoint]


@pytest.mark.asyncio
async def test_replay_unknown_session_is_empty(client: AsyncClient) -> None:
    replay = (await client.get(f"/sessions/{uuid4()}/events")).json()
    assert replay == []


class _FakeWs:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self._fail = fail

    async def send_json(self, message: dict[str, Any]) -> None:
        if self._fail:
            raise RuntimeError("socket is dead")
        self.sent.append(message)


@pytest.mark.asyncio
async def test_broadcast_fans_out_and_prunes_dead_sockets() -> None:
    mgr = ConnectionManager()
    sid = uuid4()
    live, dead = _FakeWs(), _FakeWs(fail=True)
    mgr._rooms[sid] = {live, dead}  # type: ignore[assignment]

    await mgr.broadcast(sid, {"type": "node.created"})

    assert live.sent == [{"type": "node.created"}]
    assert dead not in mgr._rooms.get(sid, set())  # pruned after send failure
