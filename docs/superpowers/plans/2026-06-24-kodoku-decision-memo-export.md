# Decision-Memo Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a decision session as a downloadable Markdown memo (JSON option) via `GET /sessions/{id}/export` plus an in-app button.

**Architecture:** A pure formatter (`render_markdown`) over the existing `SessionBundle` from `get_bundle` — no schema change, no LLM call. JSON reuses `SessionDetailResponse`. A thin endpoint sets the download header. Frontend adds anchor links that hit the endpoint.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest/httpx (backend); Next.js + React + Tailwind (frontend).

## Global Constraints

- Backend lives under `backend/kodoku/`; tests under `backend/tests/`. Run tests with `pytest` from `backend/`.
- Pydantic models use `from __future__ import annotations` at top of every module.
- Endpoint follows existing `sessions.py` patterns: `Depends(_repo)`, 404 via `HTTPException` from `SessionNotFound`.
- `SessionBundle` fields: `.session` (ORM `Session`: `title`, `goal`, `status`, `config` dict, `cost_usd`, `final_synthesis`, `created_at`, `updated_at`), `.nodes` (sorted by `(depth, created_at)`), `.evaluations`, `.checkpoints`.
- Node statuses: `pending`, `active`, `pruned`, `kept`, `expanded`. Node kinds: `root`, `candidate`, `synthesis`.
- Frontend has no JS test framework — verify the button manually by running the app.

---

### Task 1: Markdown formatter (pure)

**Files:**
- Create: `backend/kodoku/export/__init__.py` (empty)
- Create: `backend/kodoku/export/memo.py`
- Test: `backend/tests/test_export_memo.py`

**Interfaces:**
- Consumes: `SessionBundle` from `kodoku.repo.sessions`; `NodeKind` from `kodoku.domain.enums`.
- Produces: `render_markdown(bundle: SessionBundle) -> str`, `_slug(text: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_export_memo.py
from __future__ import annotations

from decimal import Decimal

from kodoku.db.models import Evaluation, Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import NodeKind, NodeStatus, SessionStatus
from kodoku.export.memo import _slug, render_markdown
from kodoku.repo.sessions import SessionBundle


def _bundle(*, synthesis: str | None) -> SessionBundle:
    session = SessionModel(
        title="Pick a database",
        goal="Choose a datastore for the new service.",
        status=SessionStatus.DONE.value,
        config={
            "model": "anthropic/claude-sonnet-4-6",
            "branching_factor": 3,
            "max_depth": 3,
            "decide_mode": "judge",
            "hitl_mode": "autopilot",
        },
        cost_usd=Decimal("0.1234"),
        final_synthesis=synthesis,
    )
    root = Node(
        session_id=session.id, parent_id=None, depth=0,
        kind=NodeKind.ROOT.value, title="root", content="goal",
        status=NodeStatus.EXPANDED.value,
    )
    kept = Node(
        session_id=session.id, parent_id=root.id, depth=1,
        kind=NodeKind.CANDIDATE.value, title="Postgres",
        content="Relational, mature.", status=NodeStatus.KEPT.value,
    )
    pruned = Node(
        session_id=session.id, parent_id=root.id, depth=1,
        kind=NodeKind.CANDIDATE.value, title="Flat files",
        content="No server.", status=NodeStatus.PRUNED.value,
    )
    ev = Evaluation(
        node_id=kept.id, score=Decimal("8.5"),
        critique="Strong consistency guarantees.", dimensions={}, model="x",
    )
    return SessionBundle(
        session=session, nodes=[root, kept, pruned],
        evaluations=[ev], checkpoints=[],
    )


def test_markdown_contains_goal_recommendation_and_scores() -> None:
    md = render_markdown(_bundle(synthesis="Use Postgres."))
    assert "Choose a datastore for the new service." in md
    assert "Use Postgres." in md
    assert "Postgres — KEPT (score 8.5)" in md
    assert "Strong consistency guarantees." in md
    assert "Flat files — PRUNED" in md
    assert "root" not in md.split("## Branches")[1]  # root excluded from branches


def test_markdown_handles_missing_synthesis() -> None:
    md = render_markdown(_bundle(synthesis=None))
    assert "_(run not yet complete)_" in md


def test_slug_is_filename_safe() -> None:
    assert _slug("Pick a DB!! (v2)") == "pick-a-db-v2"
    assert _slug("") == "session"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_export_memo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kodoku.export'`

- [ ] **Step 3: Create the empty package init**

```python
# backend/kodoku/export/__init__.py
```

(empty file)

- [ ] **Step 4: Write the formatter**

```python
# backend/kodoku/export/memo.py
"""Render a decision session as a Markdown memo. Pure: no DB, no LLM."""
from __future__ import annotations

import re
from datetime import datetime
from itertools import groupby

from kodoku.domain.enums import NodeKind
from kodoku.repo.sessions import SessionBundle


def _fmt_dt(dt: datetime | None) -> str:
    return dt.isoformat(timespec="minutes") if dt else "—"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "session"


def render_markdown(bundle: SessionBundle) -> str:
    s = bundle.session
    cfg = s.config or {}
    # ponytail: last-wins; in practice <=1 evaluation per node.
    eval_by_node = {e.node_id: e for e in bundle.evaluations}

    lines: list[str] = [
        f"# {s.title}",
        "",
        f"**Goal:** {s.goal}",
        "",
        "## Recommendation",
        "",
        s.final_synthesis or "_(run not yet complete)_",
        "",
        "## Run details",
        "",
        f"- **Status:** {s.status}",
        f"- **Created:** {_fmt_dt(s.created_at)}",
        f"- **Updated:** {_fmt_dt(s.updated_at)}",
        f"- **Total cost:** ${float(s.cost_usd or 0):.4f}",
        f"- **Model:** {cfg.get('model', '—')}",
        f"- **Branching factor:** {cfg.get('branching_factor', '—')}",
        f"- **Max depth:** {cfg.get('max_depth', '—')}",
        f"- **Decide mode:** {cfg.get('decide_mode', '—')}",
        f"- **HITL mode:** {cfg.get('hitl_mode', '—')}",
    ]
    if cfg.get("budget_usd") is not None:
        lines.append(f"- **Budget:** ${float(cfg['budget_usd']):.4f}")
    branch_models = [m for m in (cfg.get("branch_models") or []) if m]
    if branch_models:
        lines.append(f"- **Per-branch models:** {', '.join(branch_models)}")

    lines += ["", "## Branches & reasoning", ""]

    candidates = [n for n in bundle.nodes if n.kind == NodeKind.CANDIDATE.value]
    if not candidates:
        lines.append("_(no candidate branches)_")
    else:
        # bundle.nodes is pre-sorted by (depth, created_at) so groupby is contiguous.
        for depth, group in groupby(candidates, key=lambda n: n.depth):
            lines += [f"### Depth {depth}", ""]
            for n in group:
                ev = eval_by_node.get(n.id)
                score = f" (score {float(ev.score):g})" if ev else ""
                lines += [f"#### {n.title} — {n.status.upper()}{score}", "", n.content, ""]
                if ev and ev.critique:
                    lines += [f"> {ev.critique}", ""]

    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_export_memo.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/kodoku/export backend/tests/test_export_memo.py
git commit -m "feat(export): pure render_markdown decision-memo formatter"
```

---

### Task 2: Export endpoint

**Files:**
- Modify: `backend/kodoku/api/sessions.py` (add imports + `export_session` route)
- Test: `backend/tests/test_sessions_api.py` (append tests; reuses the `client` fixture there)

**Interfaces:**
- Consumes: `render_markdown`, `_slug` from `kodoku.export.memo`; existing `get_bundle`, `SessionDetailResponse`, `SessionResponse`.
- Produces: `GET /sessions/{session_id}/export?format=md|json` → `Response` with `Content-Disposition: attachment`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_sessions_api.py`)

```python
@pytest.mark.asyncio
async def test_export_md_is_downloadable_markdown(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan an export of the decision memo."},
    )).json()

    resp = await client.get(f"/sessions/{created['session_id']}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=" in resp.headers["content-disposition"]
    assert ".md" in resp.headers["content-disposition"]
    assert "## Recommendation" in resp.text


@pytest.mark.asyncio
async def test_export_json_returns_bundle_shape(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan an export of the decision memo as json."},
    )).json()

    resp = await client.get(f"/sessions/{created['session_id']}/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["id"] == created["session_id"]
    assert body["nodes"][0]["kind"] == "root"


@pytest.mark.asyncio
async def test_export_unknown_id_returns_404(client: AsyncClient) -> None:
    import uuid

    resp = await client.get(f"/sessions/{uuid.uuid4()}/export")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_bad_format_returns_422(client: AsyncClient) -> None:
    created = (await client.post(
        "/sessions",
        json={"goal": "Plan an export with a bad format value."},
    )).json()

    resp = await client.get(f"/sessions/{created['session_id']}/export?format=pdf")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_sessions_api.py -k export -v`
Expected: FAIL — 404 on `/export` (route not defined) / 422 cases not yet enforced.

- [ ] **Step 3: Add imports to `sessions.py`**

At the top, extend the `typing` import and add the memo import. The `from typing import Literal` line and:

```python
from kodoku.export.memo import _slug, render_markdown
```

(`Response`, `status`, `HTTPException`, `Depends`, `UUID`, `SessionDetailResponse`, `SessionResponse` are already imported.)

- [ ] **Step 4: Add the route** (place after `get_session`, before `update_session`)

```python
@router.get("/{session_id}/export")
async def export_session(
    session_id: UUID,
    format: Literal["md", "json"] = "md",
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> Response:
    try:
        bundle = await repo.get_bundle(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    slug = _slug(bundle.session.title)
    short = str(session_id)[:8]
    if format == "json":
        detail = SessionDetailResponse.model_validate({
            **SessionResponse.model_validate(bundle.session).model_dump(),
            "nodes": bundle.nodes,
            "evaluations": bundle.evaluations,
            "checkpoints": bundle.checkpoints,
        })
        content = detail.model_dump_json()
        media_type = "application/json"
        ext = "json"
    else:
        content = render_markdown(bundle)
        media_type = "text/markdown"
        ext = "md"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="kodoku-{slug}-{short}.{ext}"',
        },
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_sessions_api.py -k export -v`
Expected: PASS (4 tests). Then run the full file: `pytest tests/test_sessions_api.py -v` — all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/kodoku/api/sessions.py backend/tests/test_sessions_api.py
git commit -m "feat(export): GET /sessions/{id}/export endpoint (md|json)"
```

---

### Task 3: Frontend Export button

**Files:**
- Modify: `frontend/app/s/[sessionId]/SessionGraphView.tsx` (add export links in the header action group)

**Interfaces:**
- Consumes: `API_BASE` (already defined in the file), `sessionId` prop, the `GET /sessions/{id}/export` endpoint from Task 2.
- Produces: two anchor links in the header that download the memo.

- [ ] **Step 1: Add the export links**

In the header action `<div className="ml-auto flex items-center gap-2">`, insert before the `Emit debug events` button:

```tsx
<a
  href={`${API_BASE}/sessions/${sessionId}/export?format=md`}
  className="inline-flex h-8 items-center rounded-md border border-input px-3 text-xs font-medium hover:bg-accent"
>
  Export
</a>
<a
  href={`${API_BASE}/sessions/${sessionId}/export?format=json`}
  className="text-xs text-muted-foreground hover:underline"
>
  json
</a>
```

- [ ] **Step 2: Verify by running the app**

Start the frontend detached (per project convention):
```powershell
Start-Process cmd "/c npm run dev" -WorkingDirectory frontend
```
With the backend running, open a session page (`/s/<id>`), click **Export** → a `.md` file downloads; click **json** → a `.json` file downloads. Open the `.md` and confirm it has `## Recommendation` and `## Branches & reasoning`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/s/[sessionId]/SessionGraphView.tsx
git commit -m "feat(export): Export memo links on the session page"
```

---

## Self-Review

- **Spec coverage:** Markdown formatter (Task 1) ✓; JSON via `SessionDetailResponse` (Task 2) ✓; endpoint with `format` param + attachment header + 404/422 (Task 2) ✓; in-app button (Task 3) ✓; tests (Tasks 1–2) ✓; deliberate simplifications (no HITL section, reuse detail DTO) honored ✓.
- **Placeholders:** none — all code shown in full.
- **Type consistency:** `render_markdown(bundle: SessionBundle) -> str` and `_slug(text) -> str` defined in Task 1, consumed by Task 2 with matching names. `format: Literal["md","json"]` consistent between endpoint and frontend query strings.
- **Note:** per-role models (expand/evaluate/synth) live in global app settings, not `session.config`; the memo shows the session's default `model` + per-branch overrides only — accurate to available data.
