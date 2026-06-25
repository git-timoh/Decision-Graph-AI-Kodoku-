from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from kodoku.db.bootstrap import ensure_schema


async def test_ensure_schema_creates_tables_on_sqlite() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")  # in-memory
    ran = await ensure_schema(engine)
    assert ran is True
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: sa.inspect(c).get_table_names())
    assert {"sessions", "nodes", "events", "evaluations", "checkpoints"} <= set(names)
    # idempotent: second run does not raise
    assert await ensure_schema(engine) is True
    await engine.dispose()


async def test_ensure_schema_skips_non_sqlite() -> None:
    # build an engine object without connecting; postgres dialect must be skipped
    engine = create_async_engine("postgresql+asyncpg://u:p@localhost/db")
    assert await ensure_schema(engine) is False
    await engine.dispose()
