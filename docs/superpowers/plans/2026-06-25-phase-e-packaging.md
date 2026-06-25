# Phase E — Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Kodoku a downloadable, single-command local app: one process serves the API, WebSockets, and the prebuilt UI on one port, backed by a SQLite file it creates itself — distributed via `pipx` (primary) and a thin Docker image (secondary), with the existing two-process dev flow untouched.

**Architecture:** Build the Next.js frontend to a static export (`out/`) at *packaging time*. FastAPI mounts that `out/` and serves it; any `/s/<id>` request returns the single client-rendered session shell. On startup the app creates the SQLite schema via `Base.metadata.create_all` (Postgres path keeps Alembic). A `kodoku` console-script starts uvicorn and opens the browser. One runtime shape, multiple distribution wrappers.

**Tech Stack:** FastAPI + Starlette `StaticFiles`, SQLAlchemy 2 async, hatchling, Next.js 14 static export, pipx, Docker (multi-stage).

## Global Constraints

- Python `>=3.12`; pinned dep versions in `backend/pyproject.toml` — do **not** bump existing pins.
- **No new runtime Python dependency** for this phase (use stdlib `webbrowser`, `pathlib`, `threading`; `uvicorn` is already a dep).
- Local-first default `DATABASE_URL = sqlite+aiosqlite:///./kodoku.db` must keep working with **zero** manual DB setup.
- A `postgresql+asyncpg://` URL must still work and must **not** trigger `create_all` (that path keeps Alembic).
- The existing dev flow (separate `uvicorn` + `next dev`) must remain functional — when no built `out/` is present, the backend runs API-only and mounts nothing.
- Frontend is a client-side SPA (all data via `fetch`/WS using `NEXT_PUBLIC_API_BASE_URL`); keep it that way.
- Match existing style; surgical changes only.

---

### Task 1: Create the SQLite schema on startup

**Files:**
- Create: `backend/kodoku/db/bootstrap.py`
- Modify: `backend/kodoku/main.py` (add a lifespan that calls bootstrap)
- Test: `backend/tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `kodoku.db.base.Base`, `kodoku.db.models` (registers mappers), `sqlalchemy.ext.asyncio.AsyncEngine`.
- Produces: `async def ensure_schema(engine: AsyncEngine) -> bool` — runs `Base.metadata.create_all` (checkfirst) **only when `engine.dialect.name == "sqlite"`**; returns `True` if it ran, `False` if skipped (non-sqlite). Idempotent.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bootstrap.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_bootstrap.py -v`
Expected: FAIL — `ModuleNotFoundError: kodoku.db.bootstrap`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/kodoku/db/bootstrap.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_bootstrap.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire it into app startup via lifespan**

Modify `backend/kodoku/main.py` — add a lifespan that bootstraps the schema, and pass it to `FastAPI(...)`. Add imports at top and the lifespan function above `create_app`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from kodoku.db.bootstrap import ensure_schema
from kodoku.db.engine import get_engine
```

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await ensure_schema(get_engine())
    yield
```

Then change the `app = FastAPI(...)` constructor call inside `create_app` to include `lifespan=lifespan`:

```python
    app = FastAPI(
        title="Kodoku",
        version=__version__,
        description="Decision Graph AI — Tree of Thoughts planner",
        lifespan=lifespan,
    )
```

- [ ] **Step 6: Verify the full suite still passes**

Run: `cd backend && pytest -q`
Expected: PASS — existing count + 2 new tests, no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/kodoku/db/bootstrap.py backend/kodoku/main.py backend/tests/test_bootstrap.py
git commit -m "feat(db): create SQLite schema on startup (local-first bootstrap)"
```

---

### Task 2: Serve the prebuilt frontend from FastAPI

**Files:**
- Create: `backend/kodoku/web.py`
- Modify: `backend/kodoku/main.py` (mount static + session-shell route after routers)
- Test: `backend/tests/test_web_serving.py`

**Interfaces:**
- Consumes: built frontend dir (`kodoku/_web` when packaged, else `<repo>/frontend/out` in dev). Session shell lives at `<web>/s/_/index.html` (Next emits this from Task 3's `generateStaticParams([{sessionId:"_"}])` with `trailingSlash: true`).
- Produces:
  - `def web_dir() -> Path | None` — bundled `Path(__file__).parent / "_web"`, else dev `Path(__file__).parents[2] / "frontend" / "out"`, else `None`.
  - `def mount_web(app: FastAPI) -> bool` — if `web_dir()` exists: registers `GET /s/{session_id}` returning the session shell, then mounts `StaticFiles(directory=web_dir(), html=True)` at `/`; returns `True`. If no web dir: returns `False` (API-only). Must be called **after** all API/WS routers so they take precedence.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_web_serving.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kodoku.web import mount_web


def _make_web(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    (out / "s" / "_").mkdir(parents=True)
    (out / "index.html").write_text("<html>home</html>", encoding="utf-8")
    (out / "s" / "_" / "index.html").write_text("<html>session-shell</html>", encoding="utf-8")
    return out


def test_mount_web_serves_index_and_session_shell(tmp_path: Path, monkeypatch) -> None:
    out = _make_web(tmp_path)
    monkeypatch.setattr("kodoku.web.web_dir", lambda: out)

    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    assert mount_web(app) is True
    client = TestClient(app)

    # API route still wins over the static mount
    assert client.get("/healthz").json() == {"status": "ok"}
    # root serves index.html
    assert "home" in client.get("/").text
    # any /s/<id> serves the single client shell
    assert "session-shell" in client.get("/s/abc-123").text


def test_mount_web_noop_without_build(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("kodoku.web.web_dir", lambda: None)
    app = FastAPI()
    assert mount_web(app) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_web_serving.py -v`
Expected: FAIL — `ModuleNotFoundError: kodoku.web`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/kodoku/web.py
"""Serve the prebuilt Next.js static export from FastAPI (packaged single-port mode).

In dev (no build present) this is a no-op and the app is API-only; run `next dev`
separately. When packaged, the build is bundled at `kodoku/_web`.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def web_dir() -> Path | None:
    bundled = Path(__file__).parent / "_web"
    if bundled.is_dir():
        return bundled
    dev = Path(__file__).parents[2] / "frontend" / "out"
    if dev.is_dir():
        return dev
    return None


def mount_web(app: FastAPI) -> bool:
    root = web_dir()
    if root is None:
        return False

    shell = root / "s" / "_" / "index.html"

    @app.get("/s/{session_id}", include_in_schema=False)
    async def session_shell(session_id: str) -> FileResponse:
        return FileResponse(shell)

    # html=True serves index.html for "/" and directory paths (e.g. /settings).
    app.mount("/", StaticFiles(directory=root, html=True), name="web")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_web_serving.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Call `mount_web` last in `create_app`**

Modify `backend/kodoku/main.py` — add `from kodoku.web import mount_web` to imports, and as the **last** statement before `return app` in `create_app` (after every `include_router`):

```python
    mount_web(app)

    return app
```

- [ ] **Step 6: Verify the full suite still passes**

Run: `cd backend && pytest -q`
Expected: PASS, no regressions. (No `frontend/out` exists in the test env, so `mount_web` is a no-op and existing routes are unaffected.)

- [ ] **Step 7: Commit**

```bash
git add backend/kodoku/web.py backend/kodoku/main.py backend/tests/test_web_serving.py
git commit -m "feat(web): serve prebuilt frontend + SPA session route from FastAPI"
```

---

### Task 3: Static-export the frontend; client-render the session route

**Files:**
- Modify: `frontend/next.config.mjs`
- Modify: `frontend/app/s/[sessionId]/page.tsx` (thin server shell: `generateStaticParams` + render client child)
- Create: `frontend/app/s/[sessionId]/SessionPageClient.tsx` (runtime fetch, client-rendered)

**Interfaces:**
- Consumes: `api.getSession`, `ApiError` from `@/lib/api/client`; `SessionGraphView` (already `"use client"`, takes `sessionId/initialStatus/initialSynthesis/initialNodes/initialEvaluations`); `SessionSidebar`.
- Produces: a static export in `frontend/out/` containing `out/index.html`, `out/settings/index.html`, and `out/s/_/index.html` (the param-independent session shell consumed by Task 2). `generateStaticParams` returns `[{ sessionId: "_" }]`, `dynamicParams = false`.

- [ ] **Step 1: Enable static export**

Replace `frontend/next.config.mjs` with:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
```

- [ ] **Step 2: Create the client session page**

Create `frontend/app/s/[sessionId]/SessionPageClient.tsx`. This moves the old server-side fetch into the browser (the rest of the app already fetches client-side):

```tsx
"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { SessionGraphView } from "@/app/s/[sessionId]/SessionGraphView";
import { ApiError, api } from "@/lib/api/client";
import type { SessionDetailResponse } from "@/lib/types/api";

type Load =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "ready"; session: SessionDetailResponse };

export function SessionPageClient() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    let active = true;
    api
      .getSession(sessionId)
      .then((session) => active && setLoad({ state: "ready", session }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          if (active) setLoad({ state: "missing" });
          return;
        }
        throw err;
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  if (load.state === "loading") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Loading session…
      </div>
    );
  }
  if (load.state === "missing") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Session not found.
      </div>
    );
  }

  const { session } = load;
  return (
    <div className="flex h-screen">
      <SessionSidebar activeSessionId={session.id} />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">{session.title}</h1>
          <p className="text-xs text-muted-foreground">{session.goal}</p>
        </header>
        <section className="flex-1 overflow-hidden">
          <SessionGraphView
            sessionId={session.id}
            initialStatus={session.status}
            initialSynthesis={session.final_synthesis}
            initialNodes={session.nodes}
            initialEvaluations={session.evaluations}
          />
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Replace the server page with a static shell**

Replace `frontend/app/s/[sessionId]/page.tsx` entirely with:

```tsx
import { SessionPageClient } from "@/app/s/[sessionId]/SessionPageClient";

// Static export needs at least one param; the page is client-rendered and
// param-independent, so one shell ("_") is served by the backend for every id.
export const dynamicParams = false;

export function generateStaticParams() {
  return [{ sessionId: "_" }];
}

export default function SessionPage() {
  return <SessionPageClient />;
}
```

- [ ] **Step 4: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors. (`notFound`/`SessionDetailResponse` import in the old page is gone; the new client component imports what it uses.)

- [ ] **Step 5: Build the static export and verify the shells exist**

Run: `cd frontend && npm run build`
Expected: build succeeds; verify these files now exist:
- `frontend/out/index.html`
- `frontend/out/settings/index.html`
- `frontend/out/s/_/index.html`

Run: `ls frontend/out/s/_/index.html frontend/out/index.html`
Expected: both paths listed (no error).

- [ ] **Step 6: Smoke the single-port serving end to end**

With the build present, the dev backend now serves the UI (Task 2's `web_dir()` finds `frontend/out`). Start the backend and curl it:

Run: `cd backend && (uvicorn kodoku.main:app --port 8123 &) ; sleep 3 ; curl -s localhost:8123/ | head -c 200 ; echo ; curl -s localhost:8123/s/anything | head -c 200 ; kill %1 2>/dev/null`
Expected: both responses return HTML (the Next shell markup), not a JSON 404.

> Note (Windows/agent env): if the background uvicorn pattern doesn't hold, run `uvicorn kodoku.main:app --port 8123` in one shell and `curl` in another, or rely on Task 2's HTTP tests as the automated check and have the user click through once.

- [ ] **Step 7: Commit**

```bash
git add frontend/next.config.mjs "frontend/app/s/[sessionId]/page.tsx" "frontend/app/s/[sessionId]/SessionPageClient.tsx"
git commit -m "feat(frontend): static export + client-rendered session route"
```

> Do **not** commit `frontend/out/` — it is a build artifact (ensure it is gitignored; add `frontend/out/` to `.gitignore` if missing, in this commit).

---

### Task 4: `kodoku` console-script launcher

**Files:**
- Create: `backend/kodoku/cli.py`
- Modify: `backend/pyproject.toml` (`[project.scripts]` + bundle `_web` into the wheel)
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: `uvicorn` (already a dependency), stdlib `webbrowser`, `threading`, `argparse`.
- Produces: `def main(argv: list[str] | None = None) -> None` — parses `--host` (default `127.0.0.1`), `--port` (default `8000`), `--no-browser`; schedules a browser open (unless `--no-browser`) then runs `uvicorn.run("kodoku.main:app", host=host, port=port)`. Exposed as console script `kodoku`.

- [ ] **Step 1: Write the failing test**

Test the arg parsing and that a browser open is scheduled, without actually starting a server (patch `uvicorn.run` and `webbrowser.open`).

```python
# backend/tests/test_cli.py
from __future__ import annotations

import kodoku.cli as cli


def test_main_runs_uvicorn_with_defaults(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    monkeypatch.setattr(cli, "_open_browser_when_ready", lambda host, port: calls.update(opened=(host, port)))

    cli.main(["--port", "9001", "--no-browser"])

    assert calls["app"] == "kodoku.main:app"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9001
    assert "opened" not in calls  # --no-browser suppresses it


def test_main_schedules_browser_by_default(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: None)
    monkeypatch.setattr(cli, "_open_browser_when_ready", lambda host, port: calls.update(opened=(host, port)))

    cli.main(["--port", "9002"])

    assert calls["opened"] == ("127.0.0.1", 9002)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: kodoku.cli`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/kodoku/cli.py
"""`kodoku` console entry point: start the server and open the browser."""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def _open_browser_when_ready(host: str, port: int) -> None:
    # ponytail: fixed 1.5s delay instead of polling the port; good enough for a
    # local launch. Switch to a readiness poll if startup ever gets slow.
    url = f"http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}/"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kodoku", description="Run Kodoku locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser")
    args = parser.parse_args(argv)

    if not args.no_browser:
        _open_browser_when_ready(args.host, args.port)
    uvicorn.run("kodoku.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Register the console script and bundle the web build**

Modify `backend/pyproject.toml`. Add after the `[project]` block (top-level table):

```toml
[project.scripts]
kodoku = "kodoku.cli:main"
```

And extend the wheel build to include the bundled UI when present (placed at `kodoku/_web` by the packaging step / Dockerfile). Under `[tool.hatch.build.targets.wheel]`, the package list stays `["kodoku"]`; add an artifacts include so `_web` (gitignored) is packed if it exists:

```toml
[tool.hatch.build.targets.wheel]
packages = ["kodoku"]
artifacts = ["kodoku/_web/**"]
```

- [ ] **Step 6: Verify install + entry point resolves**

Run: `cd backend && pip install -e . && kodoku --help`
Expected: argparse help text prints with `--host`, `--port`, `--no-browser`; exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/kodoku/cli.py backend/pyproject.toml backend/tests/test_cli.py
git commit -m "feat(cli): kodoku console-script launcher + bundle web build in wheel"
```

---

### Task 5: Docker on-ramp + user-facing docs

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)
- Modify: `README.md` (add an "Install & run" section for end users)

**Interfaces:**
- Consumes: Task 3's `frontend` build, Task 4's `kodoku` entry point and `kodoku/_web` bundling location.
- Produces: a runnable image whose `CMD` is `kodoku --host 0.0.0.0 --no-browser`, serving everything on port 8000; documented `pipx` and `docker` install flows.

- [ ] **Step 1: Write the Dockerfile (multi-stage: build UI → install backend)**

Create `Dockerfile`:

```dockerfile
# Stage 1 — build the static UI
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # -> /web/out

# Stage 2 — Python app serving API + UI on one port
FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./
# bundle the prebuilt UI where web_dir() looks first
COPY --from=web /web/out ./kodoku/_web
RUN pip install --no-cache-dir .
ENV DATABASE_URL=sqlite+aiosqlite:////data/kodoku.db
VOLUME /data
EXPOSE 8000
CMD ["kodoku", "--host", "0.0.0.0", "--no-browser"]
```

- [ ] **Step 2: Add `.dockerignore`**

Create `.dockerignore`:

```
**/node_modules
**/.venv
**/__pycache__
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
frontend/out
frontend/.next
.git
```

- [ ] **Step 3: Build the image**

Run: `docker build -t kodoku .`
Expected: build succeeds through both stages; final image tagged `kodoku`.

> If Docker is unavailable in this environment, skip the live build and have the user run it; the Dockerfile is reviewed for correctness against Task 3/4 paths (`/web/out` → `kodoku/_web`, `kodoku` entry point exists).

- [ ] **Step 4: Smoke-run the container**

Run: `docker run --rm -p 8000:8000 -v kodoku-data:/data kodoku &` then `sleep 5 ; curl -s localhost:8000/healthz ; echo ; curl -s localhost:8000/ | head -c 120`
Expected: `/healthz` returns `{"status":"ok",...}` and `/` returns HTML. Stop with `docker stop` of the run.

- [ ] **Step 5: Update the README**

In `README.md`, add a section near the top (after the intro, before "Stack") titled `## Install & run (local app)` documenting both on-ramps. Keep the existing dev quickstart as the contributor flow. Content:

````markdown
## Install & run (local app)

Kodoku runs entirely on your machine: one process serves the UI and API, and it
stores everything in a `kodoku.db` SQLite file. Bring your own model key via the
in-app `/settings` page.

**With pipx (needs Python 3.12+):**

```bash
# build the UI once, bundle it into the package, then install
cd frontend && npm ci && npm run build && cd ..
cp -r frontend/out backend/kodoku/_web
pipx install ./backend
kodoku            # starts the server and opens http://localhost:8000
```

**With Docker (no Python/Node needed):**

```bash
docker build -t kodoku .
docker run --rm -p 8000:8000 -v kodoku-data:/data kodoku
# open http://localhost:8000
```

Both serve on one port; there is no separate frontend process. The two-process
`next dev` + `uvicorn` flow below is only for development.
````

> Windows note for the pipx copy step: `xcopy /E /I frontend\out backend\kodoku\_web` (or `Copy-Item -Recurse`). Document the bash form; mention the Windows equivalent in one line.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore README.md
git commit -m "feat(packaging): Docker image + install/run docs (pipx + docker)"
```

---

## Self-Review

**Spec coverage** (against the Phase E goal + the two memory blockers):
- *SQLite app can build its DB* (memory blocker: Alembic is Postgres-only) → Task 1 (`create_all` gated to SQLite; Postgres keeps Alembic).
- *One-command local run, no Node at runtime* → Task 2 (FastAPI serves prebuilt UI) + Task 3 (static export) + Task 4 (`kodoku` launcher).
- *Multiple on-ramps, one runtime shape* → Task 4 (pipx) + Task 5 (Docker); dev flow preserved by `mount_web` no-op when no build present.
- *Dynamic `/s/[id]` route under static export* → Task 3 (`generateStaticParams` shell + `dynamicParams=false`) consumed by Task 2's `/s/{id}` route.

**Placeholder scan:** none — every code/test step carries full content.

**Type/name consistency:** `ensure_schema` (T1) ←→ used in T1 lifespan. `web_dir`/`mount_web` (T2) ←→ patched in T2 tests, Dockerfile copies to `kodoku/_web` (T5) matching `web_dir()`'s bundled path (T2). `generateStaticParams([{sessionId:"_"}])` + `trailingSlash:true` (T3) → `out/s/_/index.html` ←→ `shell = root/"s"/"_"/"index.html"` (T2). `kodoku.cli:main` (T4) ←→ `[project.scripts]` (T4) ←→ Docker `CMD ["kodoku", ...]` (T5).

**Known follow-ups (non-blocking, do not fix here unless trivial):**
- The pipx flow has a manual `cp frontend/out → backend/kodoku/_web` step. Acceptable for a developer-packaged release; a `scripts/package.py` could automate it later (YAGNI now).
- Alembic migrations remain Postgres-only by design (the SQLite path no longer needs them). The `kodoku-known-followups` "Alembic migration is Postgres-only" item is resolved *for SQLite* by Task 1 — update that memo on merge.
