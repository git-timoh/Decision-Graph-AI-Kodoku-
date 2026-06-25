"""Async repository for the `app_settings` key-value store.

Backs BYOK provider API keys and per-role model choices. Values are stored as
opaque strings (JSON-encoded by callers where structure is needed) and
upserted one row per key.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.models import AppSetting


class SettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all(self) -> dict[str, str]:
        stmt = select(AppSetting)
        rows = (await self._db.execute(stmt)).scalars().all()
        return {row.key: row.value for row in rows}

    async def get(self, key: str) -> str | None:
        stmt = select(AppSetting).where(AppSetting.key == key)
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        return row.value if row is not None else None

    async def upsert(self, items: dict[str, str]) -> None:
        if not items:
            return
        # ponytail: merge is a dialect-agnostic upsert-by-PK (SELECT then INSERT/UPDATE).
        # Settings is a tiny low-volume store, so the per-key SELECT is free.
        for key, value in items.items():
            await self._db.merge(AppSetting(key=key, value=value))
        await self._db.flush()
