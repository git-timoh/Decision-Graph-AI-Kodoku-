from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.repo.settings import SettingsRepository


@pytest.mark.asyncio
async def test_upsert_then_get_all_round_trips(db_session: AsyncSession) -> None:
    repo = SettingsRepository(db_session)
    await repo.upsert({"key.anthropic": "sk-ant-abc", "key.openai": "sk-oai-xyz"})

    all_settings = await repo.get_all()
    assert all_settings == {
        "key.anthropic": "sk-ant-abc",
        "key.openai": "sk-oai-xyz",
    }


@pytest.mark.asyncio
async def test_upsert_overwrites_existing_key(db_session: AsyncSession) -> None:
    repo = SettingsRepository(db_session)
    await repo.upsert({"model.expand": "anthropic/claude-sonnet-4-6"})
    await repo.upsert({"model.expand": "anthropic/claude-opus-4-6"})

    value = await repo.get("model.expand")
    assert value == "anthropic/claude-opus-4-6"

    all_settings = await repo.get_all()
    assert all_settings == {"model.expand": "anthropic/claude-opus-4-6"}


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(db_session: AsyncSession) -> None:
    repo = SettingsRepository(db_session)
    value = await repo.get("does_not_exist")
    assert value is None
