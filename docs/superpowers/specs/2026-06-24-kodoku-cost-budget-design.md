# Cost Tracking + Budget Hard-Stop — Design

**Goal:** Track per-session LLM spend (USD + tokens) live, with an optional budget cap that hard-stops the run at a branch boundary. This closes the "unbudgeted cost/latency" gap flagged in the product thesis. It is the remaining Phase B work after the LLM-as-judge `decide` (shipped 2026-06-24).

**Explicitly dropped (YAGNI):** the `litellm.Router` — Phase A already builds one `LiteLLMClient` per role (`expand`/`evaluate`/`synthesize`), so per-role routing exists; a Router only adds load-balancing/fallbacks/retries, none needed for a local single-user tool. Cost tracking uses the plain `litellm.completion_cost` on the existing calls.

## Scope

In scope:
- Per-session cumulative `cost_usd` (and prompt/completion token totals), persisted, surviving resume.
- Live cost display in the UI (fed by a journaled `cost.updated` event).
- Optional `SessionConfig.budget_usd`. When exceeded, hard-stop the run before synthesis (mirrors the M5 `_paused` checkpoint flow).

Out of scope (say so if wanted later):
- Per-role or per-node cost breakdown — session running total only.
- Budget-gating the final synthesis call — synthesis runs after the BFS loop, so its cost lands in the total but is not gated. `ponytail:` noted.

## Architecture

### 1. Config (`backend/kodoku/api/dtos.py`)
Add to `SessionConfig`:
```python
budget_usd: float | None = Field(default=None, ge=0)
```
`None` = no cap. `extra="forbid"` already set; default applies to missing field, so stored configs without it still parse (backward compatible).

### 2. Cost capture (client layer)
Extend the `LLMClient` protocol (`backend/kodoku/llm/base.py`) with a cumulative attribute:
```python
cost_usd: float   # running total of completion_cost across this client's calls
```
- `LiteLLMClient` (`litellm_client.py`): init `self.cost_usd = 0.0`. In `complete`, after the response, add `litellm.completion_cost(completion_response=response)` to `self.cost_usd`. Wrap in a guard so a cost-calc failure (unknown model) never breaks the call — best-effort add, `ponytail:` noted.
- `stream` (synthesize role): request usage via `stream_options={"include_usage": True}`; if a final usage chunk arrives, compute and add its cost. Best-effort — `ponytail:` noted if the provider omits usage.
- `FakeLLMClient` (`fake.py`): add `cost_per_call: float = 0.0` constructor arg; each `complete` adds it to `self.cost_usd`. Lets engine tests drive the accumulator deterministically without a real provider.

### 3. Engine (`backend/kodoku/engine/state_machine.py`)
- New column `Session.cost_usd: Mapped[float]` (`Numeric`, default 0) in `backend/kodoku/db/models.py`, plus an alembic migration (autogenerate, following the `app_settings` migration pattern).
- At engine run start, capture `self._cost_base = float(session.cost_usd or 0)`.
- After each branch in the BFS loop (once per `_expand_one`), call a helper:
  - `total = self.clients.expand.cost_usd + self.clients.evaluate.cost_usd + self.clients.synthesize.cost_usd`
  - `self.session.cost_usd = self._cost_base + total`
  - emit `COST_UPDATED` with `{cost_usd, budget_usd}`
  - if `budget_usd is not None and self.session.cost_usd >= budget_usd`: set `self._budget_exceeded = True`, emit `BUDGET_EXCEEDED` with `{cost_usd, budget_usd}`.
- The BFS loop condition gains `and not self._budget_exceeded`. On exceed, after the loop: set status `PAUSED`, `current_step = None`, flush, return before synthesis (parallel to the existing `_paused` handling).
- Stays flush-only; the only `commit()` remains the `/run`//`/resume` boundary.

### 4. Events (`backend/kodoku/engine/events.py`)
```python
COST_UPDATED = "cost.updated"      # {cost_usd, budget_usd}
BUDGET_EXCEEDED = "budget.exceeded" # {cost_usd, budget_usd}
```
Update the module's name-count comment.

### 5. Frontend
- `NewSessionDialog.tsx`: optional "Budget (USD)" number input → `budget_usd` (empty = `null`). Regenerate `contracts.ts`.
- Live cost display: the WS reducer accumulates the latest `cost.updated` payload; render a small cost line/badge (e.g. `$0.0123` and tokens) near the session header/status.
- `budget.exceeded`: show a "Budget exceeded — run stopped" banner, mirroring the existing M5 paused/checkpoint banner markup.

## Data flow
LLM call → `LiteLLMClient` adds `completion_cost` to `self.cost_usd` → after each branch the engine sums role-client costs onto `session.cost_usd`, emits `cost.updated` (journaled) → frontend reducer shows live total. If `cost_usd >= budget_usd` → emit `budget.exceeded`, stop loop, session `PAUSED`. On reload, frontend reads the persisted total (session GET / last cost event). On resume, `_cost_base` seeds from the persisted `cost_usd` so the cap is cumulative across run segments.

## Testing
- Client: `LiteLLMClient` cost accrual not unit-tested against a live provider (`ponytail:` — no real calls); `FakeLLMClient.cost_per_call` accrual covered.
- Engine (fakes only): (a) cost accumulates and `cost.updated` emitted per branch; (b) budget exceeded → `budget.exceeded` emitted, session `PAUSED`, synthesis skipped; (c) `budget_usd=None` → never stops, behavior unchanged (existing autopilot suite proves regression-free); (d) `_cost_base` resume seeding — a session with prior `cost_usd` continues accumulating from it.
- Frontend: TS strict, typecheck + lint clean.

## Global constraints
- Python 3.12, `from __future__ import annotations`; mypy strict + ruff (E,F,I,B,UP,W) zero errors.
- Engine stays flush-only.
- Never hit a real provider in tests.
- TS strict, no `any`; regen `contracts.ts` after the `SessionConfig` change.
- `budget_usd=None` (default) → behavior byte-for-byte unchanged except the additive `cost.updated` emit.
