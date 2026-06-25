from __future__ import annotations

import pytest
from sqlalchemy import text

from kodoku.db.engine import get_engine, get_sessionmaker


@pytest.mark.asyncio
async def test_engine_can_connect() -> None:
    """Confirms the async engine reaches the configured database (SQLite by default)."""
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 AS ok"))
        row = result.one()
        assert row.ok == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_sessionmaker_yields_working_session() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(text("SELECT 2 AS two"))
        assert result.scalar_one() == 2
