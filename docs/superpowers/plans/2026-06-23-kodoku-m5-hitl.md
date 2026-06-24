# Kodoku M5 — Human-in-the-loop checkpoints (DB-driven) + CI

**Execute this on a fresh context window.** Use the
`superpowers:subagent-driven-development` skill: branch `m5-hitl` off `main`,
one implementer subagent per task + a task reviewer after each + a final
whole-branch review, then `superpowers:finishing-a-development-branch`. The
skill's helper scripts live at
`C:\Users\shoh5\.claude\plugins\cache\claude-plugins-official\superpowers\6.0.0\skills\subagent-driven-development\scripts\`
(`task-brief PLAN N`, `review-package BASE HEAD`). Commit this plan first so
task-1's diff is clean.

## Where the code is now (post-Phase A, on `main`)

- **Engine** `kodoku/engine/state_machine.py`: `DecisionEngine(db, session,
  clients: RoleClients, emit, *, should_stop=...)`. Loop: seed frontier with the
  root node id → per parent: `expand` (clients.expand) → persist candidate
  `Node`s → `evaluate` each child concurrently (`asyncio.gather` +
  `Semaphore(EVAL_CONCURRENCY=4)`, persist/emit in child order) → `decide`
  (deterministic, `KEEP_THRESHOLD=6.0`) → mark kept/pruned + parent EXPANDED →
  extend frontier → when frontier empty: `synthesize` → DONE. **Engine is
  flush-only; the single `commit()` is in `_run_engine`'s `finally` in
  `api/run.py`.** No HITL today — it runs to completion (this IS the autopilot
  behavior M5 keeps).
- **Steps** `kodoku/engine/steps/{expand,evaluate,decide,synthesize}.py` are
  pure. `decide(scored, *, depth, max_depth) -> Decision(keep, prune, expand)`.
- **Events** `kodoku/engine/events.py`: constants `SESSION_STARTED`,
  `ENGINE_STATE_CHANGED`, `NODE_CREATED`, `NODE_UPDATED`, `EVALUATION_COMPLETED`,
  `SYNTHESIS_STREAMING`, `SYNTHESIS_COMPLETED`, `SESSION_DONE`, `SESSION_ERROR`.
  **No checkpoint constants yet.** `Emitter = Callable[[str, dict], Awaitable]`;
  `make_db_emitter(db, session_id)` wraps `kodoku/ws/emit.py::emit_event`
  (journals to `events` table + broadcasts over WS).
- **Models** `kodoku/db/models.py`: `Checkpoint(id, session_id, kind, payload
  jsonb, decision jsonb|null, resolved_at|null, created_at)` EXISTS (M2, unused).
  `Node(id, session_id, parent_id, depth, kind, title, content, status,
  created_at)`. Enums `kodoku/domain/enums.py`: `SessionStatus`(DRAFT, RUNNING,
  AWAITING_HUMAN, DONE, ERROR, PAUSED — `AWAITING_HUMAN` exists), `NodeStatus`
  (PENDING, ACTIVE, PRUNED, KEPT, EXPANDED), `NodeKind`(ROOT, CANDIDATE,
  SYNTHESIS), `CheckpointKind`(POST_EXPAND, POST_EVALUATE, PRE_SYNTHESIS).
- **API** `kodoku/api/run.py`: `_run_engine(session_id, build_clients)` wrapper;
  `POST /sessions/{id}/run` (404 missing; 409 if status ∉ {draft, paused,
  error}; 409 if `runner.is_running`; else `runner.start(...)`); `POST
  /interrupt`. `RoleClientsBuilder = Callable[[AsyncSession], Awaitable
  [RoleClients]]` is the injectable test seam. `runner` (`engine/runner.py`):
  `start/should_stop/interrupt/is_running/join`.
- **DTOs** `kodoku/api/dtos.py`: `SessionConfig(model, branching_factor,
  max_depth, temperature)`. `CheckpointDTO(id, session_id, kind, payload,
  decision, resolved_at, created_at)` exists; `SessionDetailResponse` already
  includes `checkpoints`.
- **Frontend** `frontend/lib/ws/reducer.ts` ALREADY folds `checkpoint.reached`
  (→ status `awaiting_human`, sets `graph.checkpoint`) and `checkpoint.resolved`
  (→ `running`, clears it). `frontend/lib/ws/types.ts`: `Checkpoint =
  {checkpoint_id, kind, payload: {prune, keep, expand}}`, `GraphNode` has
  `score?`, `critique?` but NOT `dimensions`. `frontend/app/s/[sessionId]/
  SessionGraphView.tsx` renders the graph + Run/Interrupt + status badge.
  **Confirm these reducer cases still exist before scoping M5.4** — if so, M5.4
  is UI-only plus adding `dimensions` to the node.

## Design decisions (authoritative — these OVERRIDE spec §8's condition-var design)

1. **Resume is DB-driven, not waiting-task-driven.** No `asyncio` condition var.
   At a checkpoint the engine persists state and STOPS the task. `/resume`
   applies the decision to the DB and starts a FRESH engine run that rebuilds
   its frontier from the DB. This survives refresh/restart and removes async
   fragility.
2. **One frontier-rebuild function powers both resume and the dup-node fix.**
   `rebuild_frontier(db, session) -> deque[UUID]` = node ids that are still
   expandable: `status ∈ {ACTIVE, KEPT}` AND `kind != SYNTHESIS` AND `depth <
   config.max_depth` AND the node has NO children yet (not expanded). For a
   fresh DRAFT session this returns `[root_id]`; for a resumed session it returns
   the kept-but-unexpanded nodes. The engine seeds from this instead of
   hardcoding `[root]`. This alone fixes the shipped bug where re-running a
   paused/error session re-expands the root and DUPLICATES nodes.
3. **`hitl_mode` is per-session config, default `autopilot` (no behavior
   change).** `SessionConfig.hitl_mode: Literal["autopilot","every_branch"] =
   "autopilot"`. `autopilot` = today's run-to-done. `every_branch` = pause after
   each parent's evaluate.
4. **Pause = persist + emit + stop (every_branch).** After `expand`+`evaluate`
   of a parent, the engine computes the `decide` PROPOSAL but, in `every_branch`,
   does NOT apply it: it persists a `Checkpoint(kind=POST_EVALUATE, payload=
   {proposed_keep, proposed_prune, candidates:[{id,title,content,score,critique,
   dimensions}]})`, emits `checkpoint.reached {checkpoint_id, kind, payload}`,
   sets `status=AWAITING_HUMAN`, flushes, and RETURNS from `run()`. The candidate
   nodes stay `ACTIVE` until `/resume`.
5. **Decision shape is keep + prune + edits; expand is implicit.** `/resume`
   body: `{checkpoint_id, keep: [UUID], prune: [UUID], edits: {UUID:
   {title?, content?}}}`. Any checkpoint candidate not in `keep` is pruned
   (kept = survivors). A kept node within `depth < max_depth` is expanded on the
   next run (frontier rebuild picks it up) — no separate `expand` list in v1
   (YAGNI; a "keep but freeze" leaf can come later).
6. **No `pre_synthesis` checkpoint in v1.** When the rebuilt frontier is empty,
   the engine synthesizes from KEPT nodes and finishes. The per-branch
   checkpoints are the only HITL gate.
7. **Smart-decide judge is Phase B, NOT M5.** The checkpoint shows the
   deterministic `decide` proposal + each candidate's score/critique/dimensions.
   "Why this branch" = the evaluation critique for now.

## Global Constraints (bind every task)

- Python 3.12, `from __future__ import annotations`. mypy `strict = true`; ruff
  line-length 100 rules `E,F,I,B,UP,W`; zero errors. Match existing style.
- Engine STAYS flush-only; the only `commit()` is the `/run`/`/resume` boundary.
- Reuse `emit_event`/`make_db_emitter`; no second event bus. Reuse the
  `RoleClientsBuilder` injectable seam for tests; never hit a real provider in
  tests. Docker Postgres up; existing `conftest.py` fixtures.
- venv: `backend/.venv/Scripts/python.exe -m pytest|mypy|ruff|alembic`.
- Frontend: TS strict (no `any`), `npm run typecheck` + `npm run lint` clean;
  regenerate `lib/types/contracts.ts` after any backend DTO change.
- Autopilot behavior must be byte-for-byte unchanged where not explicitly
  modified (it's the default and the existing test suite covers it).

---

## Task 1: DB frontier rebuild (foundation; fixes the dup-node bug)

**Files.** `kodoku/engine/frontier.py`, `kodoku/engine/state_machine.py` (seed
from it), `backend/tests/test_frontier.py` + update `tests/test_engine.py`.

`async def rebuild_frontier(db: AsyncSession, session: Session) -> deque[UUID]`:
select candidate node ids per decision #2 — `status in (ACTIVE, KEPT)`, `kind !=
SYNTHESIS`, `depth < session.config["max_depth"]`, and id NOT in `(SELECT
DISTINCT parent_id FROM nodes WHERE parent_id IS NOT NULL AND session_id = :sid)`
(no children = not yet expanded). Order by `(depth, created_at)`. The engine's
`run()` seeds `self._frontier = await rebuild_frontier(db, session)` instead of
`deque([root_id])`.

**Tests.** Fresh DRAFT session (root only) → frontier == `[root_id]`. After a
session where root is EXPANDED with 2 candidates both KEPT at depth 1 (max_depth
2) → frontier == those 2 ids. A candidate at `depth == max_depth` → excluded. An
EXPANDED node → excluded. **Dup-node regression:** run an autopilot session to
DONE, then construct a paused scenario and call `run()` again → assert NO new
duplicate candidate nodes are created for already-expanded parents (RED against
the old `[root]` seed, GREEN after).

**Verify.** `pytest tests/test_frontier.py tests/test_engine.py`; `mypy kodoku`;
`ruff check`.

---

## Task 2: hitl_mode config + engine pause-at-branch + checkpoint events

**Files.** `kodoku/engine/events.py` (add `CHECKPOINT_REACHED =
"checkpoint.reached"`, `CHECKPOINT_RESOLVED = "checkpoint.resolved"`),
`kodoku/api/dtos.py` (`SessionConfig.hitl_mode`), `kodoku/engine/state_machine.py`
(pause branch), `backend/tests/test_engine.py` (+ cases).

- `SessionConfig.hitl_mode: Literal["autopilot","every_branch"] = "autopilot"`.
- In `run()`, after a parent's children are evaluated and the `decide` proposal
  computed: if `config.hitl_mode == "every_branch"`, persist a `Checkpoint`
  (kind=`CheckpointKind.POST_EVALUATE.value`, payload per decision #4 — include
  each candidate's id/title/content/score/critique/dimensions and the proposed
  keep/prune id lists), emit `CHECKPOINT_REACHED` with `{checkpoint_id, kind,
  payload}`, set `session.status = AWAITING_HUMAN.value`, `current_step=None`,
  `flush()`, and `return`. Do NOT mark kept/pruned, do NOT mark the parent
  EXPANDED yet (it gets marked when the children are resolved — or mark parent
  EXPANDED now since its children exist; pick one and be consistent: **mark
  parent EXPANDED now** so it isn't re-expanded by a future frontier rebuild;
  the candidates stay ACTIVE pending resolution). Autopilot path unchanged.

**Tests.** `every_branch` run with `branching_factor=2`: after `run()`, status ==
`awaiting_human`, exactly one `Checkpoint` row (POST_EVALUATE, `resolved_at`
None), `CHECKPOINT_REACHED` emitted once, the 2 candidates persisted and still
`ACTIVE`, NO synthesis, NO `SESSION_DONE`. Autopilot run with same inputs →
unchanged (still runs to DONE, no checkpoint rows) — regression guard.

**Verify.** `pytest tests/test_engine.py`; `mypy kodoku`; `ruff check`;
regenerate `contracts.ts` (SessionConfig changed).

---

## Task 3: /resume endpoint + resume restart

**Files.** `kodoku/api/dtos.py` (`ResumeRequest`), `kodoku/api/run.py`
(`POST /resume`; ensure `/run` resume path uses the new frontier rebuild — it
does automatically via Task 1), `backend/tests/test_run_api.py` (+ cases).

- `ResumeRequest`: `checkpoint_id: UUID`, `keep: list[UUID]`, `prune: list[UUID]`,
  `edits: dict[UUID, NodeEdit]` where `NodeEdit(title: str|None, content:
  str|None)`. (`prune` may be omitted/derived: survivors = `keep`, everything
  else among the checkpoint candidates is pruned — validate that `keep ∪ prune`
  ⊆ the checkpoint's candidate ids.)
- `POST /sessions/{id}/resume` → 202. Validate: session exists (404); `status ==
  AWAITING_HUMAN` (409 otherwise); the latest unresolved `Checkpoint` for the
  session has `id == checkpoint_id` (409 on mismatch — prevents racing a stale
  panel). Apply on a fresh DB session committed at the end (like `_run_engine`):
  mark each checkpoint candidate `KEPT` (in keep) or `PRUNED` (otherwise); apply
  `edits` to node `title`/`content`; emit `NODE_UPDATED` per changed node; set
  `checkpoint.decision = {keep, prune, edits}` and `resolved_at = now`; emit
  `CHECKPOINT_RESOLVED {checkpoint_id, decision}`; commit. Then
  `runner.start(id, _run_engine(id, build_clients))` to continue (the fresh run
  rebuilds the frontier — now including newly-KEPT nodes — and proceeds to the
  next parent or to synthesis if empty). Guard `runner.is_running` (409).

**Tests** (inject a `RoleClients` of fakes, `every_branch`, await `runner.join`).
Full cycle: `run` → checkpoint reached (status awaiting_human) → `resume`
keeping a subset + one edit → after join, kept nodes `KEPT`, dropped `PRUNED`,
edit applied, checkpoint `resolved_at` set, replay contains `checkpoint.reached`
then `checkpoint.resolved`; the run either reaches the next checkpoint or DONE.
`resume` with a wrong `checkpoint_id` → 409. `resume` when status is not
`awaiting_human` → 409.

**Verify.** `pytest tests/test_run_api.py`; full suite; `mypy kodoku`; `ruff
check`; regenerate `contracts.ts`.

---

## Task 4: CheckpointPanel + decision matrix (frontend)

**Files.** `frontend/components/panels/CheckpointPanel.tsx`,
`frontend/lib/ws/{types.ts,reducer.ts}` (add `dimensions` to `GraphNode`, fold it
from `evaluation.completed`), `frontend/lib/api/client.ts` (`resumeSession`),
`frontend/app/s/[sessionId]/SessionGraphView.tsx` (mount the panel), regenerate
`contracts.ts`. **First verify** the reducer already folds `checkpoint.reached`/
`checkpoint.resolved` (it should) — if so, no event-handling changes beyond
`dimensions`.

- When `graph.status === "awaiting_human"` and `graph.checkpoint` is set, show a
  slide-in `CheckpointPanel`: a **decision matrix** of the checkpoint's
  candidates — rows = candidates, columns = score + each dimension + critique —
  each row with a keep/prune toggle (default to the engine's proposed
  keep/prune) and inline-editable title/content. "Approve & continue" → `POST
  /resume` with `{checkpoint_id, keep, prune, edits}`; "Use engine proposal" →
  resume with the proposed split unchanged.
- `api.resumeSession(id, body)` → `POST /sessions/${id}/resume`.

**Verify.** `npm run typecheck` + `npm run lint`. (No FE test harness — don't add
one; visual check is manual.)

---

## Task 5: Node detail drawer + resume banner + hitl toggle

**Files.** `frontend/components/panels/NodeDrawer.tsx`,
`frontend/app/s/[sessionId]/SessionGraphView.tsx` (drawer + banner),
`frontend/components/graph/NodeCard.tsx` or `Graph.tsx` (node click →
selection), `frontend/app/_components/NewSessionDialog.tsx` (hitl toggle).

- **NodeDrawer:** clicking a graph node opens a side drawer showing title,
  content, score, critique, dimensions, and the parent→node path. Reads from the
  store (`graph.nodes`); no new fetch.
- **Resume banner:** on the session page, if `status` is `paused` or `error`,
  show a banner naming the next action ("Resume from N kept nodes" / "Retry
  after error") with a button → `POST /run`. (`awaiting_human` is handled by the
  CheckpointPanel, not the banner.)
- **NewSessionDialog:** add a `hitl_mode` toggle (Autopilot vs "Review each
  branch") writing `config.hitl_mode`.

**Verify.** `npm run typecheck` + `npm run lint`.

---

## Task 6: CI (GitHub Actions)

**Files.** `.github/workflows/ci.yml`.

- **backend job:** `services: postgres` (postgres:16, health-check); checkout;
  setup Python 3.12; `pip install -e ".[dev]"` in `backend`; `alembic upgrade
  head`; `pytest`; `ruff check kodoku tests`; `mypy kodoku`. Set `DATABASE_URL`
  to the service.
- **frontend job:** checkout; setup Node 20; `npm ci` in `frontend`; `npm run
  typecheck`; `npm run lint`; `npm run build`.
- Trigger on `push` and `pull_request`.

**Verify.** YAML parses; jobs are well-formed. (Actions can't run locally — it
executes on push; confirm the commands match what the plan's other tasks run
locally.)

---

## Dependencies / order
1 → 2 → 3 (backend chain). 4 and 5 depend on 2/3's endpoints + events. 6 is
independent (do anytime). Recommended: 1, 2, 3, 4, 5, 6.

## Out of scope (later)
Smart-decide judge + per-node model override + budget/cost UI (Phase B / D);
`pre_synthesis` checkpoint; keep-but-freeze leaves; replay-animation; export
memo. Don't build these here.
