# Kodoku — Decision Graph AI

> A decision engine, not a chatbot. Give it a goal; it expands a **tree of
> ideas**, scores and critiques each branch, prunes the weak ones, and
> synthesizes a recommendation — with you in the loop at every branch.

Kodoku turns one goal into a visible graph of explored options. Each node is an
idea; the engine branches it into candidates, an LLM evaluates and critiques
them, a decision step keeps the strong branches and prunes the rest, and a final
step writes up the recommendation. You can let it run on autopilot or pause to
approve, edit, or override at each branch.

It runs **entirely on your machine**: one local process, your own model key, a
single SQLite file. No account, no server, no data leaves your computer except
the model calls you configure.

## What you get

- **Tree-of-Thoughts engine** — expand → evaluate → decide → synthesize, as a
  live graph you watch update over WebSocket.
- **Human-in-the-loop** — *autopilot* (run start to finish) or *review each
  branch* (pause for your keep/prune/edit at every checkpoint).
- **Bring your own models** — per-role models (a strong model to expand, a cheap
  one to judge/synthesize), via one OpenRouter key or per-provider keys. Ollama
  works for fully local runs.
- **Cost control** — live cost tracking and an optional budget cap that stops a
  run at a branch boundary.
- **Export & replay** — download a decision memo (Markdown/JSON) and scrub back
  through how a session unfolded.

## Install & run

Kodoku ships as one process that serves the UI and API together on
`http://localhost:8000` and stores everything in a `kodoku.db` SQLite file. Add
a model key in-app under **Settings** to start.

### With pipx (needs Python 3.12+ and Node 20+ to build the UI)

```bash
python scripts/build.py   # builds the UI and stages it into the package
pipx install ./backend
kodoku                    # starts the server and opens http://localhost:8000
```

`kodoku --help` shows `--host`, `--port`, and `--no-browser`.

### With Docker (no Python/Node needed)

```bash
docker build -t kodoku .
docker run --rm -p 8000:8000 -v kodoku-data:/data kodoku
# open http://localhost:8000
```

The `-v kodoku-data:/data` volume persists your sessions across container
restarts.

### First run

1. Open the app and go to **Settings**.
2. Add an API key — the simplest is one **OpenRouter** key (one key, many
   models). Per-provider keys (OpenAI, Anthropic, DeepSeek, …) also work, as
   does an **Ollama** base URL for local models.
3. Back on the home page, click **New session**, describe a goal, and **Run**.

## Configuration

All configuration is in-app under **Settings** (stored in the local DB):

- **Provider keys (BYOK)** — never displayed in full after saving; only a
  4-character hint is shown.
- **Per-role models** — `expand` / `evaluate` / `synthesize`. Defaults favor a
  strong model for expansion and a cheap one for scoring. Any LiteLLM-style
  `provider/model` slug works, including custom ones not in the shortlist.
- **Per session** (New session dialog) — goal, model, optional per-branch model
  overrides, human-review mode, decision mode (threshold vs. LLM judge), and an
  optional USD budget cap.

The only environment variable you may want is `DATABASE_URL`. It defaults to
`sqlite+aiosqlite:///./kodoku.db`. Point it at a `postgresql+asyncpg://…` URL to
run against Postgres instead (intended for a future hosted/multi-user build).

## Development

The packaged app serves a *prebuilt* UI. For development, run the backend and
frontend as two processes with hot reload.

Prereqs: Python 3.12, Node 20+.

```bash
# Backend (terminal A)
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn kodoku.main:app --reload --port 8000   # creates kodoku.db on first run

# Frontend (terminal B)
cd frontend
cp .env.example .env.local       # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev                      # http://localhost:3000
```

The backend creates the SQLite schema automatically on startup; no migration
step is needed for the local default. (Postgres uses Alembic: `alembic upgrade
head`.)

### Tests & checks

```bash
# Backend
cd backend && pytest && ruff check kodoku tests && mypy kodoku

# Frontend
cd frontend && npm run typecheck && npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs the backend suite, the frontend
build, and a Docker build that smoke-tests the packaged single-port app.

### Regenerating frontend types

`frontend/lib/types/contracts.ts` is generated from the backend's OpenAPI
schema. After changing a Pydantic DTO, run the backend, then:

```bash
cd frontend && npm run gen:contracts
```

## Tech stack

- **Frontend:** Next.js 14 (App Router, static export), TypeScript, Tailwind,
  Zustand, React Flow.
- **Backend:** FastAPI, SQLAlchemy 2 (async), Pydantic v2; Alembic for Postgres.
- **Database:** SQLite by default (local-first); PostgreSQL supported.
- **LLM:** LiteLLM (OpenRouter / OpenAI / Anthropic / DeepSeek / Ollama / …).

## Repo layout

```
kodoku/
├── backend/         FastAPI + SQLAlchemy; the kodoku package + CLI
├── frontend/        Next.js 14 app (built to a static export)
├── scripts/         build.py — stage the UI into the package for packaging
├── docs/            architecture notes, specs, plans
└── Dockerfile       multi-stage: build UI → serve UI + API on one port
```

## License

See `LICENSE`.
