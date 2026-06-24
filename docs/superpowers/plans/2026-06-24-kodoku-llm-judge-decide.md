# LLM-as-judge `decide` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in LLM judge that comparatively selects keep/prune across a parent's sibling candidates, with the deterministic threshold `decide` as the guaranteed fallback.

**Architecture:** New pure step `engine/steps/judge.py` exposing `decide_with_judge(...)` (tries the LLM judge, falls back to `decide()` on any failure). `SessionConfig.decide_mode` selects threshold (default) vs judge in `_expand_one`; the chosen `Decision` flows through the existing keep/prune marking and the M5 checkpoint proposal unchanged. A new `decide.completed` event carries the judge rationale. One frontend toggle exposes the config.

**Tech Stack:** Python 3.12, SQLAlchemy async, pydantic, pytest; Next.js 14 + TS strict frontend. Spec: `docs/superpowers/specs/2026-06-24-kodoku-llm-judge-decide-design.md`.

## Global Constraints

- Python 3.12, `from __future__ import annotations`. mypy `strict = true` zero errors; ruff line-length 100 rules `E,F,I,B,UP,W` zero errors. Match existing style.
- Engine STAYS flush-only; the only `commit()` is the `/run`/`/resume` boundary.
- Reuse `parse_json`, the step/prompt pattern (`Template(...).safe_substitute`), `make_db_emitter`, and the `RoleClientsBuilder` test seam. Never hit a real provider in tests.
- venv: `backend/.venv/Scripts/python.exe -m pytest|mypy|ruff`.
- Frontend: TS strict (no `any`), `npm run typecheck` + `npm run lint` clean; regenerate `frontend/lib/types/contracts.ts` after the `SessionConfig` change (`npm run gen:contracts` from `frontend/`).
- `threshold` (default) behavior must be byte-for-byte unchanged — the existing engine suite covers it.

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `backend/kodoku/engine/steps/judge.py` (create) | `JudgeCandidate`, `JudgeOutcome`, `judge_decide`, `decide_with_judge` — pure judge + total fallback to `decide()` | 1 |
| `backend/kodoku/engine/prompts/judge.md` (create) | Judge prompt template | 1 |
| `backend/tests/test_judge.py` (create) | Judge step + fallback unit tests | 1 |
| `backend/kodoku/api/dtos.py` (modify) | `SessionConfig.decide_mode` field | 2 |
| `backend/kodoku/engine/events.py` (modify) | `DECIDE_COMPLETED` constant | 2 |
| `backend/kodoku/engine/state_machine.py` (modify) | Branch threshold/judge in `_expand_one`; emit `decide.completed` | 2 |
| `backend/tests/test_engine.py` (modify) | judge-mode + threshold-regression engine tests | 2 |
| `frontend/app/_components/NewSessionDialog.tsx` (modify) | `decide_mode` segmented toggle | 3 |
| `frontend/lib/types/contracts.ts` (regen) | Reflect `decide_mode` | 3 |

## Dependencies / order
1 → 2 (engine consumes the judge step + config). 3 depends on 2's `SessionConfig` change. Order: 1, 2, 3.

---

### Task 1: Judge step + prompt (pure, with total fallback)

**Files:**
- Create: `backend/kodoku/engine/steps/judge.py`
- Create: `backend/kodoku/engine/prompts/judge.md`
- Test: `backend/tests/test_judge.py`

**Interfaces:**
- Consumes: `kodoku.engine.steps.decide.Decision` and `decide`; `kodoku.engine.steps.parse.parse_json`, `StepError`; `kodoku.llm.base.LLMClient`.
- Produces (later tasks rely on these exact names/types):
  - `JudgeCandidate(id: UUID, title: str, content: str, score: float, critique: str, dimensions: dict[str, float])` (frozen dataclass)
  - `JudgeOutcome(decision: Decision, rationale: str, source: str)` (frozen dataclass; `source` ∈ `{"judge", "threshold_fallback"}`)
  - `async def decide_with_judge(llm: LLMClient, *, goal: str, candidates: list[JudgeCandidate], depth: int, max_depth: int) -> JudgeOutcome`

- [ ] **Step 1: Write the prompt template**

Create `backend/kodoku/engine/prompts/judge.md`:

```markdown
You are selecting which candidate ideas to keep versus prune toward a goal.

Goal: $goal

You are given sibling candidates that were each scored independently. Judge them
COMPARATIVELY: keep the ones most worth expanding toward the goal and prune the
rest. Keeping fewer, stronger candidates is better than keeping everything.

Candidates:
$candidates_block

Return ONLY valid JSON matching this schema, with no other text. Every candidate
id MUST appear in exactly one of "keep" or "prune". Keep at least one.

{"keep": ["<uuid>", ...], "prune": ["<uuid>", ...], "rationale": "one short paragraph comparing them"}
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_judge.py`:

```python
"""Tests for the LLM-judge decide step and its deterministic fallback."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from kodoku.engine.steps.judge import JudgeCandidate, decide_with_judge
from kodoku.llm.fake import FakeLLMClient

pytestmark = pytest.mark.asyncio


def _cands() -> list[JudgeCandidate]:
    return [
        JudgeCandidate(id=uuid4(), title="A", content="A body", score=8.0,
                       critique="strong", dimensions={"impact": 8.0}),
        JudgeCandidate(id=uuid4(), title="B", content="B body", score=3.0,
                       critique="weak", dimensions={"impact": 3.0}),
    ]


async def test_judge_keeps_subset_and_returns_rationale() -> None:
    cands = _cands()
    keep_id, prune_id = cands[0].id, cands[1].id
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(keep_id)], "prune": [str(prune_id)],
                    "rationale": "A beats B"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "judge"
    assert out.decision.keep == [keep_id]
    assert out.decision.prune == [prune_id]
    assert out.decision.expand == [keep_id]  # depth 1 < max_depth 2
    assert out.rationale == "A beats B"


async def test_judge_no_expansion_at_max_depth() -> None:
    cands = _cands()
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(cands[0].id)], "prune": [str(cands[1].id)],
                    "rationale": "x"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=2, max_depth=2)
    assert out.decision.expand == []


async def test_falls_back_when_ids_not_exact_cover() -> None:
    cands = _cands()
    # keep references an id that isn't a candidate; prune omits a real one.
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(uuid4())], "prune": [], "rationale": "bad"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    # threshold floor: A (8.0) >= 6.0 kept, B (3.0) pruned.
    assert out.decision.keep == [cands[0].id]
    assert out.decision.prune == [cands[1].id]
    assert out.rationale == ""


async def test_falls_back_when_keep_empty() -> None:
    cands = _cands()
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [], "prune": [str(cands[0].id), str(cands[1].id)],
                    "rationale": "prune all"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    assert out.decision.keep == [cands[0].id]  # best-of by threshold floor


async def test_falls_back_on_malformed_json() -> None:
    cands = _cands()
    # parse_json retries (retries+1 = 3 calls) then raises StepError -> fallback.
    llm = FakeLLMClient(completions=["not json", "still not", "nope"])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    assert out.decision.keep == [cands[0].id]
```

- [ ] **Step 3: Run the tests, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_judge.py -v` (from `backend/`)
Expected: FAIL — `ModuleNotFoundError: No module named 'kodoku.engine.steps.judge'`.

- [ ] **Step 4: Implement `judge.py`**

Create `backend/kodoku/engine/steps/judge.py`:

```python
"""LLM-judge decide step: comparatively select keep/prune across siblings.

`decide_with_judge` calls the LLM judge and falls back to the deterministic
`decide()` on ANY failure (LLM error, bad JSON, ids not an exact cover of the
candidates, or empty keep), so the threshold floor is always reachable and the
engine never crashes on a bad judge response.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from string import Template
from uuid import UUID

from pydantic import BaseModel

from kodoku.engine.steps.decide import Decision, decide
from kodoku.engine.steps.parse import parse_json
from kodoku.llm.base import LLMClient

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "judge.md"
_SYSTEM = "You are a rigorous strategic planning assistant that replies with strict JSON."


@dataclass(frozen=True, slots=True)
class JudgeCandidate:
    id: UUID
    title: str
    content: str
    score: float
    critique: str
    dimensions: dict[str, float]


@dataclass(frozen=True, slots=True)
class JudgeOutcome:
    decision: Decision
    rationale: str
    source: str  # "judge" | "threshold_fallback"


class _JudgeResult(BaseModel):
    keep: list[UUID]
    prune: list[UUID]
    rationale: str


def _render_candidates(candidates: list[JudgeCandidate]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- id={c.id} | score={c.score} | dimensions={c.dimensions}\n"
            f"  title: {c.title}\n"
            f"  content: {c.content}\n"
            f"  critique: {c.critique}"
        )
    return "\n".join(lines)


async def judge_decide(
    llm: LLMClient,
    *,
    goal: str,
    candidates: list[JudgeCandidate],
    depth: int,
    max_depth: int,
) -> tuple[Decision, str]:
    """Ask the LLM to comparatively keep/prune. Raises on invalid/unusable output."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = Template(template).safe_substitute(
        goal=goal,
        candidates_block=_render_candidates(candidates),
    )
    result = await parse_json(llm, system=_SYSTEM, prompt=prompt, model_cls=_JudgeResult)

    candidate_ids = {c.id for c in candidates}
    keep = [cid for cid in result.keep if cid in candidate_ids]
    keep_set = set(keep)
    submitted = set(result.keep) | set(result.prune)
    if submitted != candidate_ids or not keep:
        raise ValueError("judge result is not an exact, non-empty cover of candidates")

    # Preserve input order; derive prune from the cover so it always matches.
    keep_ordered = [c.id for c in candidates if c.id in keep_set]
    prune_ordered = [c.id for c in candidates if c.id not in keep_set]
    expand = list(keep_ordered) if depth < max_depth else []
    return Decision(keep=keep_ordered, prune=prune_ordered, expand=expand), result.rationale


async def decide_with_judge(
    llm: LLMClient,
    *,
    goal: str,
    candidates: list[JudgeCandidate],
    depth: int,
    max_depth: int,
) -> JudgeOutcome:
    """Judge with total fallback to the deterministic `decide()`."""
    try:
        decision, rationale = await judge_decide(
            llm, goal=goal, candidates=candidates, depth=depth, max_depth=max_depth
        )
        return JudgeOutcome(decision=decision, rationale=rationale, source="judge")
    except Exception as exc:  # noqa: BLE001 — fallback must be total
        logger.warning("judge decide failed, falling back to threshold: %s", exc)
        scored = [(c.id, c.score) for c in candidates]
        decision = decide(scored, depth=depth, max_depth=max_depth)
        return JudgeOutcome(decision=decision, rationale="", source="threshold_fallback")
```

- [ ] **Step 5: Run the tests, verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_judge.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Lint + type-check**

Run: `backend/.venv/Scripts/python.exe -m ruff check kodoku tests` then `backend/.venv/Scripts/python.exe -m mypy kodoku`
Expected: both clean.

- [ ] **Step 7: Commit**

```bash
git add backend/kodoku/engine/steps/judge.py backend/kodoku/engine/prompts/judge.md backend/tests/test_judge.py
git commit -m "feat(judge): add LLM-judge decide step with threshold fallback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Config + engine wiring + `decide.completed` event

**Files:**
- Modify: `backend/kodoku/api/dtos.py` (`SessionConfig`)
- Modify: `backend/kodoku/engine/events.py`
- Modify: `backend/kodoku/engine/state_machine.py:199-201` (the `decide(...)` call) and its imports
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `decide_with_judge`, `JudgeCandidate` from Task 1; existing `decide`, `Decision`; `self.clients.evaluate`, `self.config`, `self.session.goal`.
- Produces: `SessionConfig.decide_mode: Literal["threshold","judge"] = "threshold"`; event constant `DECIDE_COMPLETED = "decide.completed"` with payload `{parent_id, keep, prune, rationale, source}`.

- [ ] **Step 1: Add the config field**

In `backend/kodoku/api/dtos.py`, `SessionConfig` (after `hitl_mode`), add:

```python
    decide_mode: Literal["threshold", "judge"] = "threshold"
```

(`Literal` is already imported for `hitl_mode`; if not, add `from typing import Literal`.)

- [ ] **Step 2: Add the event constant**

In `backend/kodoku/engine/events.py`, after the M5 checkpoint constants, add:

```python
DECIDE_COMPLETED = "decide.completed"
```

(Update the module's "nine names"/count comment to reflect the new total.)

- [ ] **Step 3: Write the failing engine tests**

In `backend/tests/test_engine.py`, add near the other run tests (reuse `_make_session`, `_roles`, `_Recorder`, `_expand`, `_eval`, `FakeLLMClient`). Note the fake is FIFO-shared across roles, so in judge mode each parent consumes one extra judge completion after its evals:

```python
from kodoku.engine.events import DECIDE_COMPLETED  # add to the existing events import


async def test_judge_mode_drives_keep_prune_and_emits_decide_completed(
    db_session: AsyncSession,
) -> None:
    # branching_factor=2, max_depth=1: expand root -> A, B; judge keeps B, prunes A.
    session = await _make_session(db_session, branching_factor=2, max_depth=1)
    session.config["decide_mode"] = "judge"

    # We can't know child ids until after expand, so the judge selects by a
    # sentinel the engine maps to ids: instead, script the judge to keep the
    # LOWER-scored child to prove the judge (not the threshold) decided.
    # Use a custom fake that, on its judge call, returns keep=[<lower-scored id>].
    rec = _Recorder()

    class _JudgeFake(FakeLLMClient):
        async def complete(self, *, system, prompt, json_object=False):  # type: ignore[override]
            self.calls.append((system, prompt))
            # expand + eval calls are scripted; the judge call is detected by the
            # candidates_block containing both ids — return keep=second id.
            if "keep" in prompt and "prune" in prompt and "id=" in prompt:
                import re
                ids = re.findall(r"id=([0-9a-f-]{36})", prompt)
                return json.dumps({"keep": [ids[1]], "prune": [ids[0]],
                                   "rationale": "judge chose B"})
            return self.completions.pop(0)

    llm = _JudgeFake(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(9.0)),
                     json.dumps(_eval(2.0))],
        chunks=["done"],
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    nodes = (await db_session.execute(
        select(Node).where(Node.session_id == session.id,
                            Node.kind == NodeKind.CANDIDATE.value))).scalars().all()
    by_title = {n.title: n for n in nodes}
    # Judge kept B (score 2.0) and pruned A (score 9.0) — opposite of threshold.
    assert by_title["B"].status == NodeStatus.KEPT.value
    assert by_title["A"].status == NodeStatus.PRUNED.value
    assert rec.count(DECIDE_COMPLETED) == 1
    payload = next(p for t, p in rec.events if t == DECIDE_COMPLETED)
    assert payload["source"] == "judge"
    assert payload["rationale"] == "judge chose B"


# (`_JudgeFake` is defined inline above; no module-level judge stub is needed.)


async def test_threshold_mode_unchanged_and_emits_decide_completed(
    db_session: AsyncSession,
) -> None:
    session = await _make_session(db_session, branching_factor=2, max_depth=1)
    # default decide_mode == "threshold"
    rec = _Recorder()
    llm = FakeLLMClient(
        completions=[json.dumps(_expand("A", "B")), json.dumps(_eval(8.0)),
                     json.dumps(_eval(3.0))],
        chunks=["done"],
    )
    engine = DecisionEngine(db_session, session, _roles(llm), rec)
    await engine.run()

    nodes = (await db_session.execute(
        select(Node).where(Node.session_id == session.id,
                            Node.kind == NodeKind.CANDIDATE.value))).scalars().all()
    by_title = {n.title: n for n in nodes}
    assert by_title["A"].status == NodeStatus.KEPT.value   # 8.0 >= 6.0
    assert by_title["B"].status == NodeStatus.PRUNED.value
    payload = next(p for t, p in rec.events if t == DECIDE_COMPLETED)
    assert payload["source"] == "threshold"
    assert payload["rationale"] == ""
```

- [ ] **Step 4: Run the tests, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_engine.py -k "judge_mode or threshold_mode_unchanged" -v`
Expected: FAIL — `DECIDE_COMPLETED` import error / `decide.completed` not emitted / judge path absent.

- [ ] **Step 5: Wire the engine**

In `backend/kodoku/engine/state_machine.py`, add imports near the other step imports:

```python
from kodoku.engine.events import DECIDE_COMPLETED  # add to the existing events import line
from kodoku.engine.steps.judge import JudgeCandidate, decide_with_judge
```

Replace lines 199-201 (the `decision = decide(...)` block) with:

```python
        if self.config.decide_mode == "judge":
            judge_cands = [
                JudgeCandidate(
                    id=child.id, title=child.title, content=child.content,
                    score=ev.score, critique=ev.critique, dimensions=ev.dimensions,
                )
                for child, ev in zip(children, results, strict=True)
            ]
            outcome = await decide_with_judge(
                self.clients.evaluate, goal=self.session.goal,
                candidates=judge_cands, depth=parent.depth + 1,
                max_depth=self.config.max_depth,
            )
            decision, rationale, source = outcome.decision, outcome.rationale, outcome.source
        else:
            decision = decide(scored, depth=parent.depth + 1, max_depth=self.config.max_depth)
            rationale, source = "", "threshold"

        await self.emit(
            DECIDE_COMPLETED,
            {
                "parent_id": str(parent.id),
                "keep": [str(cid) for cid in decision.keep],
                "prune": [str(cid) for cid in decision.prune],
                "rationale": rationale,
                "source": source,
            },
        )
```

The existing `if self.config.hitl_mode == "every_branch": ...` block and the autopilot marking below it are unchanged — they consume `decision` as before, so the judge's proposal flows into `_pause_for_checkpoint` automatically.

- [ ] **Step 6: Run the new tests + full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_engine.py -k "judge_mode or threshold_mode_unchanged" -v`
Expected: PASS.
Run: `backend/.venv/Scripts/python.exe -m pytest`
Expected: full suite green (existing autopilot tests still pass = threshold unchanged).

- [ ] **Step 7: Lint + type-check**

Run: `backend/.venv/Scripts/python.exe -m ruff check kodoku tests` then `backend/.venv/Scripts/python.exe -m mypy kodoku`
Expected: both clean.

- [ ] **Step 8: Regenerate contracts**

Run (from `frontend/`): `npm run gen:contracts`
Expected: `lib/types/contracts.ts` now lists `decide_mode` on `SessionConfig` (a minimal additive diff).

- [ ] **Step 9: Commit**

```bash
git add backend/kodoku/api/dtos.py backend/kodoku/engine/events.py backend/kodoku/engine/state_machine.py backend/tests/test_engine.py frontend/lib/types/contracts.ts
git commit -m "feat(judge): wire decide_mode into engine + decide.completed event

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `decide_mode` toggle in NewSessionDialog (frontend)

**Files:**
- Modify: `frontend/app/_components/NewSessionDialog.tsx`

**Interfaces:**
- Consumes: `SessionConfig.decide_mode: "threshold" | "judge"` (from `contracts.ts`, Task 2). Mirrors the existing `hitl_mode` segmented toggle in this same file.

- [ ] **Step 1: Add state + toggle, write into config**

In `frontend/app/_components/NewSessionDialog.tsx`:

1. Add state near the existing `hitlMode` state:

```tsx
const [decideMode, setDecideMode] = useState<"threshold" | "judge">("threshold");
```

2. In the `createSession({ ..., config: { ... } })` call, add the field next to `hitl_mode`:

```tsx
          decide_mode: decideMode,
```

3. Add a segmented toggle in the form, mirroring the existing `hitl_mode` toggle's markup/styling, with options:
   - `threshold` → label "Threshold"
   - `judge` → label "LLM judge"

Use the same control component and Tailwind classes the `hitl_mode` toggle uses (read that block and copy its shape; only the state setter, values, and labels differ).

- [ ] **Step 2: Type-check + lint**

Run (from `frontend/`): `npm run typecheck` then `npm run lint`
Expected: both clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/_components/NewSessionDialog.tsx
git commit -m "feat(judge): add decide_mode toggle to new-session dialog

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (later Phase B / D)
LiteLLM Router; cost/budget tracking + UI; persisting the judge rationale + "why this branch" UI; a distinct per-role judge model (reuse `evaluate`); per-node model override. Don't build these here.
