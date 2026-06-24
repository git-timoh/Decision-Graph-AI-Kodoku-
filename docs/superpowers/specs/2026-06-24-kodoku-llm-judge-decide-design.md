# Kodoku — LLM-as-judge `decide` (Phase B, sub-project 1)

## Goal

Replace Kodoku's dumb threshold `decide` with an opt-in LLM judge that selects
which sibling candidates to keep vs prune **comparatively** (seeing all siblings
of a parent at once), with the deterministic threshold as the guaranteed
fallback. This closes the first of the two thesis-flagged engine gaps ("dumb
threshold `decide`"). Cost/budget tracking and the LiteLLM Router are separate
Phase B sub-projects, out of scope here.

## Background (current state on `main`, post-M5)

- `kodoku/engine/steps/decide.py`: pure `decide(scored, *, depth, max_depth) ->
  Decision(keep, prune, expand)`. `keep` = ids scoring ≥ `KEEP_THRESHOLD=6.0`
  (or the single best if none qualify); `prune` = the rest; `expand` = `keep`
  unless `depth >= max_depth`. This stays as the fallback.
- `kodoku/engine/steps/evaluate.py`: per-node `evaluate(llm, …) ->
  EvaluationResult(score, critique, dimensions)`. Step pattern: read a prompt
  template under `kodoku/engine/prompts/`, `Template(...).safe_substitute(...)`
  (user text may contain `{`/`}`), then `parse_json(llm, system, prompt,
  model_cls)`.
- `kodoku/llm/factory.py`: `RoleClients(expand, evaluate, synthesize)`; per-role
  models, `evaluate`/`synthesize` default to the cheap `deepseek/deepseek-chat`.
  The judge **reuses `self.clients.evaluate`** — no new role.
- `kodoku/engine/state_machine.py::_expand_one`: after children are evaluated
  (`results`, `scored`), it calls `decide(...)`. In `every_branch` HITL mode
  (M5) it persists a `Checkpoint` whose payload carries `proposed_keep` /
  `proposed_prune` (the decide proposal) and the candidates, then pauses.
- `kodoku/engine/events.py`: event-type constants + `make_db_emitter`. M5 added
  `CHECKPOINT_REACHED` / `CHECKPOINT_RESOLVED`.
- `kodoku/api/dtos.py::SessionConfig`: `model, branching_factor, max_depth,
  temperature, hitl_mode` (pydantic, `extra="forbid"`). Engine reads
  `self.config = SessionConfig(**session.config)`.
- Frontend `NewSessionDialog.tsx` already has a `hitl_mode` segmented toggle —
  the `decide_mode` toggle mirrors it.

## Design

### New step: `kodoku/engine/steps/judge.py`

```python
class JudgeResult(BaseModel):
    keep: list[UUID]        # ids to keep (must be a subset of the candidate ids)
    prune: list[UUID]       # ids to prune
    rationale: str          # short comparative explanation

async def judge_decide(
    llm: LLMClient,
    *,
    goal: str,
    candidates: list[JudgeCandidate],   # id, title, content, score, critique, dimensions
    depth: int,
    max_depth: int,
) -> Decision:
    ...
```

- Builds a prompt from `kodoku/engine/prompts/judge.md` listing every candidate
  with its id, title, content, score, critique, and dimensions; asks the model
  to return strict JSON `{keep: [...], prune: [...], rationale: "..."}`.
- Parses via `parse_json(llm, system=_SYSTEM, prompt=prompt,
  model_cls=JudgeResult)`.
- **Validation:** `keep ∪ prune` must equal the candidate id set (exact cover);
  every id must be a real candidate id. If the model keeps none, that is allowed
  only if it is a deliberate prune-all — but to match the threshold floor's
  "synthesis always has material" guarantee, if `keep` is empty the judge result
  is treated as invalid and falls back (see below).
- Returns a `Decision` (reusing `decide.py`'s dataclass): `keep`/`prune` from the
  judge; `expand = list(keep) if depth < max_depth else []` — expansion stays
  structural, identical to threshold mode.
- Returns the `rationale` to the caller as well (e.g. `(Decision, rationale)` or
  a small wrapper); the engine emits it (below). Exact return shape is an
  implementation detail for the plan.

### Fallback (guaranteed floor)

`judge_decide` (or the engine call site) wraps the LLM path so that **any** of:
LLM error, JSON parse failure, ids not an exact cover of candidates, or empty
`keep` → falls back to the deterministic `decide(scored, depth, max_depth)`. The
fallback is logged and surfaced in the emitted `decide.completed` event
(`source: "judge" | "threshold_fallback"`). The engine never crashes on a bad
judge response, and threshold behavior is always reachable.

### Config

`SessionConfig.decide_mode: Literal["threshold", "judge"] = "threshold"`.
Default `"threshold"` keeps autopilot byte-for-byte unchanged. `extra="forbid"`
means old sessions without the field still parse (default applies). Contracts
regenerated after this DTO change.

### Engine wiring (`_expand_one`)

After the children are evaluated and `scored`/`results` are built, branch:

- `decide_mode == "judge"`: build `JudgeCandidate`s from `children` + `results`
  (id/title/content/score/critique/dimensions), call `judge_decide(
  self.clients.evaluate, goal=…, candidates=…, depth=parent.depth+1,
  max_depth=…)`, with the fallback wrapper. Use its `Decision`.
- otherwise: today's `decide(scored, depth=parent.depth+1, max_depth=…)`.

Then the **existing** keep/prune-marking and frontier-extension code runs on the
chosen `Decision` unchanged.

Emit `DECIDE_COMPLETED = "decide.completed"` with `{parent_id, keep: [str],
prune: [str], rationale: str, source: "judge" | "threshold" |
"threshold_fallback"}` once per parent, in BOTH autopilot and `every_branch`
paths. (Threshold mode emits `source: "threshold"`, `rationale: ""`.)

**HITL synergy:** in `every_branch`, the `Decision` computed above (judge or
threshold) is the one whose `keep`/`prune` populate the checkpoint's
`proposed_keep`/`proposed_prune`. No separate code path — the proposal the human
reviews is simply whatever `decide_mode` produced.

### Events / frontend

- New constant `DECIDE_COMPLETED = "decide.completed"` in `events.py`.
- The WS reducer's `switch` has a `default` that ignores unknown event types, so
  `decide.completed` needs **no** reducer change for v1 (it is journaled to the
  `events` table and broadcast, available for later UI). No "why this branch" UI
  in this sub-project.
- `NewSessionDialog.tsx`: add a `decide_mode` segmented toggle ("Threshold" vs
  "LLM judge") mirroring the existing `hitl_mode` toggle, writing
  `config.decide_mode`. Contracts regenerated.

## Components & boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `steps/judge.py` | Pure: candidates → `Decision` + rationale via LLM, validated | `LLMClient`, `parse_json`, `decide.Decision`, `prompts/judge.md` |
| `prompts/judge.md` | The judge prompt template | — |
| `state_machine._expand_one` | Pick threshold vs judge, apply Decision, emit `decide.completed` | `judge_decide`, `decide`, `SessionConfig.decide_mode` |
| `SessionConfig.decide_mode` | Per-session opt-in | — |
| `NewSessionDialog` toggle | Let the user set `decide_mode` | contracts |

## Testing

- **Judge step** (`tests/test_judge.py`): with a `FakeLLMClient` returning canned
  JSON — valid keep/prune subset → correct `Decision`; ids that aren't an exact
  cover → fallback to `decide`; malformed JSON / LLM error → fallback; empty
  `keep` → fallback. Reuse existing fake-client fixtures; never hit a real
  provider.
- **Engine** (`tests/test_engine.py`): `decide_mode="judge"` autopilot run with a
  fake judge → kept/pruned statuses reflect the judge's split, `decide.completed`
  emitted once per parent with `source:"judge"`. `decide_mode="threshold"` (and
  default-unset) run → identical to current behavior, `decide.completed` with
  `source:"threshold"` — regression guard that autopilot is unchanged.
- **HITL** (existing `every_branch` tests): with `decide_mode="judge"`, the
  checkpoint's `proposed_keep`/`proposed_prune` equal the judge's split.

## Global constraints

- Python 3.12, `from __future__ import annotations`; mypy `strict = true` zero
  errors; ruff line-length 100 rules E,F,I,B,UP,W zero errors. Match existing
  style.
- Engine stays flush-only; commits only at the `/run`/`/resume` boundary.
- Reuse `parse_json`, the step/prompt pattern, `make_db_emitter`, and the
  `RoleClientsBuilder` test seam. Never hit a real provider in tests.
- Frontend TS strict, no `any`; `npm run typecheck` + `npm run lint` clean;
  regenerate `lib/types/contracts.ts` after the `SessionConfig` change.
- `threshold` (default) behavior must be byte-for-byte unchanged.

## Out of scope (later Phase B / D)

LiteLLM Router; cost/budget tracking + UI; persisting the judge rationale +
"why this branch" UI; a distinct per-role judge model (reuse `evaluate` for
now); per-node model override.
