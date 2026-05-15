from __future__ import annotations

import pytest

from kodoku.domain.enums import (
    CheckpointKind,
    NodeKind,
    NodeStatus,
    SessionStatus,
)


def test_session_status_values() -> None:
    assert SessionStatus.DRAFT.value == "draft"
    assert SessionStatus.RUNNING.value == "running"
    assert SessionStatus.AWAITING_HUMAN.value == "awaiting_human"
    assert SessionStatus.DONE.value == "done"
    assert SessionStatus.ERROR.value == "error"
    assert SessionStatus.PAUSED.value == "paused"


def test_node_kind_values() -> None:
    assert {k.value for k in NodeKind} == {"root", "candidate", "synthesis"}


def test_node_status_values() -> None:
    assert {s.value for s in NodeStatus} == {
        "pending",
        "active",
        "pruned",
        "kept",
        "expanded",
    }


def test_checkpoint_kind_values() -> None:
    assert {c.value for c in CheckpointKind} == {
        "post_expand",
        "post_evaluate",
        "pre_synthesis",
    }


def test_enums_are_str_subclass() -> None:
    """JSON-friendly: each enum is a str so it serialises directly."""
    assert isinstance(SessionStatus.DRAFT, str)
    assert SessionStatus.DRAFT == "draft"
