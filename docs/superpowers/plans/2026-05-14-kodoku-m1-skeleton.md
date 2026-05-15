# Kodoku M1 — Skeleton + Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a working Kodoku skeleton — Postgres in Docker, FastAPI backend with `/healthz`, Next.js 14 frontend pinging it through a typed client, Alembic ready for the M2 schema, basic docs in place.

**Architecture:** Single repo, two top-level apps (`backend/`, `frontend/`), Postgres in docker-compose, FastAPI app factory + Pydantic settings, Next.js app-router with a typed fetch wrapper. No domain models yet, no LLM, no WebSockets — just the foundation everything else builds on.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2, pytest + httpx, Next.js 14, TypeScript 5, Tailwind 3, Zustand 4, Docker Compose, Postgres 16.

**Deviations from the spec, justified:** The spec's M1 file list mentions `shadcn/ui`. M1's only UI surface is a one-line healthz badge, which doesn't justify the install. shadcn lands in M2 alongside the first real component (the new-session modal). Everything else in M1's spec section is implemented here.

**Spec reference:** `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md` — sections 4 (architecture), 11 (M1 milestone), 12 (M1 tasks), 14 (repo layout).

---

## File Map

### Repo root
- Create: `.gitignore`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `README.md` (overwrites the one-line placeholder)
- Create: `docs/architecture.md`

### Backend (`backend/`)
- Create: `backend/pyproject.toml` — Python project config + dependencies
- Create: `backend/.python-version` — pin to 3.12
- Create: `backend/Dockerfile.dev` — dev container (used by M6 too)
- Create: `backend/.env.example`
- Create: `backend/kodoku/__init__.py`
- Create: `backend/kodoku/domain/__init__.py` — empty package init (M2 populates)
- Create: `backend/kodoku/main.py` — FastAPI app factory
- Create: `backend/kodoku/settings.py` — Pydantic settings
- Create: `backend/kodoku/api/__init__.py`
- Create: `backend/kodoku/api/health.py` — `/healthz`
- Create: `backend/kodoku/db/__init__.py`
- Create: `backend/kodoku/db/base.py` — SQLAlchemy declarative base
- Create: `backend/kodoku/db/engine.py` — async engine + session factory
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py` — fixtures
- Create: `backend/tests/test_health.py`

### Frontend (`frontend/`)
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/.env.example`
- Create: `frontend/.eslintrc.json`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/lib/api/client.ts` — typed fetch wrapper + healthz call
- Create: `frontend/lib/types/contracts.ts` — placeholder, real types in M2

---

## Task 1: Repo root files (.gitignore, env example, docs stub)

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `docs/architecture.md`

- [ ] **Step 1: Write `.gitignore`**

Path: `.gitignore`

```
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/

# Node
node_modules/
.next/
out/
.turbo/

# Env / secrets
.env
.env.local
.env.*.local
!.env.example
!backend/.env.example
!frontend/.env.example

# IDE
.idea/
.vscode/
*.swp
.DS_Store

# Coverage
coverage/
htmlcov/
.coverage
```

- [ ] **Step 2: Write root `.env.example`**

Path: `.env.example`

```
# Postgres (used by docker-compose)
POSTGRES_USER=kodoku
POSTGRES_PASSWORD=kodoku
POSTGRES_DB=kodoku
POSTGRES_PORT=5432
```

- [ ] **Step 3: Write `docs/architecture.md` stub**

Path: `docs/architecture.md`

```markdown
# Kodoku Architecture

Long-form architecture documentation lives here. The authoritative design
spec is `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md`. This file
is filled in as milestones land and accumulates diagrams, decision records,
and operational notes.

## Status

- M1 — Skeleton + contracts: in progress
- M2 — Domain model + REST CRUD: not started
- M3 — React Flow graph + WebSocket plumbing: not started
- M4 — DecisionEngine + LLM abstraction: not started
- M5 — Human-in-the-loop checkpoints: not started
- M6 — Provider polish + export + deploy: not started
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example docs/architecture.md
git commit -m "chore: add gitignore, env example, architecture doc stub"
```

---

## Task 2: docker-compose for Postgres

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

Path: `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: kodoku-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-kodoku}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-kodoku}
      POSTGRES_DB: ${POSTGRES_DB:-kodoku}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - kodoku-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-kodoku} -d ${POSTGRES_DB:-kodoku}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  kodoku-pgdata:
```

- [ ] **Step 2: Bring it up and verify**

Run: `docker compose up -d`
Expected output (last few lines):
```
 Container kodoku-postgres  Started
```

Run: `docker compose ps`
Expected: status shows `running (healthy)` within ~10s.

- [ ] **Step 3: Connect and verify the database exists**

Run: `docker exec kodoku-postgres psql -U kodoku -d kodoku -c "SELECT 1 AS ok;"`
Expected:
```
 ok
----
  1
(1 row)
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docker-compose with Postgres 16"
```

---

## Task 3: Backend Python project + pinned versions

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/.env.example`
- Create: `backend/kodoku/__init__.py`

- [ ] **Step 1: Write `backend/.python-version`**

Path: `backend/.python-version`

```
3.12
```

- [ ] **Step 2: Write `backend/pyproject.toml`**

Path: `backend/pyproject.toml`

```toml
[project]
name = "kodoku"
version = "0.1.0"
description = "Kodoku — Decision Graph AI backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi==0.115.6",
    "uvicorn[standard]==0.32.1",
    "pydantic==2.10.3",
    "pydantic-settings==2.7.0",
    "sqlalchemy[asyncio]==2.0.36",
    "asyncpg==0.30.0",
    "alembic==1.14.0",
    "python-dotenv==1.0.1",
    "httpx==0.28.1",
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.4",
    "pytest-asyncio==0.24.0",
    "pytest-cov==6.0.0",
    "ruff==0.8.4",
    "mypy==1.13.0",
    "anyio==4.7.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["kodoku"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers"
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "W"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
```

- [ ] **Step 3: Write `backend/.env.example`**

Path: `backend/.env.example`

```
# Postgres
DATABASE_URL=postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku

# App
APP_ENV=development
LOG_LEVEL=INFO

# CORS
ALLOWED_ORIGINS=http://localhost:3000
```

- [ ] **Step 4: Create empty package inits**

Path: `backend/kodoku/__init__.py`

```python
"""Kodoku — Decision Graph AI backend."""

__version__ = "0.1.0"
```

Path: `backend/kodoku/domain/__init__.py` (empty file — M2 fills it with dataclasses and enums)

- [ ] **Step 5: Create and activate virtualenv, install dev deps**

Run (from `backend/`):
```
python -m venv .venv
.venv\Scripts\activate         # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Expected: pip resolves and installs all pinned versions without conflict; final line is `Successfully installed ...`.

- [ ] **Step 6: Verify install**

Run (in activated venv, from `backend/`): `python -c "import fastapi, sqlalchemy, alembic, pydantic_settings; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/.python-version backend/.env.example backend/kodoku/__init__.py backend/kodoku/domain/__init__.py
git commit -m "feat(backend): scaffold Python project with pinned deps"
```

---

## Task 4: Pydantic settings module

**Files:**
- Create: `backend/kodoku/settings.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_settings.py`

- [ ] **Step 1: Create test files**

Path: `backend/tests/__init__.py` (empty file)

Path: `backend/tests/conftest.py`

```python
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
```

- [ ] **Step 2: Write the failing test**

Path: `backend/tests/test_settings.py`

```python
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
```

- [ ] **Step 3: Run test, expect ImportError**

Run (from `backend/`): `pytest tests/test_settings.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'kodoku.settings'`.

- [ ] **Step 4: Implement settings**

Path: `backend/kodoku/settings.py`

```python
"""Application settings loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku"
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:3000"]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Run tests, expect pass**

Run: `pytest tests/test_settings.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/kodoku/settings.py backend/tests/__init__.py backend/tests/conftest.py backend/tests/test_settings.py
git commit -m "feat(backend): add Pydantic settings module with env loading"
```

---

## Task 5: FastAPI app factory + `/healthz` endpoint

**Files:**
- Create: `backend/kodoku/api/__init__.py`
- Create: `backend/kodoku/api/health.py`
- Create: `backend/kodoku/main.py`
- Test: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing test**

Path: `backend/tests/test_health.py`

```python
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kodoku.main import create_app


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_cors_allows_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")

    from kodoku.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/healthz",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_health.py -v`
Expected: `ModuleNotFoundError: No module named 'kodoku.main'`.

- [ ] **Step 3: Create the api package init**

Path: `backend/kodoku/api/__init__.py` (empty file)

- [ ] **Step 4: Implement the healthz router**

Path: `backend/kodoku/api/health.py`

```python
"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from kodoku import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
```

- [ ] **Step 5: Implement the app factory**

Path: `backend/kodoku/main.py`

```python
"""FastAPI application factory."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kodoku.api.health import router as health_router
from kodoku.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="Kodoku",
        version="0.1.0",
        description="Decision Graph AI — Tree of Thoughts planner",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)

    return app


app = create_app()
```

- [ ] **Step 6: Run tests, expect pass**

Run: `pytest tests/test_health.py -v`
Expected: 2 passed.

- [ ] **Step 7: Smoke-test via uvicorn**

Run (from `backend/`, in activated venv): `uvicorn kodoku.main:app --port 8000 --reload`
In a second shell: `curl -s http://localhost:8000/healthz`
Expected:
```
{"status":"ok","version":"0.1.0"}
```
Stop uvicorn with Ctrl-C.

- [ ] **Step 8: Commit**

```bash
git add backend/kodoku/api/__init__.py backend/kodoku/api/health.py backend/kodoku/main.py backend/tests/test_health.py
git commit -m "feat(backend): add FastAPI app factory and healthz endpoint"
```

---

## Task 6: SQLAlchemy async engine + Alembic wiring

**Files:**
- Create: `backend/kodoku/db/__init__.py`
- Create: `backend/kodoku/db/base.py`
- Create: `backend/kodoku/db/engine.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`
- Test: `backend/tests/test_db_engine.py`

- [ ] **Step 1: Write the failing test**

Path: `backend/tests/test_db_engine.py`

```python
from __future__ import annotations

import pytest
from sqlalchemy import text

from kodoku.db.engine import get_engine, get_sessionmaker


@pytest.mark.asyncio
async def test_engine_can_connect_to_postgres() -> None:
    """Requires docker compose up. Confirms the async engine reaches Postgres."""
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
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_db_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'kodoku.db.engine'`.

- [ ] **Step 3: Create db package files**

Path: `backend/kodoku/db/__init__.py` (empty file)

Path: `backend/kodoku/db/base.py`

```python
"""SQLAlchemy declarative base. Concrete models land in M2."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""
```

Path: `backend/kodoku/db/engine.py`

```python
"""Async SQLAlchemy engine and session factory."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kodoku.settings import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )
```

- [ ] **Step 4: Run engine tests with Postgres up**

Confirm Postgres is running: `docker compose ps`
Set the env var for the test process if needed:
```
$env:DATABASE_URL="postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku"
```
Run: `pytest tests/test_db_engine.py -v`
Expected: 2 passed.

- [ ] **Step 5: Initialize Alembic**

From `backend/` (in activated venv): `alembic init -t async alembic`
This generates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`.

- [ ] **Step 6: Replace `alembic.ini` with project-tuned config**

Path: `backend/alembic.ini` (overwrite Alembic's default)

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 7: Replace `alembic/env.py` to use settings + Base.metadata**

Path: `backend/alembic/env.py` (overwrite generated file)

```python
"""Alembic environment — async, reads DATABASE_URL from Settings."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from kodoku.db.base import Base
from kodoku.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 8: Add `.gitkeep` to keep `versions/` tracked even when empty**

Path: `backend/alembic/versions/.gitkeep` (empty file)

- [ ] **Step 9: Generate an empty baseline migration**

Run (from `backend/`): `alembic revision -m "baseline"`
This produces a new file under `backend/alembic/versions/`. Open it and confirm `upgrade()` and `downgrade()` are both `pass` — leave them that way; M2 adds real tables.

- [ ] **Step 10: Apply the migration and verify**

Run: `alembic upgrade head`
Expected output ends with: `INFO  [alembic.runtime.migration] Running upgrade  -> <rev>, baseline`

Run: `docker exec kodoku-postgres psql -U kodoku -d kodoku -c "SELECT version_num FROM alembic_version;"`
Expected: one row with the generated revision id.

- [ ] **Step 11: Commit**

```bash
git add backend/kodoku/db/ backend/alembic.ini backend/alembic/ backend/tests/test_db_engine.py
git commit -m "feat(backend): wire SQLAlchemy async engine and Alembic baseline"
```

---

## Task 7: Backend dev Dockerfile

**Files:**
- Create: `backend/Dockerfile.dev`

- [ ] **Step 1: Write the Dockerfile**

Path: `backend/Dockerfile.dev`

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY kodoku ./kodoku
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "kodoku.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [ ] **Step 2: Build it**

Run (from `backend/`): `docker build -f Dockerfile.dev -t kodoku-backend:dev .`
Expected: build completes; last line includes `naming to docker.io/library/kodoku-backend:dev`.

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile.dev
git commit -m "feat(backend): add dev Dockerfile"
```

---

## Task 8: Frontend Next.js scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/.eslintrc.json`
- Create: `frontend/.env.example`
- Create: `frontend/app/globals.css`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`

- [ ] **Step 1: Write `frontend/package.json`**

Path: `frontend/package.json`

```json
{
  "name": "kodoku-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.18",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "zustand": "4.5.5"
  },
  "devDependencies": {
    "@types/node": "20.17.10",
    "@types/react": "18.3.18",
    "@types/react-dom": "18.3.5",
    "autoprefixer": "10.4.20",
    "eslint": "8.57.1",
    "eslint-config-next": "14.2.18",
    "postcss": "8.4.49",
    "tailwindcss": "3.4.17",
    "typescript": "5.7.2"
  }
}
```

- [ ] **Step 2: Write `frontend/tsconfig.json`**

Path: `frontend/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Write `frontend/next.config.mjs`**

Path: `frontend/next.config.mjs`

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

- [ ] **Step 4: Write Tailwind config files**

Path: `frontend/tailwind.config.ts`

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
```

Path: `frontend/postcss.config.mjs`

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Write `frontend/.eslintrc.json`**

Path: `frontend/.eslintrc.json`

```json
{
  "extends": "next/core-web-vitals"
}
```

- [ ] **Step 6: Write `frontend/.env.example`**

Path: `frontend/.env.example`

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 7: Write Tailwind globals**

Path: `frontend/app/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: light dark;
}

body {
  @apply bg-neutral-50 text-neutral-900 antialiased;
}

@media (prefers-color-scheme: dark) {
  body {
    @apply bg-neutral-950 text-neutral-100;
  }
}
```

- [ ] **Step 8: Write root layout**

Path: `frontend/app/layout.tsx`

```typescript
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kodoku",
  description: "Decision Graph AI — explore, evaluate, and synthesize ideas",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 9: Write a placeholder home page (real one comes in step 9 of next task)**

Path: `frontend/app/page.tsx`

```typescript
export default function HomePage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Kodoku</h1>
      <p className="mt-2 text-neutral-600 dark:text-neutral-400">
        Decision Graph AI. Tree-of-thoughts planner. M1 scaffolding.
      </p>
    </main>
  );
}
```

- [ ] **Step 10: Install dependencies**

Run (from `frontend/`): `npm install`
Expected: lockfile written, `node_modules/` populated, no errors.

- [ ] **Step 11: Run typecheck + dev server smoke**

Run: `npm run typecheck`
Expected: no output, exit code 0.

Run: `npm run dev`
Open `http://localhost:3000` — page renders the Kodoku heading. Stop with Ctrl-C.

- [ ] **Step 12: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.mjs frontend/tailwind.config.ts frontend/postcss.config.mjs frontend/.eslintrc.json frontend/.env.example frontend/app/globals.css frontend/app/layout.tsx frontend/app/page.tsx
git commit -m "feat(frontend): scaffold Next.js 14 app with Tailwind"
```

---

## Task 9: Typed API client + healthz ping in UI

**Files:**
- Create: `frontend/lib/api/client.ts`
- Create: `frontend/lib/types/contracts.ts`
- Modify: `frontend/app/page.tsx` (replace placeholder)

- [ ] **Step 1: Write the contracts stub**

Path: `frontend/lib/types/contracts.ts`

```typescript
/**
 * Shared backend → frontend types.
 *
 * M2 will regenerate this file from the FastAPI OpenAPI schema via
 * `openapi-typescript`. For M1 we hand-write the only shape we need: the
 * healthz response. Keep this file small until the regen script lands.
 */

export type HealthResponse = {
  status: "ok";
  version: string;
};
```

- [ ] **Step 2: Write the typed fetch wrapper**

Path: `frontend/lib/api/client.ts`

```typescript
import type { HealthResponse } from "@/lib/types/contracts";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  const text = await response.text();
  const body: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(
      `${response.status} ${response.statusText} on ${path}`,
      response.status,
      body,
    );
  }

  return body as T;
}

export const api = {
  healthz: () => request<HealthResponse>("/healthz"),
};
```

- [ ] **Step 3: Replace the home page with a live healthz ping**

Path: `frontend/app/page.tsx` (full replacement)

```typescript
import { api, ApiError } from "@/lib/api/client";

async function fetchHealth() {
  try {
    return { ok: true as const, data: await api.healthz() };
  } catch (error) {
    const message =
      error instanceof ApiError
        ? `${error.status} ${error.message}`
        : error instanceof Error
          ? error.message
          : "unknown error";
    return { ok: false as const, message };
  }
}

export default async function HomePage() {
  const health = await fetchHealth();

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Kodoku</h1>
      <p className="mt-2 text-neutral-600 dark:text-neutral-400">
        Decision Graph AI — tree-of-thoughts planner.
      </p>

      <section className="mt-10 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
          Backend status
        </h2>
        {health.ok ? (
          <p className="mt-1 text-sm">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 align-middle" />{" "}
            <span className="align-middle">
              {health.data.status} (v{health.data.version})
            </span>
          </p>
        ) : (
          <p className="mt-1 text-sm">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500 align-middle" />{" "}
            <span className="align-middle">unreachable — {health.message}</span>
          </p>
        )}
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Run typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: no output, exit code 0.

- [ ] **Step 5: End-to-end smoke**

Run (in three shells):
- Shell A (from repo root): `docker compose up -d`
- Shell B (from `backend/`, venv active): `uvicorn kodoku.main:app --port 8000 --reload`
- Shell C (from `frontend/`): `npm run dev`

Open `http://localhost:3000`. Expected: page shows a green dot and `ok (v0.1.0)` under "Backend status".

Stop Shell C and Shell B with Ctrl-C; leave Postgres running for the next task.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/client.ts frontend/lib/types/contracts.ts frontend/app/page.tsx
git commit -m "feat(frontend): add typed API client and live healthz ping"
```

---

## Task 10: Root README

**Files:**
- Modify: `README.md` (overwrites the one-line placeholder)

- [ ] **Step 1: Write the README**

Path: `README.md`

```markdown
# Kodoku — Decision Graph AI

> Tree-of-thoughts planner that turns a goal into a graph of explored, evaluated,
> and synthesized ideas — with human-in-the-loop checkpoints at every step.

**Status:** M1 (skeleton) in progress. See `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md`
for the full design spec and `docs/architecture.md` for milestone status.

## Stack

- **Frontend:** Next.js 14, TypeScript, Tailwind, Zustand, React Flow (M3+)
- **Backend:** FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2
- **Database:** PostgreSQL 16
- **LLM:** LiteLLM (Claude / OpenAI / OpenRouter / Ollama — wired in M4)
- **Deploy:** Vercel (frontend), Fly.io (backend) — wired in M6

## Quickstart (local dev)

Prereqs: Docker, Node 20+, Python 3.12.

```bash
# 1. Start Postgres
cp .env.example .env
docker compose up -d

# 2. Backend
cd backend
cp .env.example .env
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn kodoku.main:app --reload --port 8000

# 3. Frontend (new shell)
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000` — you should see "Backend status: ok (v0.1.0)".

## Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm run typecheck && npm run lint
```

## Repo layout

```
kodoku/
├── backend/         FastAPI + SQLAlchemy + Alembic
├── frontend/        Next.js 14 app router
├── docs/            architecture notes, spec, plans
└── docker-compose.yml
```

## License

See `LICENSE`.
```

- [ ] **Step 2: Verify rendering**

Open `README.md` in a Markdown previewer (e.g., VS Code preview). Confirm headings and code blocks render cleanly.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: replace placeholder README with M1 quickstart"
```

---

## Task 11: M1 acceptance — full end-to-end verification

This task contains no new code. It runs the full M1 acceptance gate. If any step fails, fix it (or open a follow-up task) before declaring M1 done.

- [ ] **Step 1: Clean checkout test**

Run:
```
git status
```
Expected: `nothing to commit, working tree clean`. If untracked artifacts (build output, env files) appear, add them to `.gitignore` and commit that fix.

- [ ] **Step 2: Backend tests green**

Run (from `backend/`, venv active): `pytest -v`
Expected: all tests pass (`test_settings.py`, `test_health.py`, `test_db_engine.py`).

- [ ] **Step 3: Backend lint + typecheck**

Run (from `backend/`): `ruff check . && mypy kodoku`
Expected: no warnings or errors.

- [ ] **Step 4: Frontend typecheck + lint**

Run (from `frontend/`): `npm run typecheck && npm run lint`
Expected: no errors.

- [ ] **Step 5: Migrations idempotent**

Run (from `backend/`):
```
alembic downgrade base
alembic upgrade head
```
Expected: both succeed; `alembic_version` table ends with the baseline revision.

- [ ] **Step 6: Full stack smoke**

Run in parallel shells:
- `docker compose up -d` (root)
- `uvicorn kodoku.main:app --port 8000` (backend)
- `npm run dev` (frontend)

Visit `http://localhost:3000` — green dot + `ok (v0.1.0)` displayed.

Stop dev processes.

- [ ] **Step 7: Tag the milestone**

```bash
git tag -a m1-skeleton -m "M1 — skeleton + contracts complete"
```

- [ ] **Step 8: Update architecture doc status**

Path: `docs/architecture.md` — change the M1 line to:

```
- M1 — Skeleton + contracts: ✅ complete
```

Commit:
```bash
git add docs/architecture.md
git commit -m "docs: mark M1 milestone complete"
```

---

## Done with M1

Next: write the **M2 — Domain model + REST CRUD** plan against the same spec, against a fresh `m1-skeleton` tag baseline. The spec already locks the schema and REST surface; M2's plan will TDD each table, repository, route, and the sidebar UI.
