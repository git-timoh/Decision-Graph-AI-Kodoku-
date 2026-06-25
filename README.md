# Kodoku — Decision Graph AI

> Tree-of-thoughts planner that turns a goal into a graph of explored, evaluated,
> and synthesized ideas — with human-in-the-loop checkpoints at every step.

**Status:** M2 (domain model + REST CRUD) complete. See `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md`
for the full design spec and `docs/architecture.md` for milestone status.

## Install & run (local app)

Kodoku runs entirely on your machine: one process serves the UI and API, and it
stores everything in a `kodoku.db` SQLite file. Bring your own model key via the
in-app `/settings` page.

**With pipx (needs Python 3.12+ and Node 20+ to build the UI):**

```bash
python scripts/build.py   # builds the UI and stages it into the package
pipx install ./backend
kodoku                    # starts the server and opens http://localhost:8000
```

**With Docker (no Python/Node needed):**

```bash
docker build -t kodoku .
docker run --rm -p 8000:8000 -v kodoku-data:/data kodoku
# open http://localhost:8000
```

Both serve on one port; there is no separate frontend process. The two-process
`next dev` + `uvicorn` flow below is only for development.

## Stack

- **Frontend:** Next.js 14, TypeScript, Tailwind, Zustand, React Flow (M3+)
- **Backend:** FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2
- **Database:** PostgreSQL 16
- **LLM:** LiteLLM (Claude / OpenAI / OpenRouter / Ollama — wired in M4)
- **Deploy:** Vercel (frontend), Fly.io (backend) — wired in M6

## Quickstart (local dev)

Prereqs: Docker Desktop, Node 20+, Python 3.12.

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

## Local LLM (Ollama) dev mode

Set `LLM_MODEL=ollama/llama3.1` and `OLLAMA_BASE_URL=http://localhost:11434` in `backend/.env` once Ollama is running locally. Recommended models: `qwen2.5:7b-instruct` or `llama3.1:8b`. (Wired in M4.)

## Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm run typecheck && npm run lint
```

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
