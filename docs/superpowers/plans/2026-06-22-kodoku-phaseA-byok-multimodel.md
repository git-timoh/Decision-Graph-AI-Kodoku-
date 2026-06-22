# Kodoku Phase A — BYOK + multi-model + parallel evaluate + prompt-safety

Builds on M4 (merged to main). Branch off main as `phaseA-byok`. Makes the
engine usable with real models, configured by the user, without the two
shipped bugs the review caught.

**Goal.** A user pastes provider keys (or one OpenRouter key) into a settings
page, picks a model per role, runs a session against a real model. Evaluations
run concurrently. Goals containing `{`/`}` no longer crash prompts.

**Deliberately NOT in Phase A (YAGNI):** `litellm.Router`, fallback chains,
cost-based routing, budget caps + live cost UI (Phase B), the smart-decide
judge (Phase B), per-node model override (Phase D), resume-frontier rebuild
(next step after Phase A). Phase A uses plain `litellm.acompletion` with
per-call `api_key`/`api_base`.

## Global Constraints (bind every task)

- Python 3.12, `from __future__ import annotations` atop every module.
- mypy `strict = true`; ruff line-length 100, rules `E,F,I,B,UP,W`. Zero errors.
- Match existing style (async SQLAlchemy 2.x `Mapped`, Pydantic v2 `ConfigDict`,
  `StrEnum`). Docker Postgres up; tests use the existing `conftest.py` fixtures.
- venv interpreter: `backend/.venv/Scripts/python.exe`.
- **Secrets never echoed.** `GET /settings` returns presence + a masked hint
  (last 4 chars), never the full key. Keys live only in the local DB; nothing
  is sent anywhere except the provider the user configured.
- Frontend: `npm run typecheck` + `npm run lint` clean; regenerate
  `lib/types/contracts.ts` after any DTO change.

## Shared design decisions (authoritative)

- **Roles:** `expand`, `evaluate`, `synthesize`. Each has a configured model
  string (LiteLLM format). (`judge` arrives in Phase B and will reuse this
  shape.) Defaults: expand = a strong model, evaluate/synthesize = a cheap one.
- **Provider key resolution.** A model string's provider prefix
  (`deepseek/…`, `openrouter/…`, `anthropic/…`, `openai/…`, `zhipu/…` or
  `ollama/…`) maps to a stored key (and base URL for Ollama). The factory
  passes `api_key`/`api_base` straight into `litellm.acompletion`. If no stored
  key, fall back to the matching env var (so docker/.env dev still works).
- **Per-role clients.** The factory returns a `RoleClients` mapping
  (`expand`/`evaluate`/`synthesize` → `LLMClient`), each bound to its role's
  model + resolved key. The engine holds this mapping; each step uses its
  role's client. Tests inject a `RoleClients` of fakes.
- **Settings storage:** one key-value table `app_settings(key TEXT pk, value
  TEXT, updated_at)`. Holds provider keys (`key.openrouter`, `key.deepseek`,
  …), `ollama.base_url`, and role models (`model.expand`, `model.evaluate`,
  `model.synthesize`). Portable to SQLite later.

```python
# kodoku/llm/factory.py
@dataclass(frozen=True, slots=True)
class RoleClients:
    expand: LLMClient
    evaluate: LLMClient
    synthesize: LLMClient
```

---

## Task 1: app_settings store + migration + repo

**Files.** `kodoku/db/models.py` (add `AppSetting`), Alembic revision under
`alembic/versions/`, `kodoku/repo/settings.py`, `backend/tests/test_repo_settings.py`.

- `AppSetting`: `key: Mapped[str]` (primary key, String), `value: Mapped[str]`
  (Text), `updated_at` (timestamptz, server_default now, onupdate now).
- `SettingsRepository(db)`: `async get_all() -> dict[str,str]`,
  `async get(key) -> str | None`, `async upsert(items: dict[str,str]) -> None`
  (insert-or-update each; use `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update`).
- Alembic migration creates the table. Generate with autogenerate, then verify.

**Tests.** upsert then get_all round-trips; upsert overwrites an existing key;
get on missing key returns None.

**Verify.** `alembic upgrade head` clean; `pytest tests/test_repo_settings.py`;
`mypy kodoku`; `ruff check`.

---

## Task 2: settings DTOs + GET/PUT /settings (masked)

**Files.** `kodoku/api/dtos.py` (add settings DTOs), `kodoku/api/settings.py`,
wire `settings_router` into `kodoku/main.py`, `backend/tests/test_settings_api.py`.

- Known keys live in a module list/enum: provider key names
  (`openrouter, deepseek, openai, anthropic, zhipu, google`), `ollama_base_url`,
  and role models (`expand, evaluate, synthesize`).
- `GET /settings` → `{ providers: {openrouter: {set: bool, hint: str|null}, …},
  ollama_base_url: str|null, models: {expand: str|null, evaluate: …, synthesize: …} }`.
  `hint` = last 4 chars of the stored key or null; full secret NEVER returned.
- `PUT /settings` body: optional `providers: {name: key|null}`, `ollama_base_url`,
  `models: {role: model_string}`. A provided key string is stored; `null`
  clears it; an omitted field is left unchanged. Model strings validated with
  the existing `_MODEL_RE` from `dtos.py`. Returns the same masked shape as GET.
- The repo stores provider keys under `key.<name>`, models under `model.<role>`,
  ollama under `ollama.base_url`.

**Tests.** PUT a key then GET → `set: true`, `hint` = last 4, full key absent
from the response body; PUT `null` clears it; PUT a model + GET reflects it;
invalid model string → 422.

**Verify.** `pytest tests/test_settings_api.py`; `mypy kodoku`; `ruff check`;
regenerate `contracts.ts`.

---

## Task 3: per-role client factory with BYOK key resolution

**Files.** `kodoku/llm/factory.py` (rewrite — replaces the M4 single-client
factory), `backend/tests/test_factory.py`. Keep `LiteLLMClient` as-is but allow
it to accept an `api_key`/`api_base` (extend its constructor; it passes them
into `acompletion`). Confirm `litellm.acompletion` accepts `api_key`/`api_base`
kwargs before relying on it.

- `PROVIDER_ENV = {"openrouter": "OPENROUTER_API_KEY", "deepseek":
  "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
  "zhipu": "ZHIPU_API_KEY", "google": "GEMINI_API_KEY"}` (verify exact LiteLLM
  env-var names; correct if different).
- `def provider_of(model: str) -> str`: the substring before the first `/`.
- `async def make_role_clients(settings: SettingsRepository) -> RoleClients`:
  for each role, read `model.<role>` (fall back to a sane default constant if
  unset), resolve the provider key from the store (`key.<provider>`) or the env
  var, resolve Ollama base URL for `ollama/*` models, and build a `LiteLLMClient`
  bound to that model + key. Return the `RoleClients`.
- The M4 `/run` wrapper changes to call `make_role_clients` and pass the mapping
  to the engine (see Task 4 for the engine signature change).

**Tests.** With a `SettingsRepository` over the test DB seeded with a key + role
models, `make_role_clients` returns clients whose `.model` matches the configured
role models and whose resolved key matches the stored key (assert via the
client's stored attributes — do NOT make a network call). Env-var fallback when
a stored key is absent. `provider_of` parses prefixes correctly.

**Verify.** `pytest tests/test_factory.py`; `mypy kodoku`; `ruff check`.

---

## Task 4: parallel evaluate + brace-safe prompt templating

**Files.** `kodoku/engine/state_machine.py` (engine takes `RoleClients`;
parallel evaluate), `kodoku/engine/steps/parse.py` + `expand.py` + `evaluate.py`
+ `synthesize.py` (templating fix), `kodoku/api/run.py` (pass `RoleClients`),
update `backend/tests/test_engine.py` + `test_run_api.py` fixtures to inject a
`RoleClients` of fakes.

**Engine signature.** `DecisionEngine(db, session, clients: RoleClients, emit,
*, should_stop=...)`. `expand` uses `clients.expand`, `evaluate` uses
`clients.evaluate`, `synthesize` uses `clients.synthesize`. Evaluation model
stored on the `Evaluation` row becomes `clients.evaluate.model`.

**Parallel evaluate.** After persisting the candidate nodes, evaluate them
concurrently: `asyncio.gather` over the children guarded by
`asyncio.Semaphore(EVAL_CONCURRENCY)` (`EVAL_CONCURRENCY = 4`, module const,
`ponytail:` comment — make configurable later). **Persist the resulting
`Evaluation` rows and emit `evaluation.completed` sequentially in child order**
after the gather (the LLM calls parallelize; the DB writes/events stay ordered).
Pass the raw float scores into `decide` in the same child order.

**Brace-safe templating.** The steps currently `.format()` templates that embed
the user goal — a goal with `{`/`}` raises. Replace with a brace-safe insertion:
use `string.Template` with `$`-placeholders in the `.md` files and
`Template(text).safe_substitute(...)`, OR keep `.md` literal and `str.replace`
the named placeholders. User-supplied text must never be parsed as a format
string. Add a test with a goal like `Compare {A, B} vs {C}` that previously
broke.

**Tests.** Existing engine tests updated to inject `RoleClients`. New: a run
whose goal contains braces completes without error (RED first: show the old
`.format` path raising on braces, then GREEN). Parallel evaluate: a run with
`branching_factor=3` persists 3 evaluations in child order and emits
`evaluation.completed` in order (assert ordering), with results correct.

**Verify.** `pytest tests/test_engine.py tests/test_run_api.py`; full suite;
`mypy kodoku`; `ruff check`.

---

## Task 5: BYOK settings page (frontend)

**Files.** `frontend/app/settings/page.tsx` (+ a client component for the form),
`frontend/lib/api/client.ts` (`getSettings`, `putSettings`), regenerate
`contracts.ts`, a link to settings from the sidebar or session header.

- Form: one masked field per provider key (show the `hint` when set, allow
  replace/clear), an Ollama base-URL field, and three model selects (expand /
  evaluate / synthesize) with the existing preset list + free-text override.
- A model select is **enabled only if** its provider's key is set (or an
  OpenRouter key is present, which covers everything) or it's an `ollama/*`
  model with a base URL. Otherwise show "add a key for <provider>".
- **Test-connection button** per saved config: calls a minimal backend check
  (a tiny `POST /settings/test` that does one cheap completion against the
  configured `evaluate` model and returns ok/error). Keep it minimal; surface
  the provider error message verbatim. (This is the "smoke-check" win.)
- Match the existing shadcn/Tailwind style (see `NewSessionDialog.tsx`).

**Verify.** `npm run typecheck` + `npm run lint` clean.

---

## Verification / manual smoke (path b — you do this with your own key)

After Tasks 1–5: open `/settings`, paste a **DeepSeek or GLM** key, set
`model.expand`/`evaluate`/`synthesize`, click **Test connection** (expect ok),
create a session with a real goal, click **Run**, and watch a real tree stream
in. This dogfoods the whole setup flow with your own key. No live-LLM test is
committed to CI.

## Out of scope reminders
Router/fallback/budget UI → Phase B. Resume-frontier rebuild + the dup-node
fix → the step right after Phase A. Per-node model override → Phase D.
