# Kodoku Architecture

Long-form architecture documentation lives here. The authoritative design
spec is `docs/superpowers/specs/2026-05-14-kodoku-mvp-design.md`. This file
is filled in as milestones land and accumulates diagrams, decision records,
and operational notes.

## Status

- M1 — Skeleton + contracts: ✅ complete
- M2 — Domain model + REST CRUD: ✅ complete
- M3 — React Flow graph + WebSocket plumbing: ✅ complete
- M4 — DecisionEngine + LLM abstraction: ✅ complete (live-provider smoke M4.11 deferred — engine exercised via FakeLLMClient)
- Phase A — BYOK + multi-model + parallel evaluate + prompt safety: ✅ complete
  (per-role models, BYOK settings page, `litellm.acompletion` per-call keys,
  concurrent evaluate, brace-safe prompts. Live run dogfooded via the settings
  page with a real key. Router/budget deferred to Phase B.)
- Next — resume correctness (DB-driven frontier rebuild; fixes dup-node on
  re-run) + CI, then M5 — human-in-the-loop checkpoints: not started
- M6 — Provider polish + export + deploy: not started
