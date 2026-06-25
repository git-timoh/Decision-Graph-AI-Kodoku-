"""First-run schema creation for the local SQLite default.

Postgres (hosted/multi-user) keeps using Alembic migrations; only the SQLite
local-first path bootstraps its schema here, since the app ships with no
migration runner for end users.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from kodoku.db.base import Base
from kodoku.db import models  # noqa: F401  — register mappers before create_all


async def ensure_schema(engine: AsyncEngine) -> bool:
    if engine.dialect.name != "sqlite":
        return False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return True
