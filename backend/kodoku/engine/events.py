"""Engine event-type constants and the emitter abstraction.

The DecisionEngine never touches the WebSocket layer directly; it calls an
injected `Emitter` for every observable transition. In production the emitter
is `make_db_emitter`, which journals + broadcasts via `emit_event`. Tests pass
a recording emitter instead, so the engine stays I/O-agnostic and testable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.ws.emit import emit_event

# Event-type string constants — the eleven names the engine emits.
SESSION_STARTED = "session.started"
ENGINE_STATE_CHANGED = "engine.state_changed"
NODE_CREATED = "node.created"
NODE_UPDATED = "node.updated"
EVALUATION_COMPLETED = "evaluation.completed"
SYNTHESIS_STREAMING = "synthesis.streaming"
SYNTHESIS_COMPLETED = "synthesis.completed"
SESSION_DONE = "session.done"
SESSION_ERROR = "session.error"
CHECKPOINT_REACHED = "checkpoint.reached"
CHECKPOINT_RESOLVED = "checkpoint.resolved"

# An emitter takes an event type + payload and persists/broadcasts it.
Emitter = Callable[[str, dict[str, Any]], Awaitable[None]]


def make_db_emitter(db: AsyncSession, session_id: UUID) -> Emitter:
    """Build an `Emitter` bound to `emit_event` for the given session."""

    async def _emit(type_: str, payload: dict[str, Any]) -> None:
        await emit_event(db, session_id, type_, payload)

    return _emit
