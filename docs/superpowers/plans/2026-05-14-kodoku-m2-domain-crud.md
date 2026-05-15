# Kodoku M2 — Domain Model + REST CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the persistence and CRUD surface for Kodoku: the five tables from the spec live in Postgres, sessions can be created/listed/read/renamed/deleted via REST (with the root node created atomically on `POST /sessions`), and the frontend exposes a sidebar list + new-session modal + bare `/s/[sessionId]` shell. No engine, no WebSockets, no AI yet.

**Architecture:** SQLAlchemy 2.x async ORM models (Postgres-only — UUID, JSONB, timestamptz, numeric). Alembic migration `001_initial` creates all five tables. Domain enums live in pure Python and back-stop the Pydantic DTOs. Repositories are thin async wrappers; service-level logic (atomic create-with-root) lives in the session repo. FastAPI router translates DTOs ↔ ORM. OpenAPI schema is the contract surface — `frontend/lib/types/contracts.ts` is regenerated from it via `openapi-typescript` and committed. Frontend: shadcn lands here for the new-session modal; sidebar reads `GET /sessions`; new-session modal POSTs and routes to `/s/[id]`.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0.36 (async), Alembic 1.14, Pydantic v2, asyncpg, pytest-asyncio, Next.js 14, TypeScript 5.7, Tailwind 3.4, shadcn/ui (Radix primitives), `openapi-typescript` 7.x, Zustand 4.

**Spec reference:** `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md` — sections 5 (data model), 6 (REST API), 11 (M2 milestone), 12 (M2 tasks), 14 (repo layout).

**Deviations from the spec, justified:**
- The spec's M2 file list includes `backend/kodoku/api/nodes.py`. Section 6 of the spec does **not** define any standalone node endpoints (only `GET /sessions/{id}` returns a bundle including nodes). Per YAGNI, this plan omits `api/nodes.py` and lets the sessions detail endpoint return the bundle. M3 will introduce per-node routes when the graph UI needs them (e.g. for the node detail panel).
- The M2 verification mentions `backend/tests/test_sessions_api.py`. We use the same path but co-locate the per-table model smoke test in `tests/test_models.py` and the repository test in `tests/test_repo_sessions.py` — narrower files are easier to reason about.

**Baseline assumption:** `m1-skeleton` tag is checked out; `docker compose up -d` brings Postgres up; backend venv is active when running backend commands; frontend has `node_modules` installed.

---

## File Map

### Backend

- Create: `backend/kodoku/domain/enums.py` — string enums for `SessionStatus`, `NodeKind`, `NodeStatus`, `CheckpointKind`
- Create: `backend/kodoku/db/models.py` — SQLAlchemy 2.x ORM models for all five tables + indexes
- Modify: `backend/kodoku/db/base.py` — re-export models so Alembic autogenerate sees them
- Create: `backend/alembic/versions/<timestamp>_001_initial.py` — generated migration (one Alembic revision; slug `001_initial`)
- Create: `backend/kodoku/api/dtos.py` — Pydantic v2 request/response models for sessions API
- Create: `backend/kodoku/repo/__init__.py`
- Create: `backend/kodoku/repo/sessions.py` — async session repository (CRUD + atomic create-with-root + bundle load)
- Create: `backend/kodoku/db/session.py` — `get_db` FastAPI dependency yielding `AsyncSession`
- Create: `backend/kodoku/api/sessions.py` — REST router for `/sessions`
- Modify: `backend/kodoku/main.py` — include the sessions router
- Modify: `backend/tests/conftest.py` — add test-DB fixtures (per-session migration, per-test transaction rollback, dependency override)
- Create: `backend/tests/test_models.py` — smoke test that all models insert + cascade
- Create: `backend/tests/test_repo_sessions.py` — repository-level tests (atomic create, list, get bundle, rename, delete, status guard)
- Create: `backend/tests/test_sessions_api.py` — end-to-end HTTP tests via `httpx.ASGITransport`

### Frontend

- Modify: `frontend/package.json` — add shadcn-adjacent deps (`class-variance-authority`, `clsx`, `tailwind-merge`, `tailwindcss-animate`, `lucide-react`, `@radix-ui/react-dialog`, `@radix-ui/react-label`, `@radix-ui/react-select`, `@radix-ui/react-slot`) and dev dep `openapi-typescript`. Add scripts: `gen:contracts`.
- Modify: `frontend/tailwind.config.ts` — extend theme with shadcn tokens + `tailwindcss-animate` plugin
- Modify: `frontend/app/globals.css` — add shadcn CSS variables (light + dark)
- Create: `frontend/components.json` — shadcn config
- Create: `frontend/lib/utils.ts` — `cn` helper
- Create: `frontend/components/ui/button.tsx`
- Create: `frontend/components/ui/dialog.tsx`
- Create: `frontend/components/ui/input.tsx`
- Create: `frontend/components/ui/label.tsx`
- Create: `frontend/components/ui/select.tsx`
- Create: `frontend/components/ui/textarea.tsx`
- Create: `frontend/scripts/gen-contracts.mjs` — generates `lib/types/contracts.ts` from `/openapi.json`
- Modify: `frontend/lib/types/contracts.ts` — replaced by generated output (committed)
- Modify: `frontend/lib/api/client.ts` — add `listSessions`, `getSession`, `createSession`, `patchSession`, `deleteSession`
- Modify: `frontend/app/page.tsx` — replace healthz placeholder with sidebar + main pane
- Create: `frontend/app/_components/SessionSidebar.tsx`
- Create: `frontend/app/_components/NewSessionDialog.tsx`
- Create: `frontend/app/s/[sessionId]/page.tsx` — session detail shell
- Create: `frontend/state/sessionStore.ts` — Zustand store for sidebar refresh signal (minimal — full state lands in M3)

### Docs

- Modify: `docs/architecture.md` — mark M2 status in progress, then complete at acceptance time
- Modify: `README.md` — add "Regenerating frontend types" subsection

---

## Task 1: Domain enums

**Files:**
- Create: `backend/kodoku/domain/enums.py`
- Test: `backend/tests/test_enums.py`

- [ ] **Step 1: Write the failing test**

Path: `backend/tests/test_enums.py`

```python
from __future__ import annotations

import pytest

from kodoku.domain.enums import (
    CheckpointKind,
    NodeKind,
    NodeStatus,
    SessionStatus,
)


def test_session_status_values() -> None:
    assert SessionStatus.DRAFT.value == "draft"
    assert SessionStatus.RUNNING.value == "running"
    assert SessionStatus.AWAITING_HUMAN.value == "awaiting_human"
    assert SessionStatus.DONE.value == "done"
    assert SessionStatus.ERROR.value == "error"
    assert SessionStatus.PAUSED.value == "paused"


def test_node_kind_values() -> None:
    assert {k.value for k in NodeKind} == {"root", "candidate", "synthesis"}


def test_node_status_values() -> None:
    assert {s.value for s in NodeStatus} == {
        "pending",
        "active",
        "pruned",
        "kept",
        "expanded",
    }


def test_checkpoint_kind_values() -> None:
    assert {c.value for c in CheckpointKind} == {
        "post_expand",
        "post_evaluate",
        "pre_synthesis",
    }


def test_enums_are_str_subclass() -> None:
    """JSON-friendly: each enum is a str so it serialises directly."""
    assert isinstance(SessionStatus.DRAFT, str)
    assert SessionStatus.DRAFT == "draft"
```

- [ ] **Step 2: Run, expect failure**

Run (from `backend/`): `pytest tests/test_enums.py -v`
Expected: `ModuleNotFoundError: No module named 'kodoku.domain.enums'`.

- [ ] **Step 3: Implement enums**

Path: `backend/kodoku/domain/enums.py`

```python
"""Domain enums — string-valued so they serialise straight into JSON / DB."""
from __future__ import annotations

from enum import StrEnum


class SessionStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    DONE = "done"
    ERROR = "error"
    PAUSED = "paused"


class NodeKind(StrEnum):
    ROOT = "root"
    CANDIDATE = "candidate"
    SYNTHESIS = "synthesis"


class NodeStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PRUNED = "pruned"
    KEPT = "kept"
    EXPANDED = "expanded"


class CheckpointKind(StrEnum):
    POST_EXPAND = "post_expand"
    POST_EVALUATE = "post_evaluate"
    PRE_SYNTHESIS = "pre_synthesis"
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_enums.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/kodoku/domain/enums.py backend/tests/test_enums.py
git commit -m "feat(domain): add string enums for session, node, checkpoint kinds"
```

---

## Task 2: SQLAlchemy models + test-DB conftest

**Files:**
- Create: `backend/kodoku/db/models.py`
- Modify: `backend/kodoku/db/base.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Extend conftest with a test database**

Replace `backend/tests/conftest.py` entirely (the existing `_isolate_env` fixture is preserved):

```python
"""Shared pytest fixtures for Kodoku backend tests."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kodoku.db.base import Base
from kodoku.db import models  # noqa: F401  — register mappers


TEST_DB_NAME = "kodoku_test"


def _admin_dsn() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku",
    )
    # asyncpg admin connection wants the `postgres` maintenance DB, plain driver.
    parsed = urlparse(raw.replace("+asyncpg", ""))
    return urlunparse(parsed._replace(path="/postgres"))


def _test_db_url() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kodoku:kodoku@localhost:5432/kodoku",
    )
    parsed = urlparse(raw)
    return urlunparse(parsed._replace(path=f"/{TEST_DB_NAME}"))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean, deterministic env."""
    for key in list(os.environ):
        if key.startswith(("APP_ENV", "LOG_LEVEL", "ALLOWED_ORIGINS")):
            monkeypatch.delenv(key, raising=False)
    # Always point at the test DB.
    monkeypatch.setenv("DATABASE_URL", _test_db_url())

    from kodoku.settings import get_settings

    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session")
async def _bootstrap_test_db() -> AsyncIterator[None]:
    """Create the test database (if absent) and create all tables once."""
    admin = await asyncpg.connect(dsn=_admin_dsn())
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await admin.close()

    engine = create_async_engine(_test_db_url(), future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_engine(_bootstrap_test_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_test_db_url(), future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test session wrapped in a transaction that always rolls back."""
    connection = await db_engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def truncate_all(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Available for tests that bypass the per-test transaction (e.g. HTTP tests)."""
    yield
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE events, checkpoints, evaluations, nodes, sessions "
                "RESTART IDENTITY CASCADE"
            )
        )
```

> Note: `pytest_asyncio` was already pinned in M1's `pyproject.toml`. `asyncio_mode = "auto"` is set, so `pytest_asyncio.fixture` works without extra markers.

- [ ] **Step 2: Update `db/base.py` to expose `Base` only**

`db/base.py` already defines `Base`. Confirm by reading it. No edit needed at this step — the conftest does `from kodoku.db import models` to load mappers onto `Base.metadata`, so all we need is for `models.py` to be importable in Task 2/Step 3.

- [ ] **Step 3: Write the failing model smoke test**

Path: `backend/tests/test_models.py`

```python
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.models import (
    Checkpoint,
    Evaluation,
    Event,
    Node,
    Session as SessionModel,
)
from kodoku.domain.enums import (
    CheckpointKind,
    NodeKind,
    NodeStatus,
    SessionStatus,
)


@pytest.mark.asyncio
async def test_session_round_trip(db_session: AsyncSession) -> None:
    s = SessionModel(
        title="Side projects in AI + music",
        goal="Brainstorm side projects combining AI and music",
        status=SessionStatus.DRAFT.value,
        config={"model": "anthropic/claude-sonnet-4-6", "branching_factor": 3, "max_depth": 3, "temperature": 0.7},
    )
    db_session.add(s)
    await db_session.flush()

    fetched = (await db_session.execute(select(SessionModel).where(SessionModel.id == s.id))).scalar_one()
    assert fetched.user_id == "local"
    assert fetched.title == "Side projects in AI + music"
    assert fetched.status == "draft"
    assert fetched.config["model"] == "anthropic/claude-sonnet-4-6"
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_node_cascade_delete(db_session: AsyncSession) -> None:
    s = SessionModel(
        title="t", goal="goal goal goal", status=SessionStatus.DRAFT.value, config={}
    )
    db_session.add(s)
    await db_session.flush()

    root = Node(
        session_id=s.id, parent_id=None, depth=0,
        kind=NodeKind.ROOT.value, title="t", content="goal goal goal",
        status=NodeStatus.ACTIVE.value,
    )
    db_session.add(root)
    await db_session.flush()

    child = Node(
        session_id=s.id, parent_id=root.id, depth=1,
        kind=NodeKind.CANDIDATE.value, title="c", content="content content",
        status=NodeStatus.PENDING.value,
    )
    db_session.add(child)
    await db_session.flush()

    await db_session.delete(s)
    await db_session.flush()

    remaining = (await db_session.execute(select(Node))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_evaluation_round_trip(db_session: AsyncSession) -> None:
    s = SessionModel(title="t", goal="goal goal goal", status="draft", config={})
    db_session.add(s)
    await db_session.flush()
    n = Node(
        session_id=s.id, parent_id=None, depth=0,
        kind="candidate", title="c", content="x x x", status="pending",
    )
    db_session.add(n)
    await db_session.flush()

    e = Evaluation(
        node_id=n.id,
        score=Decimal("7.50"),
        critique="solid",
        dimensions={"feasibility": 8, "novelty": 7, "impact": 7, "effort": 5, "fit": 8},
        model="anthropic/claude-sonnet-4-6",
    )
    db_session.add(e)
    await db_session.flush()

    fetched = (await db_session.execute(select(Evaluation))).scalar_one()
    assert fetched.score == Decimal("7.50")
    assert fetched.dimensions["feasibility"] == 8


@pytest.mark.asyncio
async def test_checkpoint_and_event(db_session: AsyncSession) -> None:
    s = SessionModel(title="t", goal="goal goal goal", status="awaiting_human", config={})
    db_session.add(s)
    await db_session.flush()

    cp = Checkpoint(
        session_id=s.id,
        kind=CheckpointKind.POST_EVALUATE.value,
        payload={"prune": [], "expand": [], "keep": []},
        decision=None,
    )
    ev = Event(
        session_id=s.id,
        type="checkpoint.reached",
        payload={"checkpoint_id": "00000000-0000-0000-0000-000000000000"},
    )
    db_session.add_all([cp, ev])
    await db_session.flush()

    assert cp.id is not None
    assert isinstance(ev.id, int) and ev.id > 0
```

- [ ] **Step 4: Run, expect failure**

Run: `pytest tests/test_models.py -v`
Expected: `ModuleNotFoundError: No module named 'kodoku.db.models'`.

- [ ] **Step 5: Implement the ORM models**

Path: `backend/kodoku/db/models.py`

```python
"""SQLAlchemy 2.x ORM models for Kodoku.

Schema mirrors section 5 of the design spec. All ids are UUID v4 except
`events.id` which is bigserial for cheap monotonic ordering.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kodoku.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String, nullable=False, default="local", server_default="local"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    current_step: Mapped[str | None] = mapped_column(String, nullable=True)
    final_synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    nodes: Mapped[list["Node"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    checkpoints: Mapped[list["Checkpoint"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="nodes")
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_nodes_session_id_parent_id", "session_id", "parent_id"),
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    critique: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    node: Mapped["Node"] = relationship(back_populates="evaluations")

    __table_args__ = (Index("ix_evaluations_node_id", "node_id"),)


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="checkpoints")

    __table_args__ = (
        Index("ix_checkpoints_session_id_resolved_at", "session_id", "resolved_at"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="events")

    __table_args__ = (Index("ix_events_session_id_id", "session_id", "id"),)
```

- [ ] **Step 6: Run model tests, expect pass**

Confirm Postgres is up: `docker compose ps` → `running (healthy)`.

Run: `pytest tests/test_models.py -v`
Expected: 4 passed. (The first run creates the `kodoku_test` database; subsequent runs reuse it.)

- [ ] **Step 7: Re-run pre-existing tests to confirm no regressions**

Run: `pytest tests/test_settings.py tests/test_health.py tests/test_db_engine.py -v`
Expected: all M1 tests still pass.

- [ ] **Step 8: Commit**

```bash
git add backend/kodoku/db/models.py backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat(db): add SQLAlchemy models for sessions, nodes, evaluations, checkpoints, events"
```

---

## Task 3: Alembic migration `001_initial`

**Files:**
- Create: `backend/alembic/versions/<timestamp>_<rev>_001_initial.py`

- [ ] **Step 1: Wipe the dev DB so autogenerate diffs from empty**

```bash
docker exec kodoku-postgres psql -U kodoku -d kodoku -c "DROP TABLE IF EXISTS alembic_version CASCADE;"
```

Run (from `backend/`): `alembic downgrade base`
Expected: exits cleanly (no-op if no version tracked).

For clarity, drop any leftover M1 baseline migration's effect by deleting the auto-generated baseline file from M1's `versions/` if it exists. Inspect:
```bash
ls backend/alembic/versions
```
If a baseline file exists from M1 (its `upgrade()` body is `pass`), keep it — Alembic chains revisions. We just need the new revision to depend on that baseline. `alembic revision --autogenerate` does this for us.

- [ ] **Step 2: Make alembic see all the models**

`alembic/env.py` already imports `Base` from `kodoku.db.base`. It needs `kodoku.db.models` to be imported so the mappers register on `Base.metadata`. Add the import.

Modify: `backend/alembic/env.py` — after `from kodoku.db.base import Base`, add:

```python
from kodoku.db import models  # noqa: F401  — register mappers for autogenerate
```

- [ ] **Step 3: Autogenerate the migration**

Run (from `backend/`): `alembic revision --autogenerate -m "001_initial"`
Expected: a new file appears under `backend/alembic/versions/` with a name like `20260514_HHMM_<rev>_001_initial.py`. Open it and verify the `upgrade()` body creates all five tables (`sessions`, `nodes`, `evaluations`, `checkpoints`, `events`) and all the indexes from Task 2's `__table_args__`. The `downgrade()` body should drop them in reverse order.

Common autogenerate quirks to fix by hand if needed:
- If autogenerate emits a separate `op.create_index` line for an FK index (e.g. `ix_nodes_session_id`) that we did **not** declare, leave it alone — Postgres FKs benefit from the index anyway.
- If autogenerate orders index creation before the table they reference (rare), Alembic handles this automatically. No manual reorder required.

- [ ] **Step 4: Apply the migration to the dev DB**

Run: `alembic upgrade head`
Expected last line: `INFO  [alembic.runtime.migration] Running upgrade <baseline_rev> -> <new_rev>, 001_initial`.

- [ ] **Step 5: Verify schema in Postgres**

```bash
docker exec kodoku-postgres psql -U kodoku -d kodoku -c "\dt"
```
Expected output includes rows for `sessions`, `nodes`, `evaluations`, `checkpoints`, `events`, `alembic_version`.

```bash
docker exec kodoku-postgres psql -U kodoku -d kodoku -c "\d nodes"
```
Confirm `session_id` and `parent_id` foreign keys, `created_at` default `now()`, and the composite index `ix_nodes_session_id_parent_id`.

- [ ] **Step 6: Test the migration round trip**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: both succeed. Then re-verify with `\dt`.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/ backend/alembic/env.py
git commit -m "feat(db): add 001_initial migration creating all five domain tables"
```

---

## Task 4: Pydantic DTOs for the sessions API

**Files:**
- Create: `backend/kodoku/api/dtos.py`
- Test: `backend/tests/test_dtos.py`

- [ ] **Step 1: Write the failing test**

Path: `backend/tests/test_dtos.py`

```python
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kodoku.api.dtos import (
    EvaluationDTO,
    NodeDTO,
    SessionCreate,
    SessionDetailResponse,
    SessionListItem,
    SessionConfig,
    SessionResponse,
    SessionUpdate,
)


def test_session_config_defaults() -> None:
    cfg = SessionConfig()
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.branching_factor == 3
    assert cfg.max_depth == 3
    assert cfg.temperature == 0.7


def test_session_config_rejects_bad_model_string() -> None:
    with pytest.raises(ValidationError):
        SessionConfig(model="not a valid model string")


def test_session_config_branching_factor_bounds() -> None:
    with pytest.raises(ValidationError):
        SessionConfig(branching_factor=0)
    with pytest.raises(ValidationError):
        SessionConfig(branching_factor=11)


def test_session_create_requires_goal() -> None:
    with pytest.raises(ValidationError):
        SessionCreate(goal="too short")


def test_session_create_title_optional() -> None:
    body = SessionCreate(goal="Brainstorm side-project ideas combining AI and music.")
    assert body.title is None
    assert body.config is None


def test_session_create_with_full_payload() -> None:
    body = SessionCreate(
        goal="Brainstorm side-project ideas combining AI and music.",
        title="AI + music projects",
        config=SessionConfig(branching_factor=4, max_depth=2),
    )
    assert body.title == "AI + music projects"
    assert body.config is not None
    assert body.config.branching_factor == 4


def test_session_update_allows_partial() -> None:
    body = SessionUpdate(title="renamed")
    assert body.title == "renamed"
    assert body.config is None


def test_session_response_roundtrip_uuid_and_datetime() -> None:
    sid = uuid4()
    now = datetime.now(timezone.utc)
    payload = {
        "id": str(sid),
        "user_id": "local",
        "title": "t",
        "goal": "goal goal goal goal goal",
        "status": "draft",
        "config": {"model": "anthropic/claude-sonnet-4-6"},
        "current_step": None,
        "final_synthesis": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    parsed = SessionResponse.model_validate(payload)
    assert parsed.id == sid
    assert parsed.status == "draft"


def test_session_detail_response_bundles_nested() -> None:
    sid = uuid4()
    nid = uuid4()
    now = datetime.now(timezone.utc)
    payload = {
        "id": sid,
        "user_id": "local",
        "title": "t",
        "goal": "goal goal goal goal goal",
        "status": "draft",
        "config": {},
        "current_step": None,
        "final_synthesis": None,
        "created_at": now,
        "updated_at": now,
        "nodes": [
            {
                "id": nid,
                "session_id": sid,
                "parent_id": None,
                "depth": 0,
                "kind": "root",
                "title": "Root",
                "content": "goal goal goal goal goal",
                "status": "active",
                "created_at": now,
            }
        ],
        "evaluations": [],
        "checkpoints": [],
    }
    detail = SessionDetailResponse.model_validate(payload)
    assert len(detail.nodes) == 1
    assert detail.nodes[0].kind == "root"


def test_session_list_item_omits_heavy_fields() -> None:
    """List endpoint returns only the columns the sidebar needs."""
    fields = set(SessionListItem.model_fields.keys())
    assert fields == {
        "id",
        "title",
        "status",
        "current_step",
        "created_at",
        "updated_at",
    }
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_dtos.py -v`
Expected: `ModuleNotFoundError: No module named 'kodoku.api.dtos'`.

- [ ] **Step 3: Implement the DTOs**

Path: `backend/kodoku/api/dtos.py`

```python
"""Pydantic v2 request/response models for the sessions API."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kodoku.domain.enums import (
    CheckpointKind,
    NodeKind,
    NodeStatus,
    SessionStatus,
)

_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._\-:/]*$")


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "anthropic/claude-sonnet-4-6"
    branching_factor: int = Field(default=3, ge=1, le=10)
    max_depth: int = Field(default=3, ge=1, le=10)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        if " " in value or not _MODEL_RE.match(value):
            raise ValueError("model must be a LiteLLM-style identifier (e.g. 'anthropic/claude-sonnet-4-6')")
        return value


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=10, max_length=4000)
    title: str | None = Field(default=None, max_length=200)
    config: SessionConfig | None = None


class SessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    config: SessionConfig | None = None


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NodeDTO(_ORM):
    id: UUID
    session_id: UUID
    parent_id: UUID | None
    depth: int
    kind: NodeKind
    title: str
    content: str
    status: NodeStatus
    created_at: datetime


class EvaluationDTO(_ORM):
    id: UUID
    node_id: UUID
    score: Decimal
    critique: str
    dimensions: dict[str, Any]
    model: str
    created_at: datetime


class CheckpointDTO(_ORM):
    id: UUID
    session_id: UUID
    kind: CheckpointKind
    payload: dict[str, Any]
    decision: dict[str, Any] | None
    resolved_at: datetime | None
    created_at: datetime


class SessionResponse(_ORM):
    id: UUID
    user_id: str
    title: str
    goal: str
    status: SessionStatus
    config: dict[str, Any]
    current_step: str | None
    final_synthesis: str | None
    created_at: datetime
    updated_at: datetime


class SessionListItem(_ORM):
    id: UUID
    title: str
    status: SessionStatus
    current_step: str | None
    created_at: datetime
    updated_at: datetime


class SessionDetailResponse(SessionResponse):
    nodes: list[NodeDTO]
    evaluations: list[EvaluationDTO]
    checkpoints: list[CheckpointDTO]


class SessionCreateResponse(BaseModel):
    session_id: UUID
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_dtos.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/kodoku/api/dtos.py backend/tests/test_dtos.py
git commit -m "feat(api): add Pydantic DTOs for sessions request/response shapes"
```

---

## Task 5: Session repository (CRUD + atomic create-with-root)

**Files:**
- Create: `backend/kodoku/repo/__init__.py`
- Create: `backend/kodoku/repo/sessions.py`
- Test: `backend/tests/test_repo_sessions.py`

- [ ] **Step 1: Write the failing tests**

Path: `backend/tests/test_repo_sessions.py`

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import SessionConfig, SessionCreate, SessionUpdate
from kodoku.db.models import Node, Session as SessionModel
from kodoku.domain.enums import NodeKind, NodeStatus, SessionStatus
from kodoku.repo.sessions import (
    SessionMutationNotAllowed,
    SessionNotFound,
    SessionRepository,
)


@pytest.mark.asyncio
async def test_create_session_atomically_creates_root_node(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    payload = SessionCreate(goal="Brainstorm side-project ideas combining AI and music.")
    session = await repo.create(payload)

    assert session.status == SessionStatus.DRAFT.value
    assert session.user_id == "local"
    assert session.title.startswith("Brainstorm side-project")
    assert session.config["model"] == "anthropic/claude-sonnet-4-6"

    nodes = await repo.list_nodes(session.id)
    assert len(nodes) == 1
    root = nodes[0]
    assert root.kind == NodeKind.ROOT.value
    assert root.parent_id is None
    assert root.depth == 0
    assert root.status == NodeStatus.ACTIVE.value
    assert root.content == payload.goal


@pytest.mark.asyncio
async def test_create_session_with_custom_title_and_config(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    payload = SessionCreate(
        goal="Plan a six-week sabbatical that builds my portfolio.",
        title="Sabbatical plan",
        config=SessionConfig(branching_factor=5, max_depth=2, temperature=0.5),
    )
    session = await repo.create(payload)

    assert session.title == "Sabbatical plan"
    assert session.config["branching_factor"] == 5
    assert session.config["max_depth"] == 2
    assert session.config["temperature"] == 0.5


@pytest.mark.asyncio
async def test_list_returns_all_sessions(db_session: AsyncSession) -> None:
    """Repo-level test only verifies the listing returns every session.

    Postgres `now()` returns transaction-start time, so multiple rows created
    within the per-test transaction share `updated_at` and ordering between
    them is non-deterministic. The recency-ordering contract is verified by
    `test_sessions_api.py::test_list_returns_summary_rows_in_recency_order`,
    where each HTTP request runs in its own transaction.
    """
    repo = SessionRepository(db_session)
    a = await repo.create(SessionCreate(goal="First goal goal goal."))
    b = await repo.create(SessionCreate(goal="Second goal goal goal."))
    c = await repo.create(SessionCreate(goal="Third goal goal goal."))

    listed = await repo.list_summaries()
    assert {s.id for s in listed} == {a.id, b.id, c.id}


@pytest.mark.asyncio
async def test_get_bundle_returns_session_with_relations(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Bundle goal goal goal."))

    bundle = await repo.get_bundle(created.id)
    assert bundle.session.id == created.id
    assert len(bundle.nodes) == 1
    assert bundle.evaluations == []
    assert bundle.checkpoints == []


@pytest.mark.asyncio
async def test_get_bundle_raises_for_missing(db_session: AsyncSession) -> None:
    import uuid

    repo = SessionRepository(db_session)
    with pytest.raises(SessionNotFound):
        await repo.get_bundle(uuid.uuid4())


@pytest.mark.asyncio
async def test_rename_updates_title(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Rename goal goal goal."))

    updated = await repo.update(created.id, SessionUpdate(title="New title"))
    assert updated.title == "New title"


@pytest.mark.asyncio
async def test_update_blocked_when_running(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Running goal goal goal."))
    # Simulate engine flipping it to running.
    created.status = SessionStatus.RUNNING.value
    await db_session.flush()

    with pytest.raises(SessionMutationNotAllowed):
        await repo.update(created.id, SessionUpdate(title="nope"))


@pytest.mark.asyncio
async def test_delete_cascades_nodes(db_session: AsyncSession) -> None:
    from sqlalchemy import select

    repo = SessionRepository(db_session)
    created = await repo.create(SessionCreate(goal="Delete goal goal goal."))

    await repo.delete(created.id)

    remaining_sessions = (await db_session.execute(select(SessionModel))).scalars().all()
    remaining_nodes = (await db_session.execute(select(Node))).scalars().all()
    assert remaining_sessions == []
    assert remaining_nodes == []


@pytest.mark.asyncio
async def test_delete_raises_for_missing(db_session: AsyncSession) -> None:
    import uuid

    repo = SessionRepository(db_session)
    with pytest.raises(SessionNotFound):
        await repo.delete(uuid.uuid4())
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_repo_sessions.py -v`
Expected: `ModuleNotFoundError: No module named 'kodoku.repo.sessions'`.

- [ ] **Step 3: Implement the repository**

Path: `backend/kodoku/repo/__init__.py` (empty file)

Path: `backend/kodoku/repo/sessions.py`

```python
"""Async repository for the `sessions` aggregate.

The engine is the only writer for nodes, evaluations, and checkpoints — except
for the root node, which is created atomically with the session at
`POST /sessions` time. That single carve-out lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kodoku.api.dtos import SessionConfig, SessionCreate, SessionUpdate
from kodoku.db.models import (
    Checkpoint,
    Evaluation,
    Node,
    Session as SessionModel,
)
from kodoku.domain.enums import NodeKind, NodeStatus, SessionStatus


class SessionNotFound(LookupError):
    """Raised when a session id does not exist."""


class SessionMutationNotAllowed(RuntimeError):
    """Raised when a session is in a state that disallows the requested mutation."""


@dataclass(slots=True)
class SessionBundle:
    session: SessionModel
    nodes: list[Node]
    evaluations: list[Evaluation]
    checkpoints: list[Checkpoint]


_MUTABLE_STATUSES = frozenset({SessionStatus.DRAFT.value, SessionStatus.DONE.value, SessionStatus.ERROR.value, SessionStatus.PAUSED.value})


def _derive_title(goal: str) -> str:
    head = goal.strip().splitlines()[0]
    if len(head) <= 60:
        return head
    return head[:57].rstrip() + "…"


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, payload: SessionCreate) -> SessionModel:
        config = (payload.config or SessionConfig()).model_dump()
        title = payload.title or _derive_title(payload.goal)

        session = SessionModel(
            title=title,
            goal=payload.goal,
            status=SessionStatus.DRAFT.value,
            config=config,
            current_step=None,
            final_synthesis=None,
        )
        self._db.add(session)
        await self._db.flush()

        root = Node(
            session_id=session.id,
            parent_id=None,
            depth=0,
            kind=NodeKind.ROOT.value,
            title=title,
            content=payload.goal,
            status=NodeStatus.ACTIVE.value,
        )
        self._db.add(root)
        await self._db.flush()
        return session

    async def list_summaries(self) -> list[SessionModel]:
        stmt = select(SessionModel).order_by(SessionModel.updated_at.desc())
        return list((await self._db.execute(stmt)).scalars().all())

    async def get(self, session_id: UUID) -> SessionModel:
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        try:
            return (await self._db.execute(stmt)).scalar_one()
        except NoResultFound as exc:
            raise SessionNotFound(str(session_id)) from exc

    async def list_nodes(self, session_id: UUID) -> list[Node]:
        stmt = (
            select(Node)
            .where(Node.session_id == session_id)
            .order_by(Node.depth.asc(), Node.created_at.asc())
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def get_bundle(self, session_id: UUID) -> SessionBundle:
        stmt = (
            select(SessionModel)
            .where(SessionModel.id == session_id)
            .options(
                selectinload(SessionModel.nodes).selectinload(Node.evaluations),
                selectinload(SessionModel.checkpoints),
            )
        )
        result = (await self._db.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise SessionNotFound(str(session_id))
        nodes = sorted(result.nodes, key=lambda n: (n.depth, n.created_at))
        evaluations = [e for n in nodes for e in n.evaluations]
        checkpoints = sorted(result.checkpoints, key=lambda c: c.created_at)
        return SessionBundle(
            session=result,
            nodes=nodes,
            evaluations=evaluations,
            checkpoints=checkpoints,
        )

    async def update(self, session_id: UUID, payload: SessionUpdate) -> SessionModel:
        session = await self.get(session_id)
        if session.status not in _MUTABLE_STATUSES:
            raise SessionMutationNotAllowed(
                f"cannot edit session in status {session.status!r}"
            )
        if payload.title is not None:
            session.title = payload.title
        if payload.config is not None:
            session.config = payload.config.model_dump()
        await self._db.flush()
        return session

    async def delete(self, session_id: UUID) -> None:
        session = await self.get(session_id)
        await self._db.delete(session)
        await self._db.flush()
```

> Note: the repo never commits. Callers (the FastAPI `get_db` dependency in Task 6, and the per-test transaction in `conftest.py`) own transaction boundaries. The repo only `flush()`es so generated ids are available within the unit of work.

- [ ] **Step 4: Run repo tests**

Run: `pytest tests/test_repo_sessions.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/kodoku/repo/ backend/tests/test_repo_sessions.py
git commit -m "feat(repo): add session repository with atomic create-with-root"
```

---

## Task 6: `get_db` dependency + sessions REST router

**Files:**
- Create: `backend/kodoku/db/session.py`
- Create: `backend/kodoku/api/sessions.py`
- Modify: `backend/kodoku/main.py`
- Test: `backend/tests/test_sessions_api.py`

- [ ] **Step 1: Write the `get_db` dependency**

Path: `backend/kodoku/db/session.py`

```python
"""FastAPI dependency that yields an `AsyncSession` and commits on success."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.engine import get_sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 2: Write the failing API tests**

Path: `backend/tests/test_sessions_api.py`

```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from kodoku.db.session import get_db
from kodoku.main import create_app


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine,
    truncate_all: None,
) -> AsyncIterator[AsyncClient]:
    """HTTP client whose `get_db` dependency points at the test database."""
    sessionmaker = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_session_returns_201_with_id(client: AsyncClient) -> None:
    response = await client.post(
        "/sessions",
        json={"goal": "Brainstorm side-project ideas combining AI and music."},
    )
    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body


@pytest.mark.asyncio
async def test_create_then_get_bundles_root_node(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan a six-week sabbatical that builds my portfolio."},
    )).json()

    fetched = await client.get(f"/sessions/{created['session_id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "draft"
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["kind"] == "root"
    assert body["evaluations"] == []
    assert body["checkpoints"] == []


@pytest.mark.asyncio
async def test_list_returns_summary_rows_in_recency_order(client: AsyncClient) -> None:
    a = (await client.post("/sessions", json={"goal": "First goal goal goal."})).json()
    b = (await client.post("/sessions", json={"goal": "Second goal goal goal."})).json()
    c = (await client.post("/sessions", json={"goal": "Third goal goal goal."})).json()

    listed = await client.get("/sessions")
    assert listed.status_code == 200
    rows = listed.json()
    ids = [row["id"] for row in rows]
    assert ids == [c["session_id"], b["session_id"], a["session_id"]]
    assert "goal" not in rows[0]  # summary view


@pytest.mark.asyncio
async def test_patch_renames_session(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Rename goal goal goal goal."},
    )).json()

    response = await client.patch(
        f"/sessions/{created['session_id']}",
        json={"title": "Renamed"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


@pytest.mark.asyncio
async def test_patch_rejects_when_running(client: AsyncClient, db_engine: AsyncEngine) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Running session goal goal goal."},
    )).json()
    # Force status into 'running' through a raw update.
    from sqlalchemy import text

    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE sessions SET status='running' WHERE id = :id"),
            {"id": created["session_id"]},
        )

    response = await client.patch(
        f"/sessions/{created['session_id']}",
        json={"title": "should fail"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_removes_session_and_root(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Delete goal goal goal goal."},
    )).json()

    response = await client.delete(f"/sessions/{created['session_id']}")
    assert response.status_code == 204

    follow_up = await client.get(f"/sessions/{created['session_id']}")
    assert follow_up.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_id_returns_404(client: AsyncClient) -> None:
    import uuid

    response = await client.get(f"/sessions/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_goal_returns_422(client: AsyncClient) -> None:
    response = await client.post("/sessions", json={"goal": "short"})
    assert response.status_code == 422
```

- [ ] **Step 3: Run, expect failure**

Run: `pytest tests/test_sessions_api.py -v`
Expected: `ModuleNotFoundError` or 404s — the router isn't wired yet.

- [ ] **Step 4: Implement the router**

Path: `backend/kodoku/api/sessions.py`

```python
"""REST API for sessions."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import (
    SessionCreate,
    SessionCreateResponse,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)
from kodoku.db.session import get_db
from kodoku.repo.sessions import (
    SessionMutationNotAllowed,
    SessionNotFound,
    SessionRepository,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _repo(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreate,
    repo: SessionRepository = Depends(_repo),
) -> SessionCreateResponse:
    session = await repo.create(payload)
    return SessionCreateResponse(session_id=session.id)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    repo: SessionRepository = Depends(_repo),
) -> list[SessionListItem]:
    rows = await repo.list_summaries()
    return [SessionListItem.model_validate(r) for r in rows]


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    repo: SessionRepository = Depends(_repo),
) -> SessionDetailResponse:
    try:
        bundle = await repo.get_bundle(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    return SessionDetailResponse.model_validate({
        **SessionResponse.model_validate(bundle.session).model_dump(),
        "nodes": bundle.nodes,
        "evaluations": bundle.evaluations,
        "checkpoints": bundle.checkpoints,
    })


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: UUID,
    payload: SessionUpdate,
    repo: SessionRepository = Depends(_repo),
) -> SessionResponse:
    try:
        session = await repo.update(session_id, payload)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except SessionMutationNotAllowed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SessionResponse.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    repo: SessionRepository = Depends(_repo),
) -> None:
    try:
        await repo.delete(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
```

- [ ] **Step 5: Wire the router into the app**

Edit `backend/kodoku/main.py`:

Old:
```python
from kodoku.api.health import router as health_router
```
New:
```python
from kodoku.api.health import router as health_router
from kodoku.api.sessions import router as sessions_router
```

Old:
```python
    app.include_router(health_router)

    return app
```
New:
```python
    app.include_router(health_router)
    app.include_router(sessions_router)

    return app
```

- [ ] **Step 6: Run API tests**

Run: `pytest tests/test_sessions_api.py -v`
Expected: 8 passed.

- [ ] **Step 7: Full backend test sweep**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Manual smoke test through uvicorn**

```bash
uvicorn kodoku.main:app --port 8000
```
In a second shell:
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"goal":"Brainstorm side-project ideas combining AI and music."}'
```
Expected: `{"session_id":"<uuid>"}` with HTTP 201.
```bash
curl http://localhost:8000/sessions
```
Expected: a JSON array with one summary row.

Stop uvicorn.

- [ ] **Step 9: Commit**

```bash
git add backend/kodoku/db/session.py backend/kodoku/api/sessions.py backend/kodoku/main.py backend/tests/test_sessions_api.py
git commit -m "feat(api): add sessions REST router (create/list/get/patch/delete)"
```

---

## Task 7: OpenAPI → `contracts.ts` regen script

**Files:**
- Create: `frontend/scripts/gen-contracts.mjs`
- Modify: `frontend/package.json` — add `openapi-typescript` devDep + `gen:contracts` script
- Modify: `frontend/lib/types/contracts.ts` — replaced by generated output
- Modify: `README.md` — add regen instructions

- [ ] **Step 1: Install `openapi-typescript`**

Run (from `frontend/`): `npm install --save-dev openapi-typescript@7.4.4`
Expected: lockfile updated, no errors.

- [ ] **Step 2: Add the regen script**

Path: `frontend/scripts/gen-contracts.mjs`

```javascript
#!/usr/bin/env node
/**
 * Regenerate `lib/types/contracts.ts` from the running backend's OpenAPI spec.
 *
 * Usage:
 *   1. Start the backend: `uvicorn kodoku.main:app --port 8000`
 *   2. From `frontend/`: `npm run gen:contracts`
 *   3. Commit the diff to `lib/types/contracts.ts`.
 *
 * In M6 this becomes a CI check that fails when contracts drift.
 */
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import openapiTS, { astToString } from "openapi-typescript";

const BACKEND = process.env.KODOKU_BACKEND_URL ?? "http://localhost:8000";
const OUTPUT = resolve(process.cwd(), "lib/types/contracts.ts");

const HEADER = `/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Regenerate with: \`npm run gen:contracts\` (backend must be running on
 * \${KODOKU_BACKEND_URL:-http://localhost:8000}).
 */
/* eslint-disable */

`;

const url = new URL("/openapi.json", BACKEND).toString();
console.log(`Fetching OpenAPI schema from ${url}…`);

const ast = await openapiTS(new URL(url));
const body = astToString(ast);
await writeFile(OUTPUT, HEADER + body, "utf8");
console.log(`Wrote ${OUTPUT}`);
```

- [ ] **Step 3: Update `frontend/package.json`**

Add to `"scripts"`:
```json
    "gen:contracts": "node scripts/gen-contracts.mjs"
```

The `devDependencies` block should now include `"openapi-typescript": "7.4.4"` (from the `npm install` step).

- [ ] **Step 4: Generate and inspect**

Start the backend in one shell:
```bash
cd backend
uvicorn kodoku.main:app --port 8000
```
From `frontend/` in another shell:
```bash
npm run gen:contracts
```
Expected console output:
```
Fetching OpenAPI schema from http://localhost:8000/openapi.json…
Wrote .../frontend/lib/types/contracts.ts
```

Open `frontend/lib/types/contracts.ts`. Confirm it contains:
- A `paths` interface with `/healthz`, `/sessions`, `/sessions/{session_id}`
- A `components.schemas` block with `SessionCreate`, `SessionResponse`, `SessionDetailResponse`, `SessionListItem`, `NodeDTO`, etc.

Stop uvicorn.

- [ ] **Step 5: Re-export the names downstream code expects**

The hand-written placeholder used `HealthResponse`. The generated file exposes schemas via `components["schemas"]`. Append the following named re-exports at the bottom of the generated file (the script's header noted "AUTO-GENERATED" — these re-exports go in a separate companion file instead, so regeneration doesn't wipe them).

Create: `frontend/lib/types/api.ts`

```typescript
import type { components, paths } from "@/lib/types/contracts";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type SessionCreate = components["schemas"]["SessionCreate"];
export type SessionCreateResponse = components["schemas"]["SessionCreateResponse"];
export type SessionResponse = components["schemas"]["SessionResponse"];
export type SessionListItem = components["schemas"]["SessionListItem"];
export type SessionDetailResponse = components["schemas"]["SessionDetailResponse"];
export type SessionUpdate = components["schemas"]["SessionUpdate"];
export type SessionConfig = components["schemas"]["SessionConfig"];
export type NodeDTO = components["schemas"]["NodeDTO"];
export type EvaluationDTO = components["schemas"]["EvaluationDTO"];
export type CheckpointDTO = components["schemas"]["CheckpointDTO"];

export type ListSessionsPath = paths["/sessions"]["get"];
export type CreateSessionPath = paths["/sessions"]["post"];
export type GetSessionPath = paths["/sessions/{session_id}"]["get"];
```

- [ ] **Step 6: Typecheck**

Run (from `frontend/`): `npm run typecheck`
Expected: no errors (the old `HealthResponse` import in `app/page.tsx` still works because we re-export it from `api.ts`; we update the import in Task 10).

- [ ] **Step 7: Update README with regen instructions**

In `README.md`, under the existing `## Tests` section, add a new section above `## Repo layout`:

```markdown
## Regenerating frontend types

`frontend/lib/types/contracts.ts` is generated from the backend's OpenAPI
schema. After any change to a Pydantic DTO:

```bash
# Terminal A
cd backend && uvicorn kodoku.main:app --port 8000

# Terminal B
cd frontend && npm run gen:contracts
git add lib/types/contracts.ts && git commit -m "chore: regenerate frontend contracts"
```

CI will enforce this in M6.
```

- [ ] **Step 8: Commit**

```bash
git add frontend/scripts/gen-contracts.mjs frontend/package.json frontend/package-lock.json frontend/lib/types/contracts.ts frontend/lib/types/api.ts README.md
git commit -m "feat(frontend): generate contracts.ts from backend OpenAPI schema"
```

---

## Task 8: shadcn/ui install + base components

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/app/globals.css`
- Create: `frontend/components.json`
- Create: `frontend/lib/utils.ts`
- Create: `frontend/components/ui/button.tsx`
- Create: `frontend/components/ui/dialog.tsx`
- Create: `frontend/components/ui/input.tsx`
- Create: `frontend/components/ui/label.tsx`
- Create: `frontend/components/ui/select.tsx`
- Create: `frontend/components/ui/textarea.tsx`

> shadcn vendors components rather than installing them as a package. We pin specific versions of the Radix primitives and helpers it depends on, then hand-vendor the six components we need so the diff is reviewable and the plan is deterministic.

- [ ] **Step 1: Install shadcn-adjacent dependencies**

Run (from `frontend/`):
```bash
npm install \
  class-variance-authority@0.7.1 \
  clsx@2.1.1 \
  tailwind-merge@2.5.5 \
  lucide-react@0.469.0 \
  @radix-ui/react-dialog@1.1.4 \
  @radix-ui/react-label@2.1.1 \
  @radix-ui/react-select@2.1.4 \
  @radix-ui/react-slot@1.1.1
npm install --save-dev tailwindcss-animate@1.0.7
```
Expected: lockfile updated, no errors.

- [ ] **Step 2: Create `components.json`**

Path: `frontend/components.json`

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "app/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 3: Add the `cn` helper**

Path: `frontend/lib/utils.ts`

```typescript
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 4: Replace `tailwind.config.ts` with shadcn-aware config**

Path: `frontend/tailwind.config.ts`

```typescript
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [animate],
};

export default config;
```

- [ ] **Step 5: Replace `app/globals.css` with shadcn variables**

Path: `frontend/app/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 0 0% 9%;
    --card: 0 0% 100%;
    --card-foreground: 0 0% 9%;
    --popover: 0 0% 100%;
    --popover-foreground: 0 0% 9%;
    --primary: 0 0% 9%;
    --primary-foreground: 0 0% 98%;
    --secondary: 0 0% 96%;
    --secondary-foreground: 0 0% 9%;
    --muted: 0 0% 96%;
    --muted-foreground: 0 0% 45%;
    --accent: 0 0% 96%;
    --accent-foreground: 0 0% 9%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 90%;
    --input: 0 0% 90%;
    --ring: 0 0% 9%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 0 0% 4%;
    --foreground: 0 0% 98%;
    --card: 0 0% 4%;
    --card-foreground: 0 0% 98%;
    --popover: 0 0% 4%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 0 0% 9%;
    --secondary: 0 0% 15%;
    --secondary-foreground: 0 0% 98%;
    --muted: 0 0% 15%;
    --muted-foreground: 0 0% 65%;
    --accent: 0 0% 15%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 63% 31%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 15%;
    --input: 0 0% 15%;
    --ring: 0 0% 83%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground antialiased;
  }
}
```

- [ ] **Step 6: Vendor `Button`**

Path: `frontend/components/ui/button.tsx`

```typescript
"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

- [ ] **Step 7: Vendor `Dialog`**

Path: `frontend/components/ui/dialog.tsx`

```typescript
"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className,
    )}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 sm:rounded-lg",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = DialogPrimitive.Content.displayName;

const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)}
    {...props}
  />
);
DialogHeader.displayName = "DialogHeader";

const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className,
    )}
    {...props}
  />
);
DialogFooter.displayName = "DialogFooter";

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
};
```

- [ ] **Step 8: Vendor `Input`**

Path: `frontend/components/ui/input.tsx`

```typescript
import * as React from "react";

import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
```

- [ ] **Step 9: Vendor `Label`**

Path: `frontend/components/ui/label.tsx`

```typescript
"use client";

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
);

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> &
    VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants(), className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
```

- [ ] **Step 10: Vendor `Select`**

Path: `frontend/components/ui/select.tsx`

```typescript
"use client";

import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";

const Select = SelectPrimitive.Root;
const SelectGroup = SelectPrimitive.Group;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1",
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectScrollUpButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollUpButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollUpButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1", className)}
    {...props}
  >
    <ChevronUp className="h-4 w-4" />
  </SelectPrimitive.ScrollUpButton>
));
SelectScrollUpButton.displayName = SelectPrimitive.ScrollUpButton.displayName;

const SelectScrollDownButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollDownButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollDownButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1", className)}
    {...props}
  >
    <ChevronDown className="h-4 w-4" />
  </SelectPrimitive.ScrollDownButton>
));
SelectScrollDownButton.displayName = SelectPrimitive.ScrollDownButton.displayName;

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      className={cn(
        "relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        position === "popper" &&
          "data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1",
        className,
      )}
      position={position}
      {...props}
    >
      <SelectScrollUpButton />
      <SelectPrimitive.Viewport
        className={cn(
          "p-1",
          position === "popper" &&
            "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]",
        )}
      >
        {children}
      </SelectPrimitive.Viewport>
      <SelectScrollDownButton />
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectLabel = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Label
    ref={ref}
    className={cn("py-1.5 pl-8 pr-2 text-sm font-semibold", className)}
    {...props}
  />
));
SelectLabel.displayName = SelectPrimitive.Label.displayName;

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

const SelectSeparator = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Separator
    ref={ref}
    className={cn("-mx-1 my-1 h-px bg-muted", className)}
    {...props}
  />
));
SelectSeparator.displayName = SelectPrimitive.Separator.displayName;

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
};
```

- [ ] **Step 11: Vendor `Textarea`**

Path: `frontend/components/ui/textarea.tsx`

```typescript
import * as React from "react";

import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export { Textarea };
```

- [ ] **Step 12: Typecheck and lint**

Run (from `frontend/`):
```bash
npm run typecheck
npm run lint
```
Expected: both clean. (lint may flag unused exports in `select.tsx`; if so, disable the rule for that file's exports or accept the warnings — these are the canonical shadcn shapes and downstream tasks consume them.)

- [ ] **Step 13: Visual smoke**

```bash
npm run dev
```
Open `http://localhost:3000`. The healthz card should still render but now using shadcn-themed neutrals (border slightly different colour). Stop dev server.

- [ ] **Step 14: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/components.json frontend/lib/utils.ts frontend/tailwind.config.ts frontend/app/globals.css frontend/components/ui/
git commit -m "feat(frontend): install shadcn/ui primitives (button, dialog, input, label, select, textarea)"
```

---

## Task 9: Extend the typed API client

**Files:**
- Modify: `frontend/lib/api/client.ts`

- [ ] **Step 1: Replace `client.ts` with the full session-aware client**

Path: `frontend/lib/api/client.ts`

```typescript
import type {
  HealthResponse,
  SessionCreate,
  SessionCreateResponse,
  SessionDetailResponse,
  SessionListItem,
  SessionResponse,
  SessionUpdate,
} from "@/lib/types/api";

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

type RequestOptions = RequestInit & { expectEmpty?: boolean };

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { expectEmpty, ...rest } = init ?? {};
  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(rest.headers ?? {}),
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

  return (expectEmpty ? undefined : body) as T;
}

export const api = {
  healthz: () => request<HealthResponse>("/healthz"),

  listSessions: () => request<SessionListItem[]>("/sessions"),

  getSession: (id: string) =>
    request<SessionDetailResponse>(`/sessions/${id}`),

  createSession: (body: SessionCreate) =>
    request<SessionCreateResponse>("/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  patchSession: (id: string, body: SessionUpdate) =>
    request<SessionResponse>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteSession: (id: string) =>
    request<void>(`/sessions/${id}`, {
      method: "DELETE",
      expectEmpty: true,
    }),
};
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: clean. (Note: `app/page.tsx` still imports `HealthResponse` from `@/lib/types/contracts` — the old hand-written placeholder. The next task replaces that page entirely, so we accept the transient mismatch for one step. If TS complains about the old import path during this step, update only the import line in `app/page.tsx` to `from "@/lib/types/api"`.)

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/client.ts
git commit -m "feat(frontend): extend typed API client with session CRUD methods"
```

---

## Task 10: Zustand store + sidebar list page

**Files:**
- Create: `frontend/state/sessionStore.ts`
- Create: `frontend/app/_components/SessionSidebar.tsx`
- Modify: `frontend/app/page.tsx` — replace healthz page with sidebar + main pane shell

- [ ] **Step 1: Add the Zustand store**

Path: `frontend/state/sessionStore.ts`

```typescript
"use client";

import { create } from "zustand";

type SessionStore = {
  /** Counter that components mutate to trigger a re-fetch of the session list. */
  sidebarRefreshTick: number;
  refreshSidebar: () => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
  sidebarRefreshTick: 0,
  refreshSidebar: () =>
    set((state) => ({ sidebarRefreshTick: state.sidebarRefreshTick + 1 })),
}));
```

- [ ] **Step 2: Add the sidebar component**

Path: `frontend/app/_components/SessionSidebar.tsx`

```typescript
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api/client";
import { useSessionStore } from "@/state/sessionStore";
import type { SessionListItem } from "@/lib/types/api";
import { cn } from "@/lib/utils";

type Props = {
  activeSessionId?: string;
};

export function SessionSidebar({ activeSessionId }: Props) {
  const [sessions, setSessions] = useState<SessionListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tick = useSessionStore((s) => s.sidebarRefreshTick);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .listSessions()
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? `${err.status} ${err.message}`
            : err instanceof Error
              ? err.message
              : "unknown error";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-border bg-card">
      <div className="px-4 py-5">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Kodoku
        </Link>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Decision Graph AI
        </p>
      </div>
      <div className="px-4 pb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Sessions
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {sessions === null && !error ? (
          <p className="px-2 text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="px-2 text-sm text-destructive">Backend unreachable: {error}</p>
        ) : sessions.length === 0 ? (
          <p className="px-2 text-sm text-muted-foreground">
            No sessions yet. Click "New session" to start.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {sessions.map((row) => (
              <li key={row.id}>
                <Link
                  href={`/s/${row.id}`}
                  className={cn(
                    "block rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                    row.id === activeSessionId && "bg-accent font-medium",
                  )}
                >
                  <span className="block truncate">{row.title}</span>
                  <span className="block text-[10px] uppercase tracking-wide text-muted-foreground">
                    {row.status}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 3: Replace `app/page.tsx`**

Path: `frontend/app/page.tsx`

```typescript
import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { NewSessionDialog } from "@/app/_components/NewSessionDialog";

export default function HomePage() {
  return (
    <div className="flex h-screen">
      <SessionSidebar />
      <main className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Sessions</h1>
            <p className="text-xs text-muted-foreground">
              Pick a session from the sidebar or start a new one.
            </p>
          </div>
          <NewSessionDialog />
        </header>
        <section className="flex flex-1 items-center justify-center">
          <div className="max-w-md text-center text-sm text-muted-foreground">
            Each session expands a goal into branches, scores them, and
            synthesises a recommendation. Click "New session" to seed the root
            node.
          </div>
        </section>
      </main>
    </div>
  );
}
```

> Note: `NewSessionDialog` is defined in Task 11. Typecheck will fail at this step until Task 11 is complete — that is intentional and the two tasks are committed in sequence.

- [ ] **Step 4: Commit**

(Skip typecheck for this single commit since the dialog import is pending. Both tasks are reviewed together.)

```bash
git add frontend/state/sessionStore.ts frontend/app/_components/SessionSidebar.tsx frontend/app/page.tsx
git commit -m "feat(frontend): add session sidebar list and store"
```

---

## Task 11: New-session modal

**Files:**
- Create: `frontend/app/_components/NewSessionDialog.tsx`

- [ ] **Step 1: Implement the dialog**

Path: `frontend/app/_components/NewSessionDialog.tsx`

```typescript
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api/client";
import { useSessionStore } from "@/state/sessionStore";

const MODEL_PRESETS = [
  { value: "anthropic/claude-sonnet-4-6", label: "Claude Sonnet 4.6 (recommended)" },
  { value: "openai/gpt-4o-mini", label: "OpenAI GPT-4o mini" },
  { value: "openrouter/anthropic/claude-3.5-sonnet", label: "OpenRouter Claude 3.5 Sonnet" },
  { value: "ollama/llama3.1", label: "Ollama (local dev)" },
];

export function NewSessionDialog() {
  const router = useRouter();
  const refreshSidebar = useSessionStore((s) => s.refreshSidebar);

  const [open, setOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [title, setTitle] = useState("");
  const [model, setModel] = useState(MODEL_PRESETS[0].value);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setGoal("");
    setTitle("");
    setModel(MODEL_PRESETS[0].value);
    setError(null);
    setSubmitting(false);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { session_id } = await api.createSession({
        goal,
        title: title.trim() ? title.trim() : null,
        config: { model, branching_factor: 3, max_depth: 3, temperature: 0.7 },
      });
      refreshSidebar();
      setOpen(false);
      reset();
      router.push(`/s/${session_id}`);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.status} ${err.message}`
          : err instanceof Error
            ? err.message
            : "unknown error";
      setError(message);
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button>New session</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New session</DialogTitle>
            <DialogDescription>
              Describe the goal you want to explore. Kodoku will seed the root
              node from it; the engine will branch into candidates once you
              click "Run" on the session page.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="goal">Goal</Label>
            <Textarea
              id="goal"
              required
              minLength={10}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. Brainstorm side-project ideas combining AI and music."
              rows={4}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="title">Title (optional)</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Auto-derived from goal if blank"
              maxLength={200}
            />
          </div>

          <div className="space-y-2">
            <Label>Model</Label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_PRESETS.map((preset) => (
                  <SelectItem key={preset.value} value={preset.value}>
                    {preset.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || goal.length < 10}>
              {submitting ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/_components/NewSessionDialog.tsx
git commit -m "feat(frontend): add new-session modal with goal + model preset"
```

---

## Task 12: Session detail shell `/s/[sessionId]`

**Files:**
- Create: `frontend/app/s/[sessionId]/page.tsx`

- [ ] **Step 1: Implement the page**

Path: `frontend/app/s/[sessionId]/page.tsx`

```typescript
import { notFound } from "next/navigation";

import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { ApiError, api } from "@/lib/api/client";
import type { SessionDetailResponse } from "@/lib/types/api";

async function loadSession(id: string): Promise<SessionDetailResponse | null> {
  try {
    return await api.getSession(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

type Props = { params: { sessionId: string } };

export default async function SessionPage({ params }: Props) {
  const session = await loadSession(params.sessionId);
  if (!session) notFound();

  const root = session.nodes.find((n) => n.kind === "root");

  return (
    <div className="flex h-screen">
      <SessionSidebar activeSessionId={session.id} />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">{session.title}</h1>
          <p className="text-xs text-muted-foreground">
            Status: {session.status} · Created{" "}
            {new Date(session.created_at).toLocaleString()}
          </p>
        </header>
        <section className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-2xl space-y-6">
            <article className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Goal
              </h2>
              <p className="mt-2 whitespace-pre-wrap text-sm">{session.goal}</p>
            </article>

            {root && (
              <article className="rounded-lg border border-border bg-card p-4">
                <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Root node
                </h2>
                <p className="mt-1 text-sm font-medium">{root.title}</p>
                <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
                  {root.content}
                </p>
              </article>
            )}

            <p className="text-xs text-muted-foreground">
              Graph rendering lands in M3. Engine + Run controls land in M4.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: End-to-end smoke**

Run in three shells:
- `docker compose up -d` (root)
- `uvicorn kodoku.main:app --port 8000` (from `backend/`, venv active)
- `npm run dev` (from `frontend/`)

In a browser:
1. Open `http://localhost:3000`. Sidebar shows "No sessions yet."
2. Click "New session". Paste a goal of 30+ characters. Pick a model. Submit.
3. Confirm redirect to `/s/<uuid>`. Goal text and root node visible.
4. Click "Kodoku" link to return home. Sidebar now shows the session.
5. Refresh `http://localhost:3000`. Session persists.
6. Click the session in the sidebar → returns to detail page.
7. Open dev tools → Network → confirm `/sessions`, `/sessions` POST, `/sessions/{id}` GET requests succeed with 201/200.

Stop the frontend and backend dev servers; leave Postgres running.

- [ ] **Step 3: Typecheck + lint**

Run (from `frontend/`):
```bash
npm run typecheck
npm run lint
```
Expected: both clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/s/[sessionId]/page.tsx
git commit -m "feat(frontend): add session detail shell with goal + root node"
```

---

## Task 13: M2 acceptance gate

This task contains no new code. It runs the full M2 acceptance gate. If any step fails, fix it (or open a follow-up task) before declaring M2 done.

- [ ] **Step 1: Working tree clean**

Run: `git status`
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 2: Backend test sweep**

Run (from `backend/`, venv active): `pytest -v`
Expected: all of `test_settings`, `test_health`, `test_db_engine`, `test_enums`, `test_dtos`, `test_models`, `test_repo_sessions`, `test_sessions_api` pass.

- [ ] **Step 3: Backend lint + typecheck**

Run (from `backend/`): `ruff check . && mypy kodoku`
Expected: no warnings or errors.

- [ ] **Step 4: Frontend lint + typecheck**

Run (from `frontend/`): `npm run typecheck && npm run lint`
Expected: no errors.

- [ ] **Step 5: Migrations round-trip**

Run (from `backend/`):
```bash
alembic downgrade base
alembic upgrade head
```
Expected: both succeed. `\dt` in psql shows the five tables.

- [ ] **Step 6: Contracts file is in sync**

Start backend:
```bash
uvicorn kodoku.main:app --port 8000
```
From `frontend/`:
```bash
npm run gen:contracts
git diff --exit-code lib/types/contracts.ts
```
Expected: exit code 0 (no diff). If there's a diff, the file is stale — investigate which DTO change wasn't followed by a regen.

Stop uvicorn.

- [ ] **Step 7: Full-stack smoke**

Run in parallel shells:
- `docker compose up -d`
- `uvicorn kodoku.main:app --port 8000`
- `npm run dev`

Manually verify the flow from Task 12 Step 2 end-to-end against a fresh DB (clean by running `alembic downgrade base && alembic upgrade head` once before the smoke).

- [ ] **Step 8: Tag the milestone**

```bash
git tag -a m2-domain-crud -m "M2 — domain model + REST CRUD complete"
```

- [ ] **Step 9: Update architecture doc status**

Modify: `docs/architecture.md` — change the M2 line to:

```
- M2 — Domain model + REST CRUD: ✅ complete
```

Commit:
```bash
git add docs/architecture.md
git commit -m "docs: mark M2 milestone complete"
```

---

## Done with M2

Next: write the **M3 — React Flow graph + WebSocket plumbing** plan against the same spec, against a fresh `m2-domain-crud` tag baseline. The spec already locks the WS event taxonomy, the events table, and the reconnect/replay contract; M3's plan will TDD the WS manager, events repo + `/events?since=` endpoint, debug-event emitter, Zustand reducer per event type, React Flow canvas with `dagre`, and the custom `NodeCard` variants.
