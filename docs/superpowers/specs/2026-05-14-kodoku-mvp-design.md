# Kodoku MVP — Decision Graph AI Design Spec

**Date:** 2026-05-14
**Status:** Approved for implementation planning
**Working name:** Kodoku
**Resume framing:** Decision Graph AI / Tree of Thoughts Planner

## 1. Purpose

Kodoku is a decision engine that helps a user explore multiple candidate ideas
or plans, branch them into alternatives, critique them, score them, prune weak
paths, and synthesize the strongest final recommendation. It is not a chatbot.
The system visibly models reasoning as a graph of branches rather than a single
linear chat response, with human-in-the-loop checkpoints at every key step.

**Initial use case:** idea generation and structured exploration for side
projects, startup ideas, and personal decisions.

**Long-term direction:** reusable decision-search engine with human-in-the-loop
checkpoints, extensible to tool-using agents (MCP) later.

## 2. Locked product and stack decisions

| Area | Decision |
|---|---|
| Auth | No login UI in v1. Every domain table carries `user_id` from day one with default `"local"`, so multi-user is a future migration, not a rewrite. |
| LLM serving | LiteLLM as the dispatcher behind a typed `LLMClient` protocol. Ollama is a first-class **dev-mode** provider (free, local). Deployed demo uses Claude or OpenAI directly through LiteLLM. |
| HITL | Auto-run with named checkpoints. User can approve, edit, skip, or interrupt at each checkpoint. |
| Graph viz | React Flow with custom node components and `dagre` layout. |
| Backend host | Fly.io, single Dockerfile, persistent machine (clean WebSocket support). |
| Frontend host | Vercel. |
| Database | PostgreSQL (Fly Postgres for prod, Docker Postgres for local). |
| Orchestration | Lightweight custom state-machine orchestrator (not LangGraph). |
| History | Left-sidebar list of named past sessions, revisitable. |
| Export | Markdown export of completed sessions. |

## 3. MVP scope

**In scope.** Create session with goal → root node renders → engine
auto-generates N candidate branches → each branch is evaluated (score +
critique) → engine proposes prune/expand/keep at a checkpoint → user approves
or overrides → loop continues to configured depth → engine synthesizes final
recommendation → all state persisted, resumable, listed in sidebar → Markdown
export of completed sessions.

**Out of scope for v1.** Auth, multi-user UI, pgvector memory or RAG, MCP
exposure, mobile layout, multi-LLM A/B in the same session, real-time
collaboration, fine-grained tool use per node, billing.

**Recruiter signal targets.** Explicit state machine; streamed WebSocket
events with a live-updating graph; provider-agnostic LLM layer with local
Ollama option; clean typed contracts shared between frontend and backend;
dockerized backend; one-click deploy; written architecture doc with state
diagram.

## 4. Top-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js 14 (Vercel)                                            │
│  ├── app/                         routes: /, /s/[sessionId]    │
│  ├── components/graph/            React Flow + custom nodes    │
│  ├── components/panels/           NodeDetail, Checkpoint, Goal │
│  ├── lib/ws/                      typed WS client + reducer   │
│  ├── lib/api/                     fetch wrappers (typed)       │
│  ├── lib/types/contracts.ts       generated from OpenAPI       │
│  └── state/                       Zustand store (graph state)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │  HTTPS (REST) + WSS (events)
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI (Fly.io, single container)                             │
│  ├── api/                         REST routers                  │
│  ├── ws/                          WebSocket manager + router    │
│  ├── engine/                                                    │
│  │   ├── state_machine.py         DecisionEngine + states       │
│  │   ├── runner.py                SessionRunner registry        │
│  │   ├── events.py                EventBus + typed events       │
│  │   ├── prompts/                 versioned prompt templates    │
│  │   └── steps/                   expand, evaluate, decide,     │
│  │                                synthesize                    │
│  ├── llm/                                                       │
│  │   ├── base.py                  LLMClient protocol            │
│  │   └── litellm_client.py        LiteLLM-backed implementation │
│  ├── domain/                      pure dataclasses + enums      │
│  ├── repo/                        SQLAlchemy repositories       │
│  ├── db/                          engine, models, migrations    │
│  └── main.py                      app factory                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                  ┌────────▼────────┐
                  │  PostgreSQL     │
                  │  (Fly Postgres) │
                  └─────────────────┘
```

**Type sharing.** Backend defines Pydantic models, FastAPI exports OpenAPI,
frontend generates `lib/types/contracts.ts` via `openapi-typescript`. One
source of truth. A regen script is committed and runs in CI.

## 5. Data model

Single user means `user_id` is on every row but defaults to `"local"`. UUIDs
throughout. All timestamps `timestamptz`.

```sql
sessions
  id              uuid pk
  user_id         text not null default 'local'
  title           text not null            -- short summary, editable
  goal            text not null            -- the original problem statement
  status          text not null            -- 'draft'|'running'|'awaiting_human'|'done'|'error'|'paused'
  config          jsonb not null           -- {model, branching_factor, max_depth, temperature}
  current_step    text                     -- mirrors DecisionEngine state for UI
  final_synthesis text                     -- populated when done
  created_at      timestamptz default now()
  updated_at      timestamptz default now()

nodes
  id              uuid pk
  session_id      uuid fk -> sessions.id on delete cascade
  parent_id       uuid fk -> nodes.id null            -- null for root
  depth           int  not null
  kind            text not null            -- 'root'|'candidate'|'synthesis'
  title           text not null            -- short label rendered on the node
  content         text not null            -- the full idea/branch text
  status          text not null            -- 'pending'|'active'|'pruned'|'kept'|'expanded'
  created_at      timestamptz default now()

evaluations
  id              uuid pk
  node_id         uuid fk -> nodes.id on delete cascade
  score           numeric(4,2) not null    -- 0.00-10.00
  critique        text not null
  dimensions      jsonb not null           -- {feasibility, novelty, impact, effort, fit}
  model           text not null
  created_at      timestamptz default now()

checkpoints
  id              uuid pk
  session_id      uuid fk -> sessions.id on delete cascade
  kind            text not null            -- 'post_expand'|'post_evaluate'|'pre_synthesis'
  payload         jsonb not null           -- engine's proposed action: {prune:[id], expand:[id], keep:[id]}
  decision        jsonb                    -- user's resolution; null until resumed
  resolved_at     timestamptz
  created_at      timestamptz default now()

events
  id              bigserial pk
  session_id      uuid fk -> sessions.id on delete cascade
  type            text not null            -- mirrors WS event names
  payload         jsonb not null
  created_at      timestamptz default now()
```

The `events` table is the durable journal. Every WebSocket message is appended
here first, then fanned out to live subscribers. Reconnecting clients fetch
`/events?since=event_id` then resume the socket — that is the entire
streaming-resumability story.

**Indexes.** `nodes(session_id, parent_id)`, `evaluations(node_id)`,
`checkpoints(session_id, resolved_at)`, `events(session_id, id)`.

## 6. REST API

```
POST   /sessions                    -> {session_id}
       body: {goal, title?, config?}                    create session + root node atomically
GET    /sessions                    -> [{id, title, status, ...}]      sidebar list
GET    /sessions/{id}               -> full session + nodes + evaluations + checkpoints
PATCH  /sessions/{id}               -> rename, update config (only when not running)
DELETE /sessions/{id}

POST   /sessions/{id}/run           -> 202                 start the engine, or resume from PAUSED/ERROR
POST   /sessions/{id}/resume        -> 202                 resolve an AWAITING_HUMAN checkpoint
       body: {checkpoint_id,
              decision: {keep:[node_id], prune:[node_id], expand:[node_id],
                         edits:{node_id:{title?,content?}}}}
POST   /sessions/{id}/interrupt     -> 202                 stop the engine at the next safe point
GET    /sessions/{id}/events?since= -> [WsEvent...]        replay log for cold reconnect
GET    /sessions/{id}/export        -> text/markdown       full session as markdown

GET    /healthz
```

All bodies are Pydantic models. OpenAPI is the contract surface; TS types are
generated from it. Writes are funneled through `/run` and `/resume` so the
engine has a single write path into the domain tables — clients never `POST` to
`/nodes`.

## 7. WebSocket contract

`WS /ws/sessions/{id}` — server-push only. Client commands go through REST so
the engine remains the single writer. Every message:

```ts
type WsEvent = {
  id: number;             // monotonic, matches events.id
  type: string;
  session_id: string;
  ts: string;             // ISO8601
  payload: object;
};
```

**Event types:**
- `session.started` / `session.done` / `session.error`
- `engine.state_changed` `{from, to}`
- `node.created` / `node.updated` / `node.pruned`
- `evaluation.completed` `{node_id, score, critique, dimensions}`
- `checkpoint.reached` `{checkpoint_id, kind, payload}`
- `checkpoint.resolved` `{checkpoint_id, decision}`
- `synthesis.streaming` `{delta}`  ← token-streamed final answer
- `synthesis.completed` `{text}`

**Client behavior.** Zustand store keyed by `session_id`. Single reducer
handles each event type. Last-seen `event.id` is kept in store; on reconnect,
client fetches `/events?since=<lastSeen>` first, applies them, then opens the
socket and resumes from there.

## 8. Tree-of-thoughts state machine

```
       ┌──── new session ────┐
       ▼                     │
    [ROOT] ──run──► [EXPANDING] ──► [EVALUATING] ──► [AWAITING_HUMAN]
                       ▲                                  │
                       │                                  ▼
                       └──── resume(expand) ─── [DECIDING] ──┐
                                                             │
                                              resume(synthesize)
                                                             ▼
                                                     [SYNTHESIZING] ──► [DONE]
                                                                          │
                                       any state ──interrupt──► [PAUSED] ─┘
                                       any state ──error──► [ERROR]
```

**`DecisionEngine`** owns: current state, session/node/checkpoint
repositories, an `EventBus`, and an `LLMClient`. Each state is implemented as
an async method (`async def expand(self) -> None`) that mutates the database,
emits events through the bus, and returns the next state. The engine runs as a
single `asyncio.Task` per session, registered in an in-memory `SessionRunner`
registry.

**Frontier queue.** The engine maintains an in-memory FIFO queue of node IDs
to expand. It is seeded with the root node ID when `/run` is first called.
Each `DECIDING` transition pushes the user-approved `expand` node IDs onto the
queue. `EXPANDING` pops the next node and operates on it as the "active
parent". When the queue is empty (or `config.max_depth` is reached) the engine
transitions to a `pre_synthesis` checkpoint. The queue is rebuilt from DB
state (`nodes.status = 'expanded' AND has children`) on resume from `PAUSED`.

**State responsibilities.**
- `EXPANDING` — pop the next node from the frontier as the active parent;
  call `expand` step; generate `config.branching_factor` candidates as new
  `nodes` rows under that parent; mark parent as `expanded`; emit
  `node.created` per child.
- `EVALUATING` — call `evaluate` step on each new candidate, persist
  `evaluations` rows, emit `evaluation.completed`.
- `AWAITING_HUMAN` — create a `checkpoint` row, emit `checkpoint.reached`, halt
  the task by awaiting a condition var keyed on `checkpoint_id`.
- `DECIDING` — apply user's decision (mark nodes as `pruned` or `kept`; push
  `expand`-marked nodes onto the frontier queue); if queue is non-empty,
  transition back to `EXPANDING`, else go to `pre_synthesis` checkpoint.
- `SYNTHESIZING` — call `synthesize` step using `kept` nodes as context;
  stream tokens through `synthesis.streaming` events; persist
  `final_synthesis`.

**Crash and restart behavior (v1).** On app restart, any session in `running`
or `awaiting_human` status is *not* auto-resumed. The UI shows them as
`paused`; the user clicks "Resume" to re-enter the engine. Durable
cross-restart execution is explicitly deferred — YAGNI for v1.

**Termination conditions.** Engine ends when (a) reached `config.max_depth`,
(b) all candidates at the current frontier are pruned, or (c) user resolves a
`pre_synthesis` checkpoint with `synthesize: true`.

## 9. LLM provider layer

```python
# backend/kodoku/llm/base.py
class LLMClient(Protocol):
    async def complete(
        self, *, system: str, prompt: str,
        json_schema: dict | None = None,
    ) -> str: ...

    async def stream(
        self, *, system: str, prompt: str,
    ) -> AsyncIterator[str]: ...


# backend/kodoku/llm/litellm_client.py
class LiteLLMClient:
    def __init__(self, model: str):
        # model strings as understood by LiteLLM:
        #   "anthropic/claude-sonnet-4-6"
        #   "openai/gpt-4o-mini"
        #   "openrouter/anthropic/claude-3.5-sonnet"
        #   "ollama/llama3.1"
        self.model = model

    async def complete(self, *, system, prompt, json_schema=None): ...
    async def stream(self, *, system, prompt): ...
```

**Configuration.** `Session.config.model` carries one LiteLLM-style model
string. The new-session modal exposes a dropdown with sensible presets (Claude
Sonnet, GPT-4o-mini, OpenRouter Sonnet, Ollama Llama 3.1) and a free-text
override so any LiteLLM-supported model works.

**Ollama dev mode.** README documents:

```
LLM_MODEL=ollama/llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

Ollama is recommended for cost-free development with `qwen2.5:7b-instruct` or
`llama3.1:8b`. It is not the recommended demo path — recruiter-facing deploy
uses Claude or OpenAI through LiteLLM.

**Structured outputs.** Prompts that require JSON (expand, evaluate, decide)
go through LiteLLM's `response_format={"type":"json_object"}` where supported
and a Pydantic-validating retry wrapper (max 2 retries) before erroring.

## 10. Orchestration choice — rationale

The state space for ToT reasoning is small and well-defined (six states plus
two terminal states). A custom orchestrator wins over LangGraph for this
project because:

1. The mapping from states to code is 1:1 and explicit — every state is a
   readable async method.
2. HITL pause-at-checkpoint is mechanically simpler as "emit, halt, await
   condition" than as LangGraph's interrupt model.
3. Provider abstraction through `LLMClient` stays clean without LangChain
   wrappers.
4. The interview story is *"I designed an explicit state machine for
   tree-of-thoughts reasoning"*, which is a stronger signal than *"I used
   LangGraph"*.

LangGraph would be the right answer if the workflow grew to dozens of nodes,
sub-graphs, or required durable cross-restart execution. For this MVP it is
overkill. The domain types (`Node`, `Branch`, `Evaluation`, `Checkpoint`)
survive a future swap if needed.

## 11. Phased roadmap

Six milestones. Each is one focused PR / commit set, verifiable end-to-end
before the next begins.

### M1 — Skeleton + contracts
**Goal.** Repo compiles and runs locally; FE talks to BE; no AI yet.
**Files.** `backend/kodoku/{main.py, settings.py, api/health.py, db/{base,engine}.py}`, alembic init, `frontend/{app/page.tsx, app/layout.tsx, lib/api/client.ts}`, `docker-compose.yml`, `.env.example`, `pyproject.toml`, `package.json`, `README.md`.
**Backend tasks.** FastAPI app factory; `/healthz`; SQLAlchemy + Alembic wired to Postgres; Pydantic settings; CORS; logging; pytest scaffold.
**Frontend tasks.** Next.js 14 app router, Tailwind, shadcn/ui, Zustand, env config, fetch wrapper, `/healthz` ping rendered in UI.
**Verification.** `docker compose up` starts Postgres; `uvicorn` and `next dev` both run; FE shows backend healthcheck; `pytest` and `tsc --noEmit` pass.
**Risks.** Windows + Docker quirks; pin all major versions in `pyproject.toml` and `package.json` early.

### M2 — Domain model + REST CRUD
**Goal.** Sessions, nodes, evaluations, checkpoints can be created or read via REST and persist.
**Files.** `backend/kodoku/{domain/models.py, db/models.py, repo/*, api/sessions.py, api/nodes.py}`, alembic revision `001_initial.py`, `backend/tests/test_sessions_api.py`.
**Backend tasks.** SQLAlchemy models matching section 5; Pydantic DTOs; repositories; session/list/get/create/rename/delete endpoints; `POST /sessions` creates session + root node atomically.
**Frontend tasks.** Sidebar list page hitting `GET /sessions`; "new session" modal with goal + model preset dropdown; route `/s/[id]` shows raw goal + root node (no graph yet).
**Verification.** Create a session via UI, see it in sidebar, refresh, still there. Integration test covers create→list→get→delete.
**Risks.** Schema churn; commit the `contracts.ts` regen script in this milestone to avoid drift.

### M3 — React Flow graph + WebSocket plumbing
**Goal.** Graph renders from DB state; WS connection wired with reconnection and replay; scripted fake events drive UI updates.
**Files.** `frontend/components/graph/{Graph.tsx, NodeCard.tsx, layout.ts}`, `frontend/lib/ws/{client.ts, reducer.ts}`, `frontend/state/sessionStore.ts`, `backend/kodoku/ws/{manager.py, router.py}`, `backend/kodoku/api/events.py`.
**Backend tasks.** WS endpoint with session_id (single-user, no auth-token); broadcast manager; events table append; `/events?since=` replay endpoint; a debug endpoint that emits scripted fake events for FE development.
**Frontend tasks.** React Flow canvas; `dagre` layout helper; custom `NodeCard` for root/candidate/synthesis kinds with status colors; WS client with exponential backoff + replay-on-reconnect; reducer per event type.
**Verification.** Open `/s/[id]`, hit debug endpoint, see fake nodes and evaluations appear live with smooth layout. Kill WS, reconnect, state matches.
**Risks.** Layout shifting on every new node — use `dagre` with fixed direction and animate transitions.

### M4 — DecisionEngine + LLM abstraction
**Goal.** Real Tree-of-Thoughts loop end-to-end through LiteLLM, including the Ollama dev path.
**Files.** `backend/kodoku/engine/{state_machine.py, runner.py, events.py, prompts/*, steps/{expand,evaluate,decide,synthesize}.py}`, `backend/kodoku/llm/{base.py, litellm_client.py}`, `backend/kodoku/api/run.py`, `backend/tests/test_engine.py`.
**Backend tasks.** `LLMClient` protocol + LiteLLM impl; prompt templates with explicit JSON schemas and versioned filenames; engine states with strict typing; `SessionRunner` registry; `POST /run` starts a task; `POST /interrupt` cancels it; events emitted to bus and journaled.
**Frontend tasks.** "Run" button on session page; engine-state badge; streaming-aware reducer for `synthesis.streaming`.
**Verification.** Create session with a real goal ("side project ideas combining AI and music"), click run, watch candidates appear, evaluations populate, synthesis streams in. Unit tests stub `LLMClient` with a fake that returns fixed structured outputs. Smoke test against local Ollama.
**Risks.** LLM returning non-conforming JSON — use structured output mode where supported and a Pydantic-validating retry wrapper (max 2 retries) before erroring. Local Ollama JSON conformance is shakier; document model recommendations.

### M5 — Human-in-the-loop checkpoints
**Goal.** Engine pauses at named checkpoints; user resolves; engine continues with the resolution applied.
**Files.** `backend/kodoku/engine/state_machine.py` (extend), `backend/kodoku/api/run.py` (`/resume`), `frontend/components/panels/CheckpointPanel.tsx`, `frontend/components/graph/NodeCard.tsx` (selection + edit).
**Backend tasks.** Transition to `AWAITING_HUMAN`; persist checkpoint; await resolution via condition var keyed on `checkpoint_id`; `POST /resume` validates decision against checkpoint, marks resolved, advances engine.
**Frontend tasks.** When `checkpoint.reached`, slide-in panel listing engine's proposed prunes/expansions; user can toggle, edit node titles/content inline, then "approve and continue" or "skip" (no changes). Show pruned nodes as faded in the graph.
**Verification.** Run a session, see the checkpoint, override the engine's prune decision, resume, observe the override reflected in the next iteration's expansions.
**Risks.** Race between engine emitting `checkpoint.reached` and UI submitting resume — solve by gating `/resume` acceptance on `checkpoint_id` match.

### M6 — Provider polish + export + deploy
**Goal.** Multiple model presets working through one LiteLLM client; app deployed; README is recruiter-ready.
**Files.** `backend/Dockerfile`, `fly.toml`, `.github/workflows/ci.yml`, `frontend/vercel.json`, `README.md`, `docs/architecture.md`, `docs/screenshots/*`, `backend/kodoku/api/export.py`, `frontend/components/panels/RunControls.tsx`.
**Backend tasks.** Markdown export endpoint; Dockerfile (multi-stage); Fly deploy with managed Postgres; env wiring; CI workflow (lint, typecheck, pytest, tsc).
**Frontend tasks.** Provider/model selector finalized in new-session modal; export button on done sessions; favicon, OG image, empty states, polish pass.
**Verification.** Deploy to Fly + Vercel; run a session against Claude and OpenAI; share URL; refresh on prod; history persists across machine restarts.
**Risks.** WebSocket through Vercel — frontend hits Fly host directly for `wss://`, not via Vercel rewrite. Test early in M6.

## 12. Task breakdown

Each line is approximately one Claude Code session.

**M1**
- M1.1 scaffold backend (FastAPI, settings, healthz, pytest, dev Dockerfile)
- M1.2 scaffold frontend (Next.js, Tailwind, shadcn, Zustand, env)
- M1.3 docker-compose with Postgres + .env.example
- M1.4 Alembic + base SQLAlchemy + first empty migration
- M1.5 typed `lib/api/client.ts` + healthz ping displayed in UI
- M1.6 root README skeleton + `docs/architecture.md` stub

**M2**
- M2.1 SQLAlchemy models for all five tables + migration `001_initial`
- M2.2 Pydantic DTOs + `contracts.ts` regen script
- M2.3 Session repository + service layer
- M2.4 REST routes for sessions (CRUD)
- M2.5 Node read endpoints (no writes — engine owns writes)
- M2.6 integration tests for session lifecycle
- M2.7 sidebar list UI + new-session modal + `/s/[id]` shell

**M3**
- M3.1 events table + repo + `/events?since=` endpoint
- M3.2 WS manager + router + connection lifecycle
- M3.3 debug endpoint to emit scripted events
- M3.4 WS client with reconnect + replay
- M3.5 Zustand store + reducer per event type
- M3.6 React Flow canvas + dagre layout helper
- M3.7 `NodeCard` custom node (root/candidate/synthesis variants)

**M4**
- M4.1 `LLMClient` protocol + fake test implementation
- M4.2 `LiteLLMClient` (streaming + structured JSON)
- M4.3 prompt templates with versioning
- M4.4 `expand` step + tests against fake
- M4.5 `evaluate` step + tests
- M4.6 `decide` step (deterministic policy over scores)
- M4.7 `synthesize` step (streaming)
- M4.8 `DecisionEngine` state machine + `SessionRunner` registry
- M4.9 `/run` + `/interrupt` endpoints
- M4.10 run-button UI + state badge + streaming reducer
- M4.11 smoke test against local Ollama, document model recommendations

**M5**
- M5.1 extend engine with `AWAITING_HUMAN` + checkpoint persistence
- M5.2 `/resume` endpoint with checkpoint validation
- M5.3 `CheckpointPanel` UI
- M5.4 node selection + inline edit
- M5.5 end-to-end HITL test against fake `LLMClient`

**M6**
- M6.1 Markdown export endpoint + UI button
- M6.2 Dockerfile (multi-stage) + `fly.toml` + Fly deploy
- M6.3 Vercel deploy + WS host config
- M6.4 README polish + screenshots + arch doc + demo GIF
- M6.5 GitHub Actions CI (lint, typecheck, pytest, tsc)

## 13. README outline

```
# Kodoku — Decision Graph AI (Tree of Thoughts Planner)

> One-paragraph hook: what it does and why it's interesting.

[Demo GIF]
[Live demo link] [Architecture doc]

## What it is
- Problem (linear chat ≠ structured exploration)
- Core loop in one diagram (state-machine PNG)

## Highlights
- Explicit state-machine orchestration (no opaque agent loop)
- Streaming WebSocket events with a durable journal and replay on reconnect
- Provider-agnostic LLM layer (LiteLLM) with Claude / OpenAI / Ollama / OpenRouter
- Human-in-the-loop checkpoints with approve / edit / skip
- Strongly typed end-to-end contracts (Pydantic → OpenAPI → TS)

## Architecture
- Diagram
- Module map (backend + frontend)
- Data model (ERD)
- WebSocket event taxonomy
- Link to docs/architecture.md for the long version

## Tree of Thoughts loop
- Stepwise walkthrough with screenshots from each checkpoint

## Tech
- Next.js 14, TypeScript, React Flow, Zustand, Tailwind/shadcn
- FastAPI, SQLAlchemy, Alembic, Pydantic v2
- Postgres, WebSockets
- LiteLLM (Claude / OpenAI / OpenRouter / Ollama)
- Docker, Fly.io, Vercel

## Running locally
- Prereqs, `.env`, `docker compose up`, `make dev`, run a session

## Local LLM (Ollama) dev mode
- Install Ollama, pull `llama3.1:8b` or `qwen2.5:7b-instruct`
- Set `LLM_MODEL=ollama/llama3.1` and `OLLAMA_BASE_URL=http://localhost:11434`

## Project structure
- Annotated tree of the top two levels

## Design decisions
- Why a custom orchestrator over LangGraph
- Why a single events table powers both WS and replay
- Why HITL is a first-class state, not a feature flag

## Roadmap
- pgvector memory, multi-user, MCP tool exposure, branch comparison view

## License
```

## 14. Final repo layout

```
kodoku/
├── README.md
├── LICENSE
├── docker-compose.yml
├── .env.example
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md
│   ├── superpowers/specs/
│   └── screenshots/
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── fly.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── kodoku/
│   │   ├── main.py
│   │   ├── settings.py
│   │   ├── api/{health,sessions,nodes,run,events,export}.py
│   │   ├── ws/{manager,router}.py
│   │   ├── engine/
│   │   │   ├── state_machine.py
│   │   │   ├── runner.py
│   │   │   ├── events.py
│   │   │   ├── prompts/{expand,evaluate,synthesize}.md
│   │   │   └── steps/{expand,evaluate,decide,synthesize}.py
│   │   ├── llm/{base,litellm_client}.py
│   │   ├── domain/{models,enums}.py
│   │   ├── repo/{sessions,nodes,evaluations,checkpoints,events}.py
│   │   └── db/{engine,models,base}.py
│   └── tests/
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── next.config.mjs
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx
    │   └── s/[sessionId]/page.tsx
    ├── components/
    │   ├── graph/{Graph,NodeCard,layout}.tsx
    │   ├── panels/{GoalPanel,NodeDetail,CheckpointPanel,RunControls}.tsx
    │   └── ui/                       (shadcn primitives)
    ├── lib/
    │   ├── api/client.ts
    │   ├── ws/{client,reducer}.ts
    │   └── types/contracts.ts        (generated)
    ├── state/sessionStore.ts
    └── styles/
```

## 15. Open questions / deferred decisions

- **Concurrency model for the engine.** Single `asyncio.Task` per session is fine for v1 since one user runs one session at a time. If session count grows, move to a worker queue (Arq or RQ) — not now.
- **Prompt caching.** Anthropic prompt caching through LiteLLM works but is wired differently than the native SDK; revisit in M6 once prompts stabilize.
- **Multi-provider in one session.** Not in v1. The schema already supports it via `evaluations.model`, but the UI does not expose it.
- **Auth path when needed.** When auth is added, swap `user_id="local"` for the authenticated user, add NextAuth or Clerk on the frontend, gate WS connections by token. Schema is already shaped for it.
