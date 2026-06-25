# Decision-Memo Export — Design

**Phase:** Productize (first deliverable). Replay mode and packaging are separate later cycles.
**Date:** 2026-06-24
**Status:** Approved (approach A)

## Goal

Let a user export a completed (or in-progress) decision session as a downloadable
artifact: a human-readable Markdown **decision memo** by default, with a JSON
option for tooling. Triggered from a backend endpoint and an in-app button.

## Why

Kodoku produces a graph of branched, scored, critiqued ideas plus a synthesized
recommendation. Today that lives only in the running UI. A memo turns a run into a
shareable, archivable record of *what was decided and why* — the "productize" step
that makes a session useful outside the app.

## Approach (A)

A pure formatter over the data already persisted. No schema changes, no LLM call —
the recommendation already exists in `Session.final_synthesis`.

- **Markdown** is rendered by a new pure function.
- **JSON** reuses the existing `SessionDetailResponse` shape (no bespoke export
  schema).

Rejected alternative (B): LLM-generated memo prose — costs money, is
non-deterministic, and re-summarizes content the LLM already produced. YAGNI.

## Data source

Everything comes from `SessionRepository.get_bundle(session_id) -> SessionBundle`,
which already returns:

- `session`: `goal`, `title`, `status`, `config` (dict), `cost_usd`,
  `final_synthesis`, `created_at`, `updated_at`.
- `nodes`: sorted by `(depth, created_at)`; each has `kind`, `title`, `content`,
  `status` (`kept` / `pruned` / `expanded` / `active` / `pending`), `model`,
  `parent_id`, `depth`.
- `evaluations`: each has `node_id`, `score`, `critique`, `dimensions`, `model`.
- `checkpoints`: present but **not** used by the memo (see Simplifications).

A node's score/critique is found by matching `evaluations` on `node_id`. A node may
have 0 or 1 evaluation in practice; the formatter takes the most recent if more than
one exists.

## Components

### `backend/kodoku/export/memo.py` (new, pure — no DB, no LLM)

```python
def render_markdown(bundle: SessionBundle) -> str: ...
```

- Builds an evaluation lookup `{node_id: Evaluation}` (latest wins).
- Emits the layout below as a single Markdown string.
- The JSON path does not live here — it reuses `SessionDetailResponse`.

A small `_slug(title) -> str` helper (lowercase, non-alphanumeric → `-`, trimmed,
capped ~40 chars) is used by the endpoint for the download filename. It can live in
`memo.py` next to the renderer.

### Endpoint — add to `backend/kodoku/api/sessions.py`

```
GET /sessions/{session_id}/export?format=md|json     (format default: md)
```

- `format=md` → `Response(content=render_markdown(bundle), media_type="text/markdown")`
- `format=json` → the `SessionDetailResponse` (built exactly as `get_session`
  does today), but returned with a download `Content-Disposition`.
- Both set `Content-Disposition: attachment; filename="kodoku-<slug>-<short-id>.<ext>"`
  where `<short-id>` is the first 8 chars of the session UUID.
- Unknown `session_id` → 404 (reuses `get_bundle`'s `SessionNotFound`, same as
  `get_session`).
- Unknown `format` value → 422 via a `Literal["md", "json"]` query param.

No new repository method — `get_bundle` already returns everything.

### Markdown layout

Leads with the answer, then the supporting reasoning.

1. `# <title>` followed by the goal text.
2. `## Recommendation` — `final_synthesis`, or `_(run not yet complete)_` when it
   is `None`.
3. `## Run details` — status; created / last-updated timestamps; total
   `cost_usd`; a config summary (per-role models + per-branch overrides if set,
   branching factor, max depth, decide mode, hitl mode, budget if set).
4. `## Branches & reasoning` — candidate nodes grouped by depth (root excluded; it
   is the goal). For each node: title, a KEPT/PRUNED marker derived from
   `status`, the content, and — when an evaluation exists — `score` and
   `critique`.

### Frontend — Export button

- In `frontend/app/s/[sessionId]/SessionGraphView.tsx`, add an **Export** control
  on the session page.
- Default action downloads the `format=md` endpoint; a small menu/toggle offers
  JSON.
- Implementation: a plain anchor/link to the backend URL (the
  `Content-Disposition` header drives the browser download) — no client-side file
  assembly, no new state. Reuses the existing API base URL from `lib/api/client.ts`.

## Testing

`backend/tests/test_export_memo.py`:

- `render_markdown` over a hand-built `SessionBundle` (a completed run with one
  kept and one pruned candidate) contains: the goal, the recommendation text, the
  kept node's score, and a PRUNED marker for the pruned node.
- `final_synthesis is None` renders the "run not yet complete" placeholder rather
  than crashing.
- Endpoint test: `format=md` returns `text/markdown` with an `attachment`
  Content-Disposition; `format=json` returns the detail bundle shape; unknown id →
  404; bad `format` → 422.

Pure-function tests assert on substrings, not whole-document equality, so layout
tweaks don't churn the tests.

## Deliberate simplifications (ponytail)

- **No HITL/checkpoint audit section.** Node `status` (KEPT / PRUNED) already
  encodes each branch's outcome. Add a "Human decisions" section sourced from
  `checkpoints[].decision` only if an explicit audit trail is later wanted.
- **JSON reuses `SessionDetailResponse`** instead of a dedicated export schema.
- **Filename slug is best-effort**, not collision-proof — the short UUID
  disambiguates.
- **No streaming / pagination.** A single session's bundle is small; render in
  memory.

## Out of scope

Replay mode, packaging (pipx vs docker), re-import of exported JSON, PDF/HTML
output. Each is a later cycle if wanted.
