"""Shared pytest fixtures for Kodoku backend tests."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean, deterministic env."""
    for key in list(os.environ):
        if key.startswith(("DATABASE_URL", "APP_ENV", "LOG_LEVEL", "ALLOWED_ORIGINS")):
            monkeypatch.delenv(key, raising=False)
