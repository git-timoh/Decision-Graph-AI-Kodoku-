# Kodoku M4 — DecisionEngine + LLM abstraction

Executes milestone M4 from `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md`
(§8 state machine, §9 LLM layer, §11/§12 roadmap). Baseline: commit on branch
`m4-decision-engine` after M3 (events journal, WS, React Flow graph).

**Goal.** Real Tree-of-Thoughts loop end-to-end through a typed `LLMClient`,
driven and tested entirely against a `FakeLLMClient`. The loop runs fully
automatically (no human pause — that is M5).

## Global Constraints (bind every task)

- Python 3.12, `from __future__ import annotations` at top of every module.
- mypy is `strict = true`; ruff line-length 100, rules `E,F,I,B,UP,W`. All new
  code must pass `mypy kodoku` and `ruff check` with zero errors.
- Match existing style: async SQLAlchemy 2.x `Mapped`/`mapped_column`,
  `StrEnum` domain enums (`kodoku/domain/enums.py`), Pydantic v2 `ConfigDict`.
- **Steps are pure**: a step takes an `LLMClient` plus plain inputs and returns
  structured data. Steps NEVER touch the DB and NEVER emit events. The
  `DecisionEngine` owns all persistence and all event emission. (`decide` is
  pure and takes no LLM — it is deterministic.)
- **Reuse M3 event plumbing.** Events are emitted through an injected emitter;
  the production emitter is `kodoku/ws/emit.py::emit_event` (journals to the
  `events` table AND broadcasts over WS). Do NOT build a second EventBus class.
- **No HITL in M4.** The `checkpoints` table and `AWAITING_HUMAN` state are M5.
  The M4 engine auto-applies the deterministic `decide` policy and continues.
- **No live LLM calls this session.** `LiteLLMClient` is written but its
  against-a-real-model smoke test is deferred (spec M4.11). Every test uses
  `FakeLLMClient`. Mark `LiteLLMClient` with a `ponytail:` comment noting it is
  unverified against a live provider.
- Event type strings (journaled + broadcast), reused from spec §7:
  `session.started`, `engine.state_changed`, `node.created`, `node.updated`,
  `evaluation.completed`, `synthesis.streaming`, `synthesis.completed`,
  `session.done`, `session.error`. (No `checkpoint.*` in M4.)
- Tests run against Postgres via the existing `conftest.py` fixtures
  (`db_session`, `client`, `truncate_all`). Docker Postgres must be up.
- The venv interpreter is `backend/.venv/Scripts/python.exe` (Windows).

## Shared interfaces (authoritative signatures)

```python
# kodoku/llm/base.py
class LLMClient(Protocol):
    async def complete(self, *, system: str, prompt: str,
                       json_object: bool = False) -> str: ...
    def stream(self, *, system: str, prompt: str) -> AsyncIterator[str]: ...
```

```python
# step result models (Pydantic v2), live in kodoku/engine/steps/*.py
class Candidate(BaseModel):      # expand output element
    title: str
    content: str
class ExpandResult(BaseModel):
    candidates: list[Candidate]
class EvaluationResult(BaseModel):
    score: float                 # 0.0–10.0
    critique: str
    dimensions: dict[str, float]
```

```python
# kodoku/engine/steps/decide.py  (pure, deterministic, no LLM)
@dataclass(frozen=True, slots=True)
class Decision:
    keep: list[UUID]
    prune: list[UUID]
    expand: list[UUID]
```

```python
# kodoku/engine/events.py
Emitter = Callable[[str, dict[str, Any]], Awaitable[None]]  # (type, payload)
```

---

## Task 1: LLM client protocol, fake, and LiteLLM implementation

**Files.** `kodoku/llm/__init__.py`, `kodoku/llm/base.py`, `kodoku/llm/fake.py`,
`kodoku/llm/litellm_client.py`, `backend/tests/test_llm.py`. Add `litellm` to
`backend/pyproject.toml` `[project].dependencies` (latest stable; pin it) and
`pip install -e ".[dev]"` into the venv.

**`base.py`.** `LLMClient` as a `@runtime_checkable` `Protocol` with the exact
signatures above. `complete` returns the model's text (caller parses JSON when
`json_object=True`); `stream` is a sync method returning an `AsyncIterator[str]`.

**`fake.py`.** `FakeLLMClient` for tests. Constructor:
`FakeLLMClient(completions: list[str] | None = None, chunks: list[str] | None = None)`.
- `complete` pops the next string from `completions` (FIFO); raises
  `AssertionError("FakeLLMClient.complete exhausted")` if empty. Records each
  `(system, prompt)` call in `self.calls: list[tuple[str, str]]`.
- `stream` yields each string in `chunks` in order (default `["", ]` → yields
  nothing meaningful; tests pass explicit chunks).
- Helper classmethod `from_json(objs: list[dict])` → builds a client whose
  `completions` are `json.dumps(o)` for each obj. Convenience for step tests.

**`litellm_client.py`.** `LiteLLMClient(model: str, temperature: float = 0.7)`.
- `complete`: `await litellm.acompletion(model=..., messages=[{system},{user}],
  temperature=..., response_format={"type":"json_object"} if json_object else None)`;
  return `resp.choices[0].message.content or ""`.
- `stream`: `await litellm.acompletion(..., stream=True)`; `async for chunk` →
  yield `chunk.choices[0].delta.content` when truthy.
- Add `ponytail:` comment: unverified against a live provider this session.

**Tests (`test_llm.py`).** No DB needed.
- `FakeLLMClient.complete` returns scripted strings in order and records calls.
- Exhausting `completions` raises.
- `from_json` round-trips: `json.loads(await c.complete(...)) == obj`.
- `stream` yields the provided chunks in order (collect with `async for`).
- `isinstance(FakeLLMClient(), LLMClient)` is True (runtime_checkable protocol).

**Verify.** `mypy kodoku/llm`, `ruff check kodoku/llm tests/test_llm.py`,
`pytest tests/test_llm.py`.

---

## Task 2: JSON-parse helper + expand and evaluate steps

**Files.** `kodoku/engine/__init__.py`, `kodoku/engine/steps/__init__.py`,
`kodoku/engine/steps/parse.py`, `kodoku/engine/steps/expand.py`,
`kodoku/engine/steps/evaluate.py`, `kodoku/engine/prompts/__init__.py`,
`kodoku/engine/prompts/expand.md`, `kodoku/engine/prompts/evaluate.md`,
`backend/tests/test_steps_expand_evaluate.py`.

**`parse.py`.** `class StepError(RuntimeError)`. 
`async def parse_json(llm, *, system, prompt, model_cls, retries=2) -> ModelT`:
call `llm.complete(system=, prompt=, json_object=True)`; `model_cls.model_validate_json`.
On `ValidationError`/`json.JSONDecodeError`, retry up to `retries` times,
appending the prior error text to the prompt ("Your previous reply was invalid:
<err>. Return ONLY valid JSON matching the schema."). After `retries`
exhausted, raise `StepError`. Generic over `model_cls` (use `TypeVar` bound to
`BaseModel`).

**`expand.py`.** `async def expand(llm, *, goal, parent_title, parent_content,
branching_factor) -> list[Candidate]`. Load `prompts/expand.md`, format with the
inputs and `branching_factor`, call `parse_json(..., model_cls=ExpandResult)`,
return `result.candidates`. If the model returns more than `branching_factor`,
truncate; if fewer, accept as-is (do not pad).

**`evaluate.py`.** `async def evaluate(llm, *, goal, candidate_title,
candidate_content) -> EvaluationResult`. Load `prompts/evaluate.md`, format,
`parse_json(..., model_cls=EvaluationResult)`. Clamp `score` into `[0, 10]`.

**Prompts.** Markdown with a clear instruction and an explicit JSON schema block.
`expand.md` asks for exactly `{branching_factor}` distinct candidates as
`{"candidates":[{"title","content"}]}`. `evaluate.md` asks for
`{"score":0-10,"critique","dimensions":{feasibility,novelty,impact,effort,fit}}`.
Load templates with `importlib.resources` or `Path(__file__).parent`.

**Tests.** Use `FakeLLMClient.from_json`.
- `expand` with a fake returning 3 candidates → returns 3 `Candidate`s with
  titles/contents; over-long list truncated to `branching_factor`.
- `evaluate` returns parsed score/critique/dimensions; out-of-range score clamped.
- `parse_json` retry: fake `completions=["not json", '{"candidates":[]}']` →
  succeeds on the 2nd; with only bad replies → raises `StepError`.

**Verify.** `mypy kodoku/engine`, `ruff check`, `pytest tests/test_steps_expand_evaluate.py`.

---

## Task 3: decide step (deterministic) + synthesize step (streaming)

**Files.** `kodoku/engine/steps/decide.py`, `kodoku/engine/steps/synthesize.py`,
`kodoku/engine/prompts/synthesize.md`, `backend/tests/test_steps_decide_synthesize.py`.

**`decide.py`.** Pure, no LLM. `KEEP_THRESHOLD = 6.0` (module const;
`ponytail:` comment — tune later / make config-driven if needed).
`def decide(scored: list[tuple[UUID, float]], *, depth: int, max_depth: int)
-> Decision`:
- `keep` = ids with `score >= KEEP_THRESHOLD`. If none qualify, keep the single
  highest-scoring id (so synthesis always has material).
- `prune` = all ids not in `keep`.
- `expand` = `keep` if `depth < max_depth` else `[]` (a candidate at `depth`
  expands into `depth+1` nodes; stop once `depth >= max_depth`).
- Preserve input order in all three lists.

**`synthesize.py`.** `def synthesize(llm, *, goal, kept) -> AsyncIterator[str]`
where `kept: list[tuple[str, str]]` is `(title, content)` of kept nodes. Load
`prompts/synthesize.md`, format with the goal and a bulleted list of kept ideas,
return `llm.stream(system=, prompt=)`. (Streaming, plain text — NOT JSON.)

**`synthesize.md`.** Instruction to write the single strongest final
recommendation grounded in the kept ideas, as prose.

**Tests.**
- `decide`: scores `[(a,8),(b,5),(c,7)]`, depth 1, max_depth 3 →
  keep `[a,c]`, prune `[b]`, expand `[a,c]`.
- `decide` all-below-threshold `[(a,3),(b,4)]` → keep `[b]` (highest), prune `[a]`.
- `decide` at `depth == max_depth` → `expand == []`.
- `synthesize`: `FakeLLMClient(chunks=["Build ", "the buddy."])` → collecting the
  async iterator yields `["Build ", "the buddy."]`.

**Verify.** `mypy kodoku/engine`, `ruff check`, `pytest tests/test_steps_decide_synthesize.py`.

---

## Task 4: DecisionEngine state machine + SessionRunner registry + events

**Files.** `kodoku/engine/events.py`, `kodoku/engine/runner.py`,
`kodoku/engine/state_machine.py`, `backend/tests/test_engine.py`.

**`events.py`.** Event-type string constants (the nine names from Global
Constraints) and the `Emitter` type alias. Factory
`def make_db_emitter(db: AsyncSession, session_id: UUID) -> Emitter` returning an
async `(type, payload)` callable that calls `emit_event(db, session_id, type, payload)`.

**`state_machine.py`.** `class DecisionEngine`. Constructor:
`DecisionEngine(db: AsyncSession, session: SessionModel, llm: LLMClient,
emit: Emitter, *, should_stop: Callable[[], bool] = lambda: False)`.
- Holds an in-memory `deque[UUID]` frontier.
- `async def run(self) -> None`: the whole loop, wrapped in try/except.
  1. status=`running`, `current_step`="expanding"; emit `session.started`;
     emit `engine.state_changed {from:"root",to:"expanding"}`; seed frontier with
     the root node id (the `kind=='root'` node). Commit.
  2. While frontier and not `should_stop()`:
     - pop `parent_id`; load parent node.
     - `cands = await expand(llm, goal=session.goal, parent_title=parent.title,
       parent_content=parent.content, branching_factor=config.branching_factor)`.
     - Insert a `Node` per candidate (`kind=candidate`, `status=active`,
       `depth=parent.depth+1`, parent_id=parent.id). Flush. Emit `node.created`
       with `{id,session_id,parent_id,depth,kind,title,content,status}` per child.
     - For each child: `ev = await evaluate(...)`; insert `Evaluation`
       (`model=config.model`); emit `evaluation.completed`
       `{node_id,score,critique,dimensions}`.
     - `decision = decide([(child.id, ev.score) ...], depth=parent.depth+1,
       max_depth=config.max_depth)`.
     - Mark kept children `status=kept`, pruned `status=pruned`; emit
       `node.updated {id,status}` for each. Mark parent `status=expanded`; emit
       `node.updated`. Extend frontier with `decision.expand`. Commit.
  3. If `should_stop()` tripped: status=`paused`; commit; return (no done event).
  4. Synthesis: gather all `status=kept` nodes (title,content). status=
     `running`/current_step="synthesizing"; emit `engine.state_changed`.
     `text = ""`; `async for delta in synthesize(llm, goal=, kept=): text += delta;
     emit synthesis.streaming {delta}`. Set `session.final_synthesis = text`;
     emit `synthesis.completed {text}`.
  5. status=`done`, current_step=None; emit `session.done`. Commit.
  - On any exception: status=`error`; emit `session.error {message}`; commit;
    re-raise only after persisting (so the API/runner sees it). Use a nested
    try so a failed commit doesn't mask the original error.
- Config read from `session.config` dict (`branching_factor`, `max_depth`,
  `model`, `temperature`) with the SessionConfig defaults if missing.

**`runner.py`.** `class SessionRunner` (module singleton `runner`):
- `self._tasks: dict[UUID, asyncio.Task]`, `self._stop: set[UUID]`.
- `def start(self, session_id, coro) -> None`: create `asyncio.create_task(coro)`,
  store; on completion callback, discard from `_tasks` and `_stop`.
- `def should_stop(self, session_id) -> bool`: `session_id in self._stop`.
- `def interrupt(self, session_id) -> bool`: add to `_stop`; return whether a
  task was running.
- `def is_running(self, session_id) -> bool`.
- `async def join(self, session_id) -> None`: await the task if present (test helper).

**Tests (`test_engine.py`).** Use the `db_session` fixture + a real `SessionModel`
with a root node (create via `SessionRepository.create`). Pass a `FakeLLMClient`
scripted for the run and a recording emitter (`events: list[tuple[str,dict]]`).
- Full run, `branching_factor=2, max_depth=2`: script expand→evaluate JSON for
  each parent. Assert: candidate Nodes persisted with correct depths; Evaluations
  persisted; `session.final_synthesis` set; `session.status == "done"`; the
  recorded event sequence starts `session.started` and ends `session.done` and
  contains the right counts of `node.created`/`evaluation.completed`.
- Decide pruning reflected: at least one node ends `status=="pruned"`, kept ones
  `"kept"`, parents `"expanded"`.
- Error path: a `FakeLLMClient` that raises (empty completions) → `session.status
  == "error"` and a `session.error` event recorded.
- `should_stop=lambda: True` from the start → engine sets `status=="paused"`,
  emits no `session.done`.
- `SessionRunner`: `interrupt` adds to stop-set and `should_stop` reads it;
  `interrupt` on an unknown id returns False.

**Verify.** `mypy kodoku/engine`, `ruff check`, `pytest tests/test_engine.py`.

---

## Task 5: /run and /interrupt endpoints + LLM factory

**Files.** `kodoku/llm/factory.py`, `kodoku/api/run.py`,
`backend/tests/test_run_api.py`; wire `run_router` into `kodoku/main.py`.

**`factory.py`.** `def make_llm_client(config: dict[str, Any]) -> LLMClient`:
build `LiteLLMClient(model=config["model"], temperature=config.get("temperature",0.7))`.
Expose as a FastAPI dependency `def get_llm_factory() -> Callable[[dict], LLMClient]`
returning `make_llm_client`, so tests override it to inject `FakeLLMClient`.

**`run.py`.** Router `prefix="/sessions/{session_id}"`, tag "run".
- `POST /run` → 202. Load session (404 if missing). If `status` not in
  `{draft, paused, error}` → 409. Build a fresh `AsyncSession` from
  `get_sessionmaker()` for the engine (NOT the request session — the request
  ends before the task does). Build llm via the injected factory from
  `session.config`. Construct `DecisionEngine` with `make_db_emitter` and
  `runner.should_stop` bound to this id. `runner.start(id, engine.run())`.
  Return `{"status": "running"}`.
- `POST /interrupt` → 202. `runner.interrupt(id)`; return `{"interrupted": bool}`.
- The engine's own session must be closed when the run ends — wrap
  `engine.run()` in a small coroutine that `async with sessionmaker() as s:`
  and closes/commits. Put that wrapper in `run.py` (or a helper in runner).

**Tests (`test_run_api.py`).** Override `get_db` (test engine) AND
`get_llm_factory` to return a `FakeLLMClient` scripted for a tiny run
(`branching_factor=1, max_depth=1` via the session's config — create the session
with that config). Because the engine runs as a background task on the same
event loop, await completion with `await runner.join(session_id)` (import the
singleton), then assert via REST:
- `POST /run` returns 202; after join, `GET /sessions/{id}` shows `status=="done"`
  and ≥1 candidate node; `GET /sessions/{id}/events` replay contains
  `session.started` … `session.done`.
- `POST /run` on an already-`running`/non-resumable session → 409. (Set status
  to `running` directly in the DB as the existing API test does.)
- `POST /interrupt` returns 202 with an `interrupted` boolean.

**Verify.** `mypy kodoku`, `ruff check kodoku tests`, full `pytest`.

---

## Task 6: Frontend Run controls

**Files.** `frontend/lib/api/client.ts` (add `runSession`, `interruptSession`),
`frontend/app/s/[sessionId]/SessionGraphView.tsx` (add Run / Interrupt buttons).
No contract types needed (endpoints return small ad-hoc JSON); use plain
`fetch`-based methods returning `void`.

- `api.runSession(id)` → `POST /sessions/${id}/run`; `api.interruptSession(id)`
  → `POST /sessions/${id}/interrupt`.
- In `SessionGraphView`, add a primary **Run** button (calls `runSession`,
  disabled while `status === "running"`) and an **Interrupt** button (visible
  only while `status === "running"`, calls `interruptSession`). Keep the existing
  status badge, live indicator, and the M3 "Emit debug events" button (dev aid).
- The existing reducer already folds `node.created` / `evaluation.completed` /
  `synthesis.streaming` / `session.*`, so a real run streams into the graph with
  no reducer changes. Do not modify the reducer or store.

**Verify.** `npm run typecheck` and `npm run lint` (both clean). No FE test
harness exists — visual confirmation is deferred to the manual M4 run.

---

## Out of scope (this milestone)

- Live provider smoke test (Ollama / Anthropic) — spec M4.11, deferred.
- `AWAITING_HUMAN` / checkpoints / `/resume` — M5.
- Any change to M3 WS/graph/reducer beyond adding the two API methods + buttons.
