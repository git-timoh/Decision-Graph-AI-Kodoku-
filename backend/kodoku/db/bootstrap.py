"""Startup recovery for the local single-user app: schema creation and
reconciling runs orphaned by a previous process.

Postgres (hosted/multi-user) keeps using Alembic migrations; only the SQLite
local-first path bootstraps its schema here, since the app ships with no
migration runner for end users.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from kodoku.db import models  # noqa: F401  — register mappers before create_all
from kodoku.db.base import Base
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import SessionStatus


async def ensure_schema(engine: AsyncEngine) -> bool:
    if engine.dialect.name != "sqlite":
        return False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return True


async def fail_orphaned_runs(session: AsyncSession) -> int:
    """Mark sessions left RUNNING by a previous process as ERROR; return the count.

    The engine runs as an in-memory asyncio task (see `engine/runner.py`); a
    server restart loses the task but leaves the row at RUNNING forever — a dead
    spinner in the UI with no escape. On startup we fail those: the UI shows an
    error and ERROR is resumable, so the user can re-run.
    """
    result = await session.execute(
        update(SessionModel)
        .where(SessionModel.status == SessionStatus.RUNNING.value)
        .values(status=SessionStatus.ERROR.value, current_step=None)
    )
    await session.commit()
    return result.rowcount or 0
