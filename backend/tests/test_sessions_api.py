from __future__ import annotations

from collections.abc import AsyncIterator

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


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine,
    truncate_all: None,
) -> AsyncIterator[AsyncClient]:
    """HTTP client whose `get_db` dependency points at the test database."""
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


@pytest.mark.asyncio
async def test_create_session_returns_201_with_id(client: AsyncClient) -> None:
    response = await client.post(
        "/sessions",
        json={"goal": "Brainstorm side-project ideas combining AI and music."},
    )
    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body


@pytest.mark.asyncio
async def test_create_then_get_bundles_root_node(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan a six-week sabbatical that builds my portfolio."},
    )).json()

    fetched = await client.get(f"/sessions/{created['session_id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "draft"
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["kind"] == "root"
    assert body["evaluations"] == []
    assert body["checkpoints"] == []


@pytest.mark.asyncio
async def test_list_returns_summary_rows_in_recency_order(client: AsyncClient) -> None:
    a = (await client.post("/sessions", json={"goal": "First goal goal goal."})).json()
    b = (await client.post("/sessions", json={"goal": "Second goal goal goal."})).json()
    c = (await client.post("/sessions", json={"goal": "Third goal goal goal."})).json()

    listed = await client.get("/sessions")
    assert listed.status_code == 200
    rows = listed.json()
    ids = [row["id"] for row in rows]
    assert ids == [c["session_id"], b["session_id"], a["session_id"]]
    assert "goal" not in rows[0]  # summary view


@pytest.mark.asyncio
async def test_patch_renames_session(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Rename goal goal goal goal."},
    )).json()

    response = await client.patch(
        f"/sessions/{created['session_id']}",
        json={"title": "Renamed"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


@pytest.mark.asyncio
async def test_patch_rejects_when_running(client: AsyncClient, db_engine: AsyncEngine) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Running session goal goal goal."},
    )).json()
    from sqlalchemy import text

    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE sessions SET status='running' WHERE id = :id"),
            {"id": created["session_id"]},
        )

    response = await client.patch(
        f"/sessions/{created['session_id']}",
        json={"title": "should fail"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_removes_session_and_root(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Delete goal goal goal goal."},
    )).json()

    response = await client.delete(f"/sessions/{created['session_id']}")
    assert response.status_code == 204

    follow_up = await client.get(f"/sessions/{created['session_id']}")
    assert follow_up.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_id_returns_404(client: AsyncClient) -> None:
    import uuid

    response = await client.get(f"/sessions/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_goal_returns_422(client: AsyncClient) -> None:
    response = await client.post("/sessions", json={"goal": "short"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_md_is_downloadable_markdown(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan an export of the decision memo."},
    )).json()

    resp = await client.get(f"/sessions/{created['session_id']}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=" in resp.headers["content-disposition"]
    assert ".md" in resp.headers["content-disposition"]
    assert "## Recommendation" in resp.text


@pytest.mark.asyncio
async def test_export_json_returns_bundle_shape(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan an export of the decision memo as json."},
    )).json()

    resp = await client.get(f"/sessions/{created['session_id']}/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["id"] == created["session_id"]
    assert body["nodes"][0]["kind"] == "root"


@pytest.mark.asyncio
async def test_export_unknown_id_returns_404(client: AsyncClient) -> None:
    import uuid

    resp = await client.get(f"/sessions/{uuid.uuid4()}/export")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_bad_format_returns_422(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan an export with a bad format value."},
    )).json()

    resp = await client.get(f"/sessions/{created['session_id']}/export?format=pdf")
    assert resp.status_code == 422
