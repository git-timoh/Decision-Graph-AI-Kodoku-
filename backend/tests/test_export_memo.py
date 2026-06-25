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
