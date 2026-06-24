from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kodoku.api.dtos import (
    EvaluationDTO,  # noqa: F401
    NodeDTO,  # noqa: F401
    SessionConfig,
    SessionCreate,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)


def test_session_config_defaults() -> None:
    cfg = SessionConfig()
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.branching_factor == 3
    assert cfg.max_depth == 3
    assert cfg.temperature == 0.7


def test_session_config_rejects_bad_model_string() -> None:
    with pytest.raises(ValidationError):
        SessionConfig(model="not a valid model string")


def test_session_config_branching_factor_bounds() -> None:
    with pytest.raises(ValidationError):
        SessionConfig(branching_factor=0)
    with pytest.raises(ValidationError):
        SessionConfig(branching_factor=11)


def test_session_create_requires_goal() -> None:
    with pytest.raises(ValidationError):
        SessionCreate(goal="too short")


def test_session_create_title_optional() -> None:
    body = SessionCreate(goal="Brainstorm side-project ideas combining AI and music.")
    assert body.title is None
    assert body.config is None


def test_session_create_with_full_payload() -> None:
    body = SessionCreate(
        goal="Brainstorm side-project ideas combining AI and music.",
        title="AI + music projects",
        config=SessionConfig(branching_factor=4, max_depth=2),
    )
    assert body.title == "AI + music projects"
    assert body.config is not None
    assert body.config.branching_factor == 4


def test_session_update_allows_partial() -> None:
    body = SessionUpdate(title="renamed")
    assert body.title == "renamed"
    assert body.config is None


def test_session_response_roundtrip_uuid_and_datetime() -> None:
    sid = uuid4()
    now = datetime.now(UTC)
    payload = {
        "id": str(sid),
        "user_id": "local",
        "title": "t",
        "goal": "goal goal goal goal goal",
        "status": "draft",
        "config": {"model": "anthropic/claude-sonnet-4-6"},
        "current_step": None,
        "final_synthesis": None,
        "cost_usd": 0.0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    parsed = SessionResponse.model_validate(payload)
    assert parsed.id == sid
    assert parsed.status == "draft"


def test_session_detail_response_bundles_nested() -> None:
    sid = uuid4()
    nid = uuid4()
    now = datetime.now(UTC)
    payload = {
        "id": sid,
        "user_id": "local",
        "title": "t",
        "goal": "goal goal goal goal goal",
        "status": "draft",
        "config": {},
        "current_step": None,
        "final_synthesis": None,
        "cost_usd": 0.0,
        "created_at": now,
        "updated_at": now,
        "nodes": [
            {
                "id": nid,
                "session_id": sid,
                "parent_id": None,
                "depth": 0,
                "kind": "root",
                "title": "Root",
                "content": "goal goal goal goal goal",
                "status": "active",
                "model": None,
                "created_at": now,
            }
        ],
        "evaluations": [],
        "checkpoints": [],
    }
    detail = SessionDetailResponse.model_validate(payload)
    assert len(detail.nodes) == 1
    assert detail.nodes[0].kind == "root"


def test_session_list_item_omits_heavy_fields() -> None:
    """List endpoint returns only the columns the sidebar needs."""
    fields = set(SessionListItem.model_fields.keys())
    assert fields == {
        "id",
        "title",
        "status",
        "current_step",
        "created_at",
        "updated_at",
    }


def test_branch_models_defaults_none() -> None:
    assert SessionConfig().branch_models is None


def test_branch_models_valid_list() -> None:
    cfg = SessionConfig(
        branching_factor=3,
        branch_models=["deepseek/deepseek-chat", "", "openai/gpt-4o"],
    )
    assert cfg.branch_models == ["deepseek/deepseek-chat", "", "openai/gpt-4o"]


def test_branch_models_too_many_rejected() -> None:
    with pytest.raises(ValueError, match="branch_models"):
        SessionConfig(branching_factor=1, branch_models=["a/b", "c/d"])


def test_branch_models_bad_id_rejected() -> None:
    with pytest.raises(ValueError, match="branch_models"):
        SessionConfig(branching_factor=2, branch_models=["not a model"])
