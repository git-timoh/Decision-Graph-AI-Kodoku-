"""Domain enums — string-valued so they serialise straight into JSON / DB."""
from __future__ import annotations

from enum import StrEnum


class SessionStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    DONE = "done"
    ERROR = "error"
    PAUSED = "paused"


class NodeKind(StrEnum):
    ROOT = "root"
    CANDIDATE = "candidate"
    SYNTHESIS = "synthesis"


class NodeStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PRUNED = "pruned"
    KEPT = "kept"
    EXPANDED = "expanded"


class CheckpointKind(StrEnum):
    POST_EXPAND = "post_expand"
    POST_EVALUATE = "post_evaluate"
    PRE_SYNTHESIS = "pre_synthesis"
