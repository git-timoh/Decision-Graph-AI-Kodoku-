"""Pydantic v2 request/response models for the sessions API."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kodoku.domain.enums import (
    CheckpointKind,
    NodeKind,
    NodeStatus,
    SessionStatus,
)

_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._\-:/]*$")


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Expand-role model for this session; None = the Settings expand model.
    #: Evaluate/synthesize always use the Settings role models (fair scoring).
    model: str | None = None
    branching_factor: int = Field(default=3, ge=1, le=10)
    max_depth: int = Field(default=3, ge=1, le=10)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    hitl_mode: Literal["autopilot", "every_branch"] = "autopilot"
    decide_mode: Literal["threshold", "judge"] = "threshold"
    budget_usd: float | None = Field(default=None, ge=0)
    branch_models: list[str] | None = Field(default=None)

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str | None) -> str | None:
        # Require a provider prefix: a slash-less string (e.g. "gpt-4o") would
        # resolve keyless in the BYOK factory and only fail at /run.
        if value is None:
            return value
        if " " in value or "/" not in value or not _MODEL_RE.match(value):
            raise ValueError(
                "model must be a LiteLLM-style 'provider/model' identifier "
                "(e.g. 'anthropic/claude-sonnet-4-6')"
            )
        return value

    @model_validator(mode="after")
    def _validate_branch_models(self) -> SessionConfig:
        if self.branch_models is None:
            return self
        if len(self.branch_models) > self.branching_factor:
            raise ValueError("branch_models cannot have more entries than branching_factor")
        for entry in self.branch_models:
            if entry == "":
                continue
            if " " in entry or "/" not in entry or not _MODEL_RE.match(entry):
                raise ValueError(
                    f"branch_models entry {entry!r} must be a LiteLLM-style "
                    "'provider/model' identifier or ''"
                )
        return self


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=10, max_length=4000)
    title: str | None = Field(default=None, max_length=200)
    config: SessionConfig | None = None


class SessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    config: SessionConfig | None = None


class NodeEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content: str | None = None


class ResumeRequest(BaseModel):
    """Body of `POST /sessions/{id}/resume`.

    `keep ∪ prune` must be a subset of the resolved checkpoint's candidate
    node ids — that check happens in the endpoint, where the checkpoint (and
    therefore its candidate ids) is loaded; the DTO has no DB access so it
    can't validate it itself.
    """

    model_config = ConfigDict(extra="forbid")

    checkpoint_id: UUID
    keep: list[UUID] = Field(default_factory=list)
    prune: list[UUID] = Field(default_factory=list)
    edits: dict[UUID, NodeEdit] = Field(default_factory=dict)


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NodeDTO(_ORM):
    id: UUID
    session_id: UUID
    parent_id: UUID | None
    depth: int
    kind: NodeKind
    title: str
    content: str
    status: NodeStatus
    model: str | None
    created_at: datetime


class EvaluationDTO(_ORM):
    id: UUID
    node_id: UUID
    score: Decimal
    critique: str
    dimensions: dict[str, Any]
    model: str
    created_at: datetime


class CheckpointDTO(_ORM):
    id: UUID
    session_id: UUID
    kind: CheckpointKind
    payload: dict[str, Any]
    decision: dict[str, Any] | None
    resolved_at: datetime | None
    created_at: datetime


class SessionResponse(_ORM):
    id: UUID
    user_id: str
    title: str
    goal: str
    status: SessionStatus
    config: dict[str, Any]
    current_step: str | None
    final_synthesis: str | None
    cost_usd: float
    created_at: datetime
    updated_at: datetime


class SessionListItem(_ORM):
    id: UUID
    title: str
    status: SessionStatus
    current_step: str | None
    created_at: datetime
    updated_at: datetime


class SessionDetailResponse(SessionResponse):
    nodes: list[NodeDTO]
    evaluations: list[EvaluationDTO]
    checkpoints: list[CheckpointDTO]


class SessionCreateResponse(BaseModel):
    session_id: UUID


class WsEvent(BaseModel):
    """A single server-push message; mirrors a row in the `events` journal."""

    id: int
    type: str
    session_id: UUID
    ts: datetime
    payload: dict[str, Any]


PROVIDER_NAMES: tuple[str, ...] = (
    "openrouter",
    "deepseek",
    "openai",
    "anthropic",
    "zhipu",
    "google",
)

MODEL_ROLES: tuple[str, ...] = ("expand", "evaluate", "synthesize")


class ProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set: bool
    hint: str | None = None


class SettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderStatus]
    ollama_base_url: str | None = None
    models: dict[str, str | None]


class SettingsTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    error: str | None = None


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, str | None] | None = None
    ollama_base_url: str | None = None
    models: dict[str, str] | None = None

    @field_validator("providers")
    @classmethod
    def _validate_providers(
        cls, value: dict[str, str | None] | None
    ) -> dict[str, str | None] | None:
        if value is None:
            return value
        unknown = sorted(set(value) - set(PROVIDER_NAMES))
        if unknown:
            raise ValueError(f"unknown provider name(s): {', '.join(unknown)}")
        return value

    @field_validator("models")
    @classmethod
    def _validate_models(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return value
        unknown = sorted(set(value) - set(MODEL_ROLES))
        if unknown:
            raise ValueError(f"unknown model role(s): {', '.join(unknown)}")
        for role, model in value.items():
            if " " in model or not _MODEL_RE.match(model):
                raise ValueError(
                    f"models.{role} must be a LiteLLM-style identifier "
                    "(e.g. 'anthropic/claude-sonnet-4-6')"
                )
        return value
