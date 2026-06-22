"""Shared pytest fixtures for Kodoku backend tests."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kodoku.db import models  # noqa: F401  — register mappers
from kodoku.db.base import Base

TEST_DB_NAME = "kodoku_test"


def _admin_dsn() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku",
    )
    parsed = urlparse(raw.replace("+asyncpg", ""))
    return urlunparse(parsed._replace(path="/postgres"))


def _test_db_url() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku",
    )
    parsed = urlparse(raw)
    return urlunparse(parsed._replace(path=f"/{TEST_DB_NAME}"))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean, deterministic env."""
    for key in list(os.environ):
        if key.startswith(("APP_ENV", "LOG_LEVEL", "ALLOWED_ORIGINS")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", _test_db_url())

    from kodoku.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Session-scoped event loop so session-scoped async fixtures can share it."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _bootstrap_test_db() -> AsyncIterator[None]:
    """Create the test database (if absent) and create all tables once."""
    admin = await asyncpg.connect(dsn=_admin_dsn())
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await admin.close()

    engine = create_async_engine(_test_db_url(), future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_engine(_bootstrap_test_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_test_db_url(), future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test session wrapped in a transaction that always rolls back."""
    connection = await db_engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def truncate_all(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Available for tests that bypass the per-test transaction (e.g. HTTP tests)."""
    yield
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE events, checkpoints, evaluations, nodes, sessions, "
                "app_settings RESTART IDENTITY CASCADE"
            )
        )
