# Cost Tracking + Budget Hard-Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track per-session LLM spend (USD) live and hard-stop a run at a branch boundary when an optional budget cap is exceeded.

**Architecture:** Each `LLMClient` accumulates `cost_usd` from `litellm.completion_cost`. The engine sums the per-role client costs onto a new `Session.cost_usd` column after each branch, emits a `cost.updated` event, and (if `SessionConfig.budget_usd` is set and exceeded) emits `budget.exceeded`, marks the session `PAUSED`, and stops before synthesis — reusing the existing `_paused` stop pattern. The frontend shows live cost and a budget banner.

**Tech Stack:** Python 3.12, SQLAlchemy async, alembic, pydantic, pytest; Next.js 14 + TS strict. Spec: `docs/superpowers/specs/2026-06-24-kodoku-cost-budget-design.md`.

## Global Constraints

- Python 3.12, `from __future__ import annotations`. mypy `strict = true` zero errors; ruff line-length 100 rules `E,F,I,B,UP,W` zero errors. Match existing style.
- Engine STAYS flush-only; the only `commit()` is the `/run`//`/resume` boundary.
- Never hit a real provider in tests — use `FakeLLMClient` only. `LiteLLMClient` cost accrual is NOT unit-tested against a live provider.
- venv: `backend/.venv/Scripts/python.exe -m pytest|mypy|ruff` (run from `backend/`).
- Frontend: TS strict (no `any`), `npm run typecheck` + `npm run lint` clean; regenerate `frontend/lib/types/contracts.ts` after the dtos change (`npm run gen:contracts` from `frontend/`).
- `budget_usd=None` (default) → engine behavior byte-for-byte unchanged except the additive `cost.updated` emit. The existing engine/autopilot suite covers the regression.
- Tests build the schema via `Base.metadata.create_all` (tests/conftest.py:81), so the new column appears automatically in tests; the alembic migration is for real DBs.

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `backend/kodoku/llm/base.py` (modify) | Add `cost_usd: float` to the `LLMClient` protocol | 1 |
| `backend/kodoku/llm/litellm_client.py` (modify) | Accrue `completion_cost` per call (best-effort) | 1 |
| `backend/kodoku/llm/fake.py` (modify) | `cost_per_call` arg + accrual for tests | 1 |
| `backend/tests/test_llm_cost.py` (create) | Fake accrual + protocol conformance | 1 |
| `backend/kodoku/db/models.py` (modify) | `Session.cost_usd` column | 2 |
| `backend/alembic/versions/*_session_cost_usd.py` (create) | Additive migration | 2 |
| `backend/kodoku/engine/events.py` (modify) | `COST_UPDATED`, `BUDGET_EXCEEDED` | 2 |
| `backend/kodoku/api/dtos.py` (modify) | `SessionConfig.budget_usd`, `SessionResponse.cost_usd` | 2 |
| `backend/kodoku/engine/state_machine.py` (modify) | Cost accumulation, budget stop, events | 2 |
| `backend/tests/test_engine.py` (modify) | Cost/budget engine tests | 2 |
| `frontend/lib/types/contracts.ts` (regen) | Reflect dtos change | 2 |
| `frontend/lib/ws/types.ts` (modify) | `costUsd`/`budgetUsd`/`budgetExceeded` on `GraphState` | 3 |
| `frontend/lib/ws/reducer.ts` (modify) | `cost.updated` + `budget.exceeded` cases | 3 |
| `frontend/app/s/[sessionId]/SessionGraphView.tsx` (modify) | Live cost badge + budget banner | 3 |
| `frontend/app/_components/NewSessionDialog.tsx` (modify) | Optional budget input | 3 |

## Dependencies / order
1 → 2 (engine sums client `cost_usd`). 3 depends on 2's events + dtos. Order: 1, 2, 3.

---

### Task 1: Per-client cost accrual

**Files:**
- Modify: `backend/kodoku/llm/base.py`
- Modify: `backend/kodoku/llm/litellm_client.py`
- Modify: `backend/kodoku/llm/fake.py`
- Test: `backend/tests/test_llm_cost.py` (create)

**Interfaces:**
- Consumes: existing `LLMClient` protocol, `LiteLLMClient`, `FakeLLMClient`.
- Produces (later tasks rely on these):
  - `LLMClient.cost_usd: float` — cumulative USD across the client's calls.
  - `FakeLLMClient(..., cost_per_call: float = 0.0)` — adds `cost_per_call` to `self.cost_usd` on every `complete`.

- [ ] **Step 1: Add `cost_usd` to the protocol**

In `backend/kodoku/llm/base.py`, add to the `LLMClient` Protocol body (after `model: str`):

```python
    cost_usd: float
```

And extend the docstring's `model` sentence with: "`cost_usd` is the cumulative USD cost of this client's calls (best-effort; 0.0 if the provider/model has no cost data)."

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_llm_cost.py`:

```python
"""Cost accrual on LLM clients. Live providers are never called here."""
from __future__ import annotations

import pytest

from kodoku.llm.base import LLMClient
from kodoku.llm.fake import FakeLLMClient
from kodoku.llm.litellm_client import LiteLLMClient

pytestmark = pytest.mark.asyncio


async def test_fake_accrues_cost_per_call() -> None:
    llm = FakeLLMClient(completions=["a", "b"], cost_per_call=0.01)
    assert llm.cost_usd == 0.0
    await llm.complete(system="s", prompt="p")
    assert llm.cost_usd == pytest.approx(0.01)
    await llm.complete(system="s", prompt="p")
    assert llm.cost_usd == pytest.approx(0.02)


async def test_fake_default_cost_is_zero() -> None:
    llm = FakeLLMClient(completions=["a"])
    await llm.complete(system="s", prompt="p")
    assert llm.cost_usd == 0.0


def test_clients_satisfy_protocol() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)
    assert isinstance(LiteLLMClient(model="anthropic/claude-sonnet-4-6"), LLMClient)
    assert LiteLLMClient(model="x").cost_usd == 0.0
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_llm_cost.py -v`
Expected: FAIL — `FakeLLMClient.__init__` has no `cost_per_call` / `cost_usd` attribute missing.

- [ ] **Step 4: Implement fake accrual**

In `backend/kodoku/llm/fake.py`, update `__init__` signature and body:

```python
    def __init__(
        self,
        completions: list[str] | None = None,
        chunks: list[str] | None = None,
        model: str = "fake",
        cost_per_call: float = 0.0,
    ) -> None:
        self.model = model
        self.completions: list[str] = list(completions) if completions is not None else []
        self.chunks: list[str] = list(chunks) if chunks is not None else [""]
        self.calls: list[tuple[str, str]] = []
        self.cost_per_call = cost_per_call
        self.cost_usd = 0.0
```

And in `complete`, after appending to `self.calls`, before the exhausted check:

```python
        self.cost_usd += self.cost_per_call
```

- [ ] **Step 5: Implement litellm accrual**

In `backend/kodoku/llm/litellm_client.py`:

1. Add the import near the top (after `import litellm`):

```python
from litellm import completion_cost
```

2. In `__init__`, after `self.api_base = api_base`, add:

```python
        self.cost_usd = 0.0
```

3. In `complete`, after `result = cast(ModelResponse, response)` and before the `return`, add:

```python
        # ponytail: best-effort — completion_cost raises for models it has no
        # pricing for; a costless call must never break completion.
        try:
            self.cost_usd += completion_cost(completion_response=result)
        except Exception:  # noqa: BLE001
            pass
```

4. In `stream`, request usage and accrue best-effort. Change the `acompletion` call to add `stream_options={"include_usage": True}` after `stream=True,`. Then inside the `async for chunk in stream:` loop, after the existing `content`/yield handling, add a best-effort cost accrual when a usage-bearing chunk arrives:

```python
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                # ponytail: best-effort streaming cost; providers that omit
                # usage in the final chunk leave synthesis cost at 0.
                try:
                    self.cost_usd += completion_cost(
                        completion_response=chunk, model=self.model
                    )
                except Exception:  # noqa: BLE001
                    pass
```

(Place the `usage` block inside the loop, after the `if content:` yield block, so both run per chunk.)

- [ ] **Step 6: Run the test, verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_llm_cost.py -v`
Expected: PASS (3 passed). `test_clients_satisfy_protocol` confirms both clients still satisfy the runtime-checkable protocol with the new attribute.

- [ ] **Step 7: Lint + type-check**

Run: `backend/.venv/Scripts/python.exe -m ruff check kodoku tests` then `backend/.venv/Scripts/python.exe -m mypy kodoku`
Expected: both clean.

- [ ] **Step 8: Commit**

```bash
git add backend/kodoku/llm/base.py backend/kodoku/llm/litellm_client.py backend/kodoku/llm/fake.py backend/tests/test_llm_cost.py
git commit -m "feat(cost): accrue per-client LLM cost via completion_cost

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Session cost column + budget hard-stop + events

**Files:**
- Modify: `backend/kodoku/db/models.py` (`Session`)
- Create: `backend/alembic/versions/20260624_0000_<rev>_session_cost_usd.py`
- Modify: `backend/kodoku/engine/events.py`
- Modify: `backend/kodoku/api/dtos.py` (`SessionConfig`, `SessionResponse`)
- Modify: `backend/kodoku/engine/state_machine.py`
- Test: `backend/tests/test_engine.py`
- Regen: `frontend/lib/types/contracts.ts`

**Interfaces:**
- Consumes: `LLMClient.cost_usd` (Task 1); `self.clients.{expand,evaluate,synthesize}`; existing `_paused` stop pattern; `SessionStatus.PAUSED`.
- Produces: `Session.cost_usd: Mapped[float]`; `SessionConfig.budget_usd: float | None`; `SessionResponse.cost_usd: float`; events `COST_UPDATED = "cost.updated"` and `BUDGET_EXCEEDED = "budget.exceeded"`, both payload `{cost_usd: float, budget_usd: float | None}`.

- [ ] **Step 1: Add the column**

In `backend/kodoku/db/models.py`, in `class Session`, after the `config` column, add:

```python
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=0, server_default="0"
    )
```

(`Decimal`, `Numeric` are already imported.)

- [ ] **Step 2: Add the config + response fields**

In `backend/kodoku/api/dtos.py`:

1. In `SessionConfig`, after `decide_mode`, add:

```python
    budget_usd: float | None = Field(default=None, ge=0)
```

2. In `SessionResponse`, after `final_synthesis: str | None`, add:

```python
    cost_usd: float
```

(`SessionResponse` is a `_ORM` model, so it reads `cost_usd` off the ORM row; SQLAlchemy returns `Decimal`, which pydantic coerces to `float`.)

- [ ] **Step 3: Add the event constants**

In `backend/kodoku/engine/events.py`, after `DECIDE_COMPLETED`, add:

```python
COST_UPDATED = "cost.updated"
BUDGET_EXCEEDED = "budget.exceeded"
```

Update the module's name-count comment (currently "the twelve names") to "the fourteen names".

- [ ] **Step 4: Write the failing engine tests**

In `backend/tests/test_engine.py`, add the new event imports to the existing `from kodoku.engine.events import (...)` block: `COST_UPDATED`, `BUDGET_EXCEEDED`. Then add these tests (reuse `_make_session`, `_roles`, `_Recorder`, `_expand`, `_eval`, `FakeLLMClient`, `select`, `Node`, `NodeStatus`, `SessionStatus`). Note the `_roles` helper wraps ONE shared `FakeLLMClient` across roles — so `cost_per_call` must be set on that shared client; the engine sums the same client three times (expand+evaluate+synthesize all point at it), which is fine for asserting "cost accrued and emitted".

```python
async def test_cost_updated_emitted_per_branch(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, branching_factor=2, max_depth=1)
    rec = _Recorder()
    llm = FakeLLMClient(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(8.0)),
                     json.dumps(_eval(3.0))],
        chunks=["done"],
        cost_per_call=0.01,
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    assert rec.count(COST_UPDATED) >= 1
    payload = next(p for t, p in rec.events if t == COST_UPDATED)
    assert payload["cost_usd"] > 0.0
    assert payload["budget_usd"] is None
    assert float(session.cost_usd) > 0.0


async def test_budget_exceeded_stops_before_synthesis(db_session: AsyncSession) -> None:
    # branching_factor=2, max_depth=2 so there is a second branch the stop prevents.
    session = await _make_session(db_session, branching_factor=2, max_depth=2)
    session.config["budget_usd"] = 0.001  # tiny: first branch's calls blow it
    rec = _Recorder()
    llm = FakeLLMClient(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(8.0)),
                     json.dumps(_eval(3.0)),
                     json.dumps(_expand("C", "D")), json.dumps(_eval(7.0)),
                     json.dumps(_eval(2.0))],
        chunks=["done"],
        cost_per_call=0.01,
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    assert rec.count(BUDGET_EXCEEDED) == 1
    assert session.status == SessionStatus.PAUSED.value
    # Synthesis never ran: no synthesis node, no SESSION_DONE.
    assert rec.count("session.done") == 0


async def test_no_budget_runs_to_completion(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, branching_factor=2, max_depth=1)
    # default budget_usd is None
    rec = _Recorder()
    llm = FakeLLMClient(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(8.0)),
                     json.dumps(_eval(3.0))],
        chunks=["done"],
        cost_per_call=0.01,
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    assert rec.count(BUDGET_EXCEEDED) == 0
    assert session.status == SessionStatus.DONE.value


async def test_cost_base_seeds_from_existing(db_session: AsyncSession) -> None:
    from decimal import Decimal
    session = await _make_session(db_session, branching_factor=2, max_depth=1)
    session.cost_usd = Decimal("0.50")  # prior spend from an earlier run segment
    await db_session.flush()
    rec = _Recorder()
    llm = FakeLLMClient(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(8.0)),
                     json.dumps(_eval(3.0))],
        chunks=["done"],
        cost_per_call=0.01,
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    # New cost adds on top of the 0.50 base, never resets below it.
    assert float(session.cost_usd) > 0.50
```

- [ ] **Step 5: Run the tests, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_engine.py -k "cost or budget" -v`
Expected: FAIL — `COST_UPDATED`/`BUDGET_EXCEEDED` import error and no cost emission.

- [ ] **Step 6: Wire the engine**

In `backend/kodoku/engine/state_machine.py`:

1. Add the event imports to the existing `from kodoku.engine.events import (...)` block: `BUDGET_EXCEEDED`, `COST_UPDATED` (keep alphabetical for ruff `I`).

2. In `__init__`, after `self._paused = False`, add:

```python
        self._budget_exceeded = False
        self._cost_base = float(session.cost_usd or 0)
```

3. In `_run`, change the BFS loop condition to also stop on budget:

```python
        while (
            self._frontier
            and not self.should_stop()
            and not self._paused
            and not self._budget_exceeded
        ):
            await self._expand_one(self._frontier.popleft())
            await self._update_cost_and_check_budget()
```

4. After the loop, before the `if self._paused:` block, add the budget-stop handling:

```python
        # Budget hit — stop before synthesis, mirroring the _paused path.
        if self._budget_exceeded:
            self.session.status = SessionStatus.PAUSED.value
            self.session.current_step = None
            await self.db.flush()
            return
```

5. Add the helper method (place it after `_expand_one`):

```python
    async def _update_cost_and_check_budget(self) -> None:
        """Sum per-role client cost onto the session and stop if over budget.

        ponytail: synthesis runs after the BFS loop, so its streaming cost is
        added to the total afterward but is not budget-gated. Acceptable: one
        cheap call, and the human is already reviewing a stopped run.
        """
        from decimal import Decimal

        total = (
            self.clients.expand.cost_usd
            + self.clients.evaluate.cost_usd
            + self.clients.synthesize.cost_usd
        )
        self.session.cost_usd = Decimal(str(self._cost_base + total))
        await self.db.flush()
        budget = self.config.budget_usd
        await self.emit(
            COST_UPDATED,
            {"cost_usd": float(self.session.cost_usd), "budget_usd": budget},
        )
        if budget is not None and float(self.session.cost_usd) >= budget:
            self._budget_exceeded = True
            await self.emit(
                BUDGET_EXCEEDED,
                {"cost_usd": float(self.session.cost_usd), "budget_usd": budget},
            )
```

(`Decimal` import is local to the helper to avoid touching the module import block; if the file already imports `Decimal` at top, use that instead and drop the local import.)

- [ ] **Step 7: Run the new tests + full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_engine.py -k "cost or budget" -v`
Expected: PASS.
Run: `backend/.venv/Scripts/python.exe -m pytest`
Expected: full suite green (existing autopilot/HITL tests unchanged = `budget_usd=None` path regression-free).

- [ ] **Step 8: Write the migration**

Create `backend/alembic/versions/20260624_0000_session_cost_usd.py` (mirror the `app_settings` migration's structure; set `down_revision` to the current head `89a17aa10606`):

```python
"""session cost_usd

Revision ID: a1b2c3d4e5f6
Revises: 89a17aa10606
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '89a17aa10606'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('cost_usd', sa.Numeric(12, 6), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('sessions', 'cost_usd')
```

Verify the chain is linear:
Run: `backend/.venv/Scripts/python.exe -m alembic heads`
Expected: single head `a1b2c3d4e5f6`.

- [ ] **Step 9: Lint + type-check**

Run: `backend/.venv/Scripts/python.exe -m ruff check kodoku tests` then `backend/.venv/Scripts/python.exe -m mypy kodoku`
Expected: both clean.

- [ ] **Step 10: Regenerate contracts**

Run (from `frontend/`): `npm run gen:contracts`
Expected: `lib/types/contracts.ts` now lists `budget_usd` on `SessionConfig` and `cost_usd` on `SessionResponse` (minimal additive diff).

- [ ] **Step 11: Commit**

```bash
git add backend/kodoku/db/models.py backend/kodoku/api/dtos.py backend/kodoku/engine/events.py backend/kodoku/engine/state_machine.py backend/tests/test_engine.py backend/alembic/versions/20260624_0000_session_cost_usd.py frontend/lib/types/contracts.ts
git commit -m "feat(cost): session cost_usd + budget hard-stop + cost/budget events

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Frontend live cost + budget banner + budget input

**Files:**
- Modify: `frontend/lib/ws/types.ts`
- Modify: `frontend/lib/ws/reducer.ts`
- Modify: `frontend/app/s/[sessionId]/SessionGraphView.tsx`
- Modify: `frontend/app/_components/NewSessionDialog.tsx`

**Interfaces:**
- Consumes: events `cost.updated` / `budget.exceeded` with `{cost_usd, budget_usd}` (Task 2); `SessionConfig.budget_usd` from `contracts.ts` (Task 2).

- [ ] **Step 1: Extend graph state**

In `frontend/lib/ws/types.ts`:

1. In `type GraphState`, after `checkpoint: Checkpoint | null;`, add:

```typescript
  costUsd: number;
  budgetUsd: number | null;
  budgetExceeded: boolean;
```

2. In `emptyGraph()`, after `checkpoint: null,`, add:

```typescript
    costUsd: 0,
    budgetUsd: null,
    budgetExceeded: false,
```

- [ ] **Step 2: Handle the events in the reducer**

In `frontend/lib/ws/reducer.ts`, add two cases before `default:`:

```typescript
    case "cost.updated": {
      const { cost_usd, budget_usd } = event.payload as unknown as {
        cost_usd: number;
        budget_usd: number | null;
      };
      next = { ...state, costUsd: cost_usd, budgetUsd: budget_usd };
      break;
    }
    case "budget.exceeded": {
      const { cost_usd } = event.payload as unknown as { cost_usd: number };
      next = { ...state, status: "paused", costUsd: cost_usd, budgetExceeded: true };
      break;
    }
```

- [ ] **Step 3: Show live cost + budget banner**

In `frontend/app/s/[sessionId]/SessionGraphView.tsx`:

1. Add store selectors near the existing ones (after the `checkpoint` selector, ~line 67):

```tsx
  const costUsd = useSessionStore((s) => s.graph.costUsd);
  const budgetExceeded = useSessionStore((s) => s.graph.budgetExceeded);
```

2. In the header bar (after the `● live / ○ disconnected` span, ~line 141), add a cost badge:

```tsx
        <span className="text-xs text-muted-foreground tabular-nums">
          ${costUsd.toFixed(4)}
        </span>
```

3. In the resume banner block (`{showResumeBanner && ( ... )}`, ~line 166), prepend a budget note when `budgetExceeded` is true. Inside that banner's content, add at the top:

```tsx
            {budgetExceeded && (
              <span className="font-medium">Budget exceeded — run stopped. </span>
            )}
```

(Place it as the first child of the banner's text container so it reads before the existing paused/error copy. Match the surrounding markup; do not restructure the banner.)

- [ ] **Step 4: Add the budget input**

In `frontend/app/_components/NewSessionDialog.tsx`:

1. Add state near `decideMode` (~line 50):

```tsx
const [budget, setBudget] = useState<string>("");
```

2. Reset it in the reset block (alongside `setDecideMode("threshold");`):

```tsx
    setBudget("");
```

3. In the `createSession({ ..., config: { ... } })` call, after `decide_mode: decideMode,`, add:

```tsx
          budget_usd: budget.trim() === "" ? null : Number(budget),
```

4. Add an input field in the form, after the decide-mode toggle block, mirroring the surrounding `<div className="space-y-2"> <Label> ... </Label> ... </div>` pattern used by other fields:

```tsx
          <div className="space-y-2">
            <Label htmlFor="budget">Budget (USD, optional)</Label>
            <input
              id="budget"
              type="number"
              min="0"
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              placeholder="No cap"
              className="w-full rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Stops the run when the session cost passes this amount.
            </p>
          </div>
```

(If the form already uses a shared `Input` component instead of a bare `<input>`, use that component with the same props — read the file's other fields and match them.)

- [ ] **Step 5: Type-check + lint**

Run (from `frontend/`): `npm run typecheck` then `npm run lint`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/ws/types.ts frontend/lib/ws/reducer.ts frontend/app/s/[sessionId]/SessionGraphView.tsx frontend/app/_components/NewSessionDialog.tsx
git commit -m "feat(cost): live cost badge, budget banner, and budget input

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (later)
Per-role / per-node cost breakdown; budget-gating the synthesis call; a global default budget setting; persisting per-call cost rows; cost-on-reload via `SessionResponse.cost_usd` is exposed but wiring the page's server component to seed `costUsd` from it is optional polish (the WS `cost.updated` event repopulates it live).
