from __future__ import annotations

import json
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
async def test_get_empty_store_returns_all_providers_unset(client: AsyncClient) -> None:
    resp = await client.get("/settings")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body["providers"]) == {
        "openrouter",
        "deepseek",
        "openai",
        "anthropic",
        "zhipu",
        "google",
    }
    for status in body["providers"].values():
        assert status == {"set": False, "hint": None}
    assert body["ollama_base_url"] is None
    assert body["models"] == {"expand": None, "evaluate": None, "synthesize": None}


@pytest.mark.asyncio
async def test_put_provider_key_then_get_masks_secret(client: AsyncClient) -> None:
    secret = "sk-ant-super-secret-token-abcd1234"
    put_resp = await client.put("/settings", json={"providers": {"anthropic": secret}})
    assert put_resp.status_code == 200

    get_resp = await client.get("/settings")
    assert get_resp.status_code == 200
    body = get_resp.json()

    assert body["providers"]["anthropic"] == {"set": True, "hint": secret[-4:]}
    # The full secret must never appear anywhere in either response body.
    assert secret not in put_resp.text
    assert secret not in get_resp.text
    assert secret not in json.dumps(put_resp.json())
    assert secret not in json.dumps(body)


@pytest.mark.asyncio
async def test_put_null_clears_provider_key(client: AsyncClient) -> None:
    await client.put("/settings", json={"providers": {"openai": "sk-oai-abcd1234"}})

    clear_resp = await client.put("/settings", json={"providers": {"openai": None}})
    assert clear_resp.status_code == 200

    body = (await client.get("/settings")).json()
    assert body["providers"]["openai"] == {"set": False, "hint": None}


@pytest.mark.asyncio
async def test_omitted_fields_left_unchanged(client: AsyncClient) -> None:
    await client.put(
        "/settings",
        json={
            "providers": {"deepseek": "sk-deepseek-1234"},
            "ollama_base_url": "http://localhost:11434",
        },
    )

    # PUT again touching only models; providers + ollama_base_url must survive.
    await client.put("/settings", json={"models": {"expand": "anthropic/claude-sonnet-4-6"}})

    body = (await client.get("/settings")).json()
    assert body["providers"]["deepseek"] == {"set": True, "hint": "1234"}
    assert body["ollama_base_url"] == "http://localhost:11434"
    assert body["models"]["expand"] == "anthropic/claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_put_model_then_get_reflects_full_string(client: AsyncClient) -> None:
    resp = await client.put(
        "/settings",
        json={"models": {"evaluate": "openrouter/deepseek/deepseek-chat"}},
    )
    assert resp.status_code == 200
    assert resp.json()["models"]["evaluate"] == "openrouter/deepseek/deepseek-chat"

    body = (await client.get("/settings")).json()
    assert body["models"]["evaluate"] == "openrouter/deepseek/deepseek-chat"


@pytest.mark.asyncio
async def test_put_invalid_model_string_is_422(client: AsyncClient) -> None:
    resp = await client.put(
        "/settings",
        json={"models": {"expand": "not a valid model id!"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_unknown_provider_name_is_422(client: AsyncClient) -> None:
    resp = await client.put(
        "/settings",
        json={"providers": {"made_up_provider": "some-key"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_unknown_model_role_is_422(client: AsyncClient) -> None:
    resp = await client.put(
        "/settings",
        json={"models": {"made_up_role": "anthropic/claude-sonnet-4-6"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_ollama_base_url_round_trips(client: AsyncClient) -> None:
    resp = await client.put(
        "/settings",
        json={"ollama_base_url": "http://localhost:11434"},
    )
    assert resp.status_code == 200
    assert resp.json()["ollama_base_url"] == "http://localhost:11434"

    body = (await client.get("/settings")).json()
    assert body["ollama_base_url"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_put_ollama_base_url_null_clears_it(client: AsyncClient) -> None:
    await client.put("/settings", json={"ollama_base_url": "http://localhost:11434"})

    resp = await client.put("/settings", json={"ollama_base_url": None})
    assert resp.status_code == 200
    assert resp.json()["ollama_base_url"] is None

    body = (await client.get("/settings")).json()
    assert body["ollama_base_url"] is None
