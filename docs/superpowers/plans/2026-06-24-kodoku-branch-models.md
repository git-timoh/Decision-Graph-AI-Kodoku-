# Per-Branch Expand-Model Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user optionally assign a different expand model to each top-level branch at session creation, and tag every node with its branch's model.

**Architecture:** `SessionConfig.branch_models` (optional list, slot i → root's i-th candidate branch) is validated against `branching_factor`. A new `Node.model` column tags each node with its branch's expand model (root's children by slot, deeper nodes inherit the parent's tag). At run start `run.py` builds an `expand_overrides` map (model string → client) via a new `build_client_for_model` factory helper and threads it into the engine, which picks `expand_overrides.get(parent.model)` (falling back to the default expand client) when expanding. Evaluate/synthesize are untouched.

**Tech Stack:** Python 3.12, SQLAlchemy async, alembic, pydantic, pytest; Next.js 14 + TS strict. Spec: `docs/superpowers/specs/2026-06-24-kodoku-branch-models-design.md`.

## Global Constraints

- Python 3.12, `from __future__ import annotations`. mypy `strict = true` zero errors; ruff line-length 100 rules `E,F,I,B,UP,W` zero errors. Match existing style.
- Engine STAYS flush-only; the only `commit()` is the `/run`//`/resume` boundary.
- Never hit a real provider in tests — use `FakeLLMClient` only.
- venv: `backend/.venv/Scripts/python.exe -m pytest|mypy|ruff` (run from `backend/`).
- Frontend: TS strict (no `any`), `npm run typecheck` + `npm run lint` clean; regenerate `frontend/lib/types/contracts.ts` after the dtos change (`npm run gen:contracts` from `frontend/`).
- `branch_models=None` (default) → engine behavior byte-for-byte unchanged except `node.created` carrying the additive `model` field. The existing engine suite covers the regression.
- Tests build schema via `Base.metadata.create_all` (tests/conftest.py:81), so the new column appears automatically in tests; the alembic migration is for real DBs.

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `backend/kodoku/api/dtos.py` (modify) | `SessionConfig.branch_models` + validation | 1 |
| `backend/kodoku/db/models.py` (modify) | `Node.model` column | 1 |
| `backend/alembic/versions/*_node_model.py` (create) | Additive migration | 1 |
| `backend/kodoku/llm/factory.py` (modify) | Extract `build_client_for_model` | 1 |
| `backend/tests/test_dtos.py` (modify) | branch_models validation tests | 1 |
| `backend/tests/test_factory.py` (create) | `build_client_for_model` test | 1 |
| `backend/kodoku/engine/state_machine.py` (modify) | `expand_overrides`, branch expand lookup, `child.model`, payload | 2 |
| `backend/kodoku/api/run.py` (modify) | Build `expand_overrides`, thread into engine | 2 |
| `backend/tests/test_engine.py` (modify) | branch-model engine tests | 2 |
| `frontend/lib/types/contracts.ts` (regen) | Reflect dtos change | 2 |
| `frontend/lib/ws/types.ts` (modify) | `model` on `GraphNode` | 3 |
| `frontend/app/s/[sessionId]/_components/NodeDrawer.tsx` (modify) | Show model tag | 3 |
| `frontend/app/_components/NewSessionDialog.tsx` (modify) | Per-branch model selects | 3 |

## Dependencies / order
1 → 2 (engine consumes the config field, the column, and the factory helper). 3 depends on 2's contracts regen. Order: 1, 2, 3.

---

### Task 1: Config + Node.model column + migration + factory helper

**Files:**
- Modify: `backend/kodoku/api/dtos.py` (`SessionConfig`)
- Modify: `backend/kodoku/db/models.py` (`Node`)
- Create: `backend/alembic/versions/20260624_0100_node_model.py`
- Modify: `backend/kodoku/llm/factory.py`
- Test: `backend/tests/test_dtos.py`, `backend/tests/test_factory.py` (create)

**Interfaces:**
- Produces (Task 2 relies on these):
  - `SessionConfig.branch_models: list[str] | None = None` — optional, slot i → root's i-th branch; entries are `""` (default) or valid LiteLLM model ids; `len <= branching_factor`.
  - `Node.model: Mapped[str | None]` — nullable column, the branch's expand model.
  - `build_client_for_model(model: str, settings: dict[str, str]) -> LLMClient` in `kodoku.llm.factory`.

- [ ] **Step 1: Write the failing config tests**

In `backend/tests/test_dtos.py`, add (the file already imports `SessionConfig` and `pytest`; if not, add `from kodoku.api.dtos import SessionConfig` and `import pytest`):

```python
def test_branch_models_defaults_none() -> None:
    assert SessionConfig().branch_models is None


def test_branch_models_valid_list() -> None:
    cfg = SessionConfig(branching_factor=3, branch_models=["deepseek/deepseek-chat", "", "openai/gpt-4o"])
    assert cfg.branch_models == ["deepseek/deepseek-chat", "", "openai/gpt-4o"]


def test_branch_models_too_many_rejected() -> None:
    with pytest.raises(ValueError, match="branch_models"):
        SessionConfig(branching_factor=1, branch_models=["a/b", "c/d"])


def test_branch_models_bad_id_rejected() -> None:
    with pytest.raises(ValueError, match="branch_models"):
        SessionConfig(branching_factor=2, branch_models=["not a model"])
```

- [ ] **Step 2: Run the config tests, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_dtos.py -k branch_models -v`
Expected: FAIL — `branch_models` is not a field (extra="forbid" rejects it).

- [ ] **Step 3: Add the config field + validator**

In `backend/kodoku/api/dtos.py`:

1. Change the pydantic import to add `model_validator`:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
```

2. In `SessionConfig`, after `budget_usd`, add the field:

```python
    branch_models: list[str] | None = Field(default=None)
```

3. After the existing `_validate_model` field_validator, add:

```python
    @model_validator(mode="after")
    def _validate_branch_models(self) -> "SessionConfig":
        if self.branch_models is None:
            return self
        if len(self.branch_models) > self.branching_factor:
            raise ValueError("branch_models cannot have more entries than branching_factor")
        for entry in self.branch_models:
            if entry == "":
                continue
            if " " in entry or not _MODEL_RE.match(entry):
                raise ValueError(
                    f"branch_models entry {entry!r} must be a LiteLLM-style identifier or ''"
                )
        return self
```

- [ ] **Step 4: Run the config tests, verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_dtos.py -k branch_models -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Add the Node column**

In `backend/kodoku/db/models.py`, in `class Node`, after the `status` column (line ~97), add:

```python
    model: Mapped[str | None] = mapped_column(String, nullable=True)
```

(`String`, `Mapped`, `mapped_column` already imported.)

- [ ] **Step 6: Write the migration**

Create `backend/alembic/versions/20260624_0100_node_model.py`:

```python
"""node model tag

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-24 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('nodes', sa.Column('model', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('nodes', 'model')
```

Run: `backend/.venv/Scripts/python.exe -m alembic heads`
Expected: single head `b2c3d4e5f6a7`.

- [ ] **Step 7: Write the failing factory test**

Create `backend/tests/test_factory.py`:

```python
"""build_client_for_model resolves a model + BYOK key into a client. No live calls."""
from __future__ import annotations

from kodoku.llm.factory import build_client_for_model
from kodoku.llm.litellm_client import LiteLLMClient


def test_build_client_for_model_resolves_key() -> None:
    client = build_client_for_model("deepseek/deepseek-chat", {"key.deepseek": "sk-test"})
    assert isinstance(client, LiteLLMClient)
    assert client.model == "deepseek/deepseek-chat"
    assert client.api_key == "sk-test"


def test_build_client_for_model_ollama_uses_base_url() -> None:
    client = build_client_for_model("ollama/llama3", {"ollama.base_url": "http://localhost:11434"})
    assert isinstance(client, LiteLLMClient)
    assert client.api_base == "http://localhost:11434"
    assert client.api_key is None
```

- [ ] **Step 8: Run the factory test, verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_factory.py -v`
Expected: FAIL — `cannot import name 'build_client_for_model'`.

- [ ] **Step 9: Extract `build_client_for_model`**

In `backend/kodoku/llm/factory.py`, replace the existing `_build_client` function with the extracted pair (keep everything else unchanged):

```python
def build_client_for_model(model: str, settings: dict[str, str]) -> LLMClient:
    """Build one `LLMClient` for an arbitrary model string, resolving its BYOK key."""
    from kodoku.llm.litellm_client import LiteLLMClient

    provider = provider_of(model)
    if provider == _OLLAMA_PROVIDER:
        api_key: str | None = None
        api_base = settings.get(_OLLAMA_BASE_URL_KEY) or None
    else:
        api_key = _resolve_api_key(provider, settings)
        api_base = None

    return LiteLLMClient(model=model, api_key=api_key, api_base=api_base)


def _build_client(role: str, settings: dict[str, str]) -> LLMClient:
    model = settings.get(f"model.{role}") or DEFAULT_MODELS[role]
    return build_client_for_model(model, settings)
```

- [ ] **Step 10: Run the factory + full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_factory.py -v`
Expected: PASS (2 passed).
Run: `backend/.venv/Scripts/python.exe -m pytest`
Expected: full suite green (the `_build_client` refactor is behavior-preserving).

- [ ] **Step 11: Lint + type-check**

Run: `backend/.venv/Scripts/python.exe -m ruff check kodoku tests` then `backend/.venv/Scripts/python.exe -m mypy kodoku`
Expected: both clean.

- [ ] **Step 12: Commit**

```bash
git add backend/kodoku/api/dtos.py backend/kodoku/db/models.py backend/alembic/versions/20260624_0100_node_model.py backend/kodoku/llm/factory.py backend/tests/test_dtos.py backend/tests/test_factory.py
git commit -m "feat(branch-models): config field, Node.model column, client-by-model factory

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Engine wiring + run.py overrides

**Files:**
- Modify: `backend/kodoku/engine/state_machine.py`
- Modify: `backend/kodoku/api/run.py` (`_run_engine`)
- Test: `backend/tests/test_engine.py`
- Regen: `frontend/lib/types/contracts.ts`

**Interfaces:**
- Consumes: `SessionConfig.branch_models`, `Node.model`, `build_client_for_model` (Task 1); existing `expand`, `RoleClients`, `LLMClient`.
- Produces: `DecisionEngine(..., expand_overrides: dict[str, LLMClient] | None = None)`; `node.created` payload gains `"model"`.

- [ ] **Step 1: Write the failing engine tests**

In `backend/tests/test_engine.py`, add (reuse `_make_session`, `_roles`, `_Recorder`, `_expand`, `_eval`, `FakeLLMClient`, `select`, `Node`, `NodeStatus`, `NodeKind`, `NODE_CREATED`; add `NODE_CREATED` to the events import if absent):

```python
async def test_branch_override_expands_via_override_client_and_tags(
    db_session: AsyncSession,
) -> None:
    # branching_factor=1, max_depth=2: root -> A (slot 0 -> override model),
    # A expands (depth 1 < 2) via the override client into A2.
    session = await _make_session(db_session, branching_factor=1, max_depth=2)
    session.config["branch_models"] = ["override/model"]
    rec = _Recorder()
    # Default client: root expand (A), eval A, eval A2. A's expansion is the
    # override client's job, so it is NOT in this FIFO.
    default = FakeLLMClient(
        completions=[json.dumps(_expand("A")), json.dumps(_eval(8.0)), json.dumps(_eval(8.0))],
        chunks=["done"],
    )
    override = FakeLLMClient(completions=[json.dumps(_expand("A2"))])
    engine = DecisionEngine(
        db_session, session, _roles(default), rec,
        expand_overrides={"override/model": override},
    )
    await engine.run()

    nodes = (await db_session.execute(
        select(Node).where(Node.session_id == session.id,
                            Node.kind == NodeKind.CANDIDATE.value))).scalars().all()
    by_title = {n.title: n for n in nodes}
    assert by_title["A"].model == "override/model"      # slot 0
    assert by_title["A2"].model == "override/model"     # inherited from A
    assert len(override.calls) == 1                      # the override expanded A
    # node.created for A carries the model tag.
    a_created = next(p for t, p in rec.events
                     if t == NODE_CREATED and p["title"] == "A")
    assert a_created["model"] == "override/model"


async def test_empty_slot_falls_back_to_default(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, branching_factor=1, max_depth=2)
    session.config["branch_models"] = [""]  # slot 0 explicitly default
    rec = _Recorder()
    default = FakeLLMClient(
        completions=[json.dumps(_expand("A")), json.dumps(_eval(8.0)),
                     json.dumps(_expand("A2")), json.dumps(_eval(8.0))],
        chunks=["done"],
    )
    override = FakeLLMClient(completions=[json.dumps(_expand("NEVER"))])
    engine = DecisionEngine(
        db_session, session, _roles(default), rec,
        expand_overrides={"override/model": override},
    )
    await engine.run()

    nodes = (await db_session.execute(
        select(Node).where(Node.session_id == session.id,
                            Node.kind == NodeKind.CANDIDATE.value))).scalars().all()
    assert all(n.model is None for n in nodes)
    assert len(override.calls) == 0  # override never used


async def test_no_branch_models_tags_none(db_session: AsyncSession) -> None:
    session = await _make_session(db_session, branching_factor=2, max_depth=1)
    # default config: branch_models is None
    rec = _Recorder()
    llm = FakeLLMClient(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(8.0)),
                     json.dumps(_eval(3.0))],
        chunks=["done"],
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    a_created = next(p for t, p in rec.events
                     if t == NODE_CREATED and p["title"] == "A")
    assert a_created["model"] is None
```

- [ ] **Step 2: Run the engine tests, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_engine.py -k "branch_override or empty_slot or no_branch_models" -v`
Expected: FAIL — `DecisionEngine` has no `expand_overrides` kwarg / `node.created` has no `model`.

- [ ] **Step 3: Wire the engine**

In `backend/kodoku/engine/state_machine.py`:

1. Add the `LLMClient` import near the other LLM/factory imports (after the `RoleClients` import):

```python
from kodoku.llm.base import LLMClient
```

2. Add a module-level helper after the imports (before the class):

```python
def _slot_model(branch_models: list[str] | None, index: int) -> str | None:
    """The expand model for branch slot `index`, or None for default/out-of-range."""
    if branch_models is None or index >= len(branch_models):
        return None
    return branch_models[index] or None
```

3. In `DecisionEngine.__init__`, add the parameter (after `should_stop`) and store it. Change the signature's keyword-only section to include:

```python
        should_stop: Callable[[], bool] = lambda: False,
        expand_overrides: dict[str, LLMClient] | None = None,
    ) -> None:
```

and in the body, after `self._cost_base = float(session.cost_usd or 0)`:

```python
        self._expand_overrides = expand_overrides or {}
```

4. In `_expand_one`, replace the `cands = await expand(self.clients.expand, ...)` call with an override-aware client pick:

```python
        override = self._expand_overrides.get(parent.model) if parent.model else None
        expand_client = override or self.clients.expand
        cands = await expand(
            expand_client,
            goal=self.session.goal,
            parent_title=parent.title,
            parent_content=parent.content,
            branching_factor=self.config.branching_factor,
        )
```

5. In the child-creation loop, set `child.model`. Replace the `for cand in cands:` loop header and `Node(...)` construction with:

```python
        children: list[Node] = []
        for index, cand in enumerate(cands):
            if parent.parent_id is None:
                child_model = _slot_model(self.config.branch_models, index)
            else:
                child_model = parent.model
            child = Node(
                session_id=self.session.id,
                parent_id=parent.id,
                depth=parent.depth + 1,
                kind=NodeKind.CANDIDATE.value,
                title=cand.title,
                content=cand.content,
                status=NodeStatus.ACTIVE.value,
                model=child_model,
            )
            self.db.add(child)
            children.append(child)
        await self.db.flush()
```

6. In the `NODE_CREATED` emit payload, add the model field (after `"status": child.status,`):

```python
                    "model": child.model,
```

- [ ] **Step 4: Run the engine tests, verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_engine.py -k "branch_override or empty_slot or no_branch_models" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Thread overrides through run.py**

In `backend/kodoku/api/run.py`:

1. Add imports (near the existing dtos/factory imports):

```python
from kodoku.api.dtos import SessionConfig
from kodoku.llm.base import LLMClient
from kodoku.llm.factory import RoleClients, build_client_for_model, make_role_clients
```

(Merge `build_client_for_model` into the existing `from kodoku.llm.factory import ...` line rather than duplicating it.)

2. In `_run_engine`, replace the engine construction block with one that builds the override map:

```python
async def _run_engine(session_id: UUID, build_clients: RoleClientsBuilder) -> None:
    """Run the engine on a fresh session; commit once, always, on exit."""
    async with get_sessionmaker()() as s:
        session = await SessionRepository(s).get(session_id)
        clients = await build_clients(s)
        cfg = SessionConfig(**session.config)
        expand_overrides: dict[str, LLMClient] = {}
        if cfg.branch_models:
            raw = await SettingsRepository(s).get_all()
            expand_overrides = {
                m: build_client_for_model(m, raw) for m in set(cfg.branch_models) if m
            }
        engine = DecisionEngine(
            s,
            session,
            clients,
            make_db_emitter(s, session_id),
            should_stop=lambda: runner.should_stop(session_id),
            expand_overrides=expand_overrides,
        )
        try:
            await engine.run()
        finally:
            await s.commit()
```

(`/resume` already re-runs the engine through `_run_engine`, so branch overrides apply on resume too — no separate change needed.)

- [ ] **Step 6: Run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest`
Expected: full suite green (existing tests unchanged = the `branch_models=None` path is byte-for-byte except the additive `node.created` `model` field).

- [ ] **Step 7: Lint + type-check**

Run: `backend/.venv/Scripts/python.exe -m ruff check kodoku tests` then `backend/.venv/Scripts/python.exe -m mypy kodoku`
Expected: both clean.

- [ ] **Step 8: Regenerate contracts**

Run (from `frontend/`): `npm run gen:contracts`
Expected: `lib/types/contracts.ts` now lists `branch_models` on `SessionConfig` and `model` on the node type (additive diff).

- [ ] **Step 9: Commit**

```bash
git add backend/kodoku/engine/state_machine.py backend/kodoku/api/run.py backend/tests/test_engine.py frontend/lib/types/contracts.ts
git commit -m "feat(branch-models): per-branch expand override in engine + run wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Frontend per-branch selects + node model tag

**Files:**
- Modify: `frontend/lib/ws/types.ts`
- Modify: `frontend/app/s/[sessionId]/_components/NodeDrawer.tsx`
- Modify: `frontend/app/_components/NewSessionDialog.tsx`

**Interfaces:**
- Consumes: `SessionConfig.branch_models` and the node `model` field from `contracts.ts` (Task 2); `MODEL_PRESETS` already defined in NewSessionDialog.

- [ ] **Step 1: Add `model` to GraphNode**

In `frontend/lib/ws/types.ts`, in `type GraphNode`, after `dimensions?: Record<string, number>;`, add:

```typescript
  model?: string | null;
```

(The `node.created` reducer case already spreads the payload into the node, so `model` flows in with no reducer change.)

- [ ] **Step 2: Show the model tag in NodeDrawer**

In `frontend/app/s/[sessionId]/_components/NodeDrawer.tsx`, find where node fields (e.g. score/status) are rendered and add a conditional model line. Read the file's existing field rows and mirror one; add:

```tsx
        {node.model && (
          <div className="text-xs text-muted-foreground">Model: {node.model}</div>
        )}
```

(Place it alongside the other node metadata rows; match the surrounding markup. If the drawer reads the node from a store selector, use the same node object.)

- [ ] **Step 3: Add per-branch model selects to the dialog**

In `frontend/app/_components/NewSessionDialog.tsx`:

1. Add state near the existing `branchingFactor` / `decideMode` state:

```tsx
const [branchModels, setBranchModels] = useState<string[]>([]);
```

2. Reset it in the reset block (alongside the other resets):

```tsx
    setBranchModels([]);
```

3. In the `createSession({ ..., config: { ... } })` call, after `branching_factor: ...`, add (send `null` when every slot is empty):

```tsx
          branch_models: branchModels.some((m) => m !== "") ? branchModels : null,
```

4. Render one optional model `<select>` per branch slot, driven by the chosen branching factor. After the branching-factor control, add a block that maps over `branchingFactor` slots (read the existing branching-factor state variable name and the `MODEL_PRESETS` array shape from this file, and mirror the model-select markup the `model` field already uses):

```tsx
          <div className="space-y-2">
            <Label>Per-branch models (optional)</Label>
            {Array.from({ length: branchingFactor }).map((_, i) => (
              <select
                key={i}
                value={branchModels[i] ?? ""}
                onChange={(e) => {
                  const next = [...branchModels];
                  next[i] = e.target.value;
                  setBranchModels(next);
                }}
                className="w-full rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
              >
                <option value="">{`Branch ${i + 1}: session default`}</option>
                {MODEL_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
            ))}
          </div>
```

(If the file uses a shared `<Select>` component for the model field rather than a bare `<select>`, mirror that component instead, with the same options. Use the actual branching-factor state variable name from the file — `branchingFactor` here is illustrative.)

- [ ] **Step 4: Type-check + lint**

Run (from `frontend/`): `npm run typecheck` then `npm run lint`
Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/ws/types.ts frontend/app/s/[sessionId]/_components/NodeDrawer.tsx frontend/app/_components/NewSessionDialog.tsx
git commit -m "feat(branch-models): per-branch model selects + node model tag

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (later)
Per-branch evaluate/synthesize models; reassigning a branch's model mid-run or at a checkpoint; auto-cycling models across branches.
