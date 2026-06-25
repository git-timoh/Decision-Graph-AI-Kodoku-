"""Async SQLAlchemy engine and session factory."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kodoku.settings import get_settings


def enable_sqlite_fk(engine: AsyncEngine) -> AsyncEngine:
    """SQLite enforces foreign keys only when asked, per connection. No-op elsewhere.

    Without this, ondelete=CASCADE / passive_deletes silently orphan child rows.
    """
    if engine.dialect.name != "sqlite":
        return engine

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL: concurrent readers see the latest commit without blocking the writer.
        cursor.execute("PRAGMA journal_mode=WAL")
        # busy_timeout: wait out the single-writer lock instead of erroring immediately.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return enable_sqlite_fk(
        create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            future=True,
        )
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )
