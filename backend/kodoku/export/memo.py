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
        f"- **Model:** {cfg.get('model') or 'settings default'}",
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
