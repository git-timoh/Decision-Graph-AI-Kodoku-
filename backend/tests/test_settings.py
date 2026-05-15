from __future__ import annotations

import pytest

from kodoku.settings import Settings, get_settings


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000,http://example.com")

    settings = Settings()

    assert settings.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert settings.app_env == "test"
    assert settings.allowed_origins == ["http://localhost:3000", "http://example.com"]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("APP_ENV", "test")

    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
