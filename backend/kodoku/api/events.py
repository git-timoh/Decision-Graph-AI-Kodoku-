"""Replay endpoint for cold reconnects, plus an M3 debug emitter that drives
the frontend with a scripted Tree-of-Thoughts storyline (no LLM, no engine).
The real engine replaces the debug path in M4.
"""
from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import DebugEmitResponse, WsEvent
from kodoku.db.session import get_db
from kodoku.repo.events import EventRepository
from kodoku.repo.sessions import SessionNotFound, SessionRepository
from kodoku.ws.emit import emit_event

router = APIRouter(prefix="/sessions/{session_id}", tags=["events"])


@router.get("/events", response_model=list[WsEvent])
async def replay_events(
    session_id: UUID,
    since: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WsEvent]:
    rows = await EventRepository(db).list_since(session_id, since)
    return [
        WsEvent(
            id=r.id,
            type=r.type,
            session_id=r.session_id,
            ts=r.created_at,
            payload=r.payload,
        )
        for r in rows
    ]


def _scripted_story(root_id: str, session_id: str) -> list[tuple[str, dict[str, Any]]]:
    """A canned ToT run: root → 3 candidates → evaluations → checkpoint →
    prune the weakest → synthesis. Node ids are fresh UUIDs so replay is
    deterministic per call."""
    cand = [str(uuid.uuid4()) for _ in range(3)]
    ideas = [
        (
            "AI practice-buddy for musicians",
            "Real-time feedback on timing and pitch while you play.",
            8.5,
        ),
        (
            "Generative ambient soundscapes",
            "Mood-driven background audio for focus apps.",
            6.0,
        ),
        (
            "Lyric-to-melody co-writer",
            "Suggests melodies that fit a lyric's meter and emotion.",
            7.5,
        ),
    ]
    story: list[tuple[str, dict[str, Any]]] = [("session.started", {})]
    for cid, (title, content, _score) in zip(cand, ideas, strict=True):
        story.append((
            "node.created",
            {
                "id": cid,
                "session_id": session_id,
                "parent_id": root_id,
                "depth": 1,
                "kind": "candidate",
                "title": title,
                "content": content,
                "status": "active",
            },
        ))
    for cid, (_t, _c, score) in zip(cand, ideas, strict=True):
        story.append((
            "evaluation.completed",
            {
                "node_id": cid,
                "score": score,
                "critique": f"Scored {score}/10 on feasibility, novelty, and fit.",
                "dimensions": {"feasibility": score, "novelty": score, "impact": score},
            },
        ))
    weakest = cand[1]  # lowest score above
    kept = [c for c in cand if c != weakest]
    story += [
        (
            "checkpoint.reached",
            {
                "checkpoint_id": str(uuid.uuid4()),
                "kind": "post_evaluate",
                "payload": {"prune": [weakest], "keep": kept, "expand": []},
            },
        ),
        ("node.updated", {"id": weakest, "status": "pruned"}),
        *[("node.updated", {"id": c, "status": "kept"}) for c in kept],
        ("synthesis.streaming", {"delta": "Recommendation: build the "}),
        ("synthesis.streaming", {"delta": "AI practice-buddy for musicians "}),
        ("synthesis.streaming", {"delta": "as the strongest first bet."}),
        (
            "synthesis.completed",
            {"text": "Recommendation: build the AI practice-buddy for musicians "
                     "as the strongest first bet."},
        ),
        ("session.done", {}),
    ]
    return story


@router.post("/debug/emit", response_model=DebugEmitResponse)
async def debug_emit(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> DebugEmitResponse:
    """Emit a scripted storyline to drive frontend development."""
    try:
        bundle = await SessionRepository(db).get_bundle(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    root = next((n for n in bundle.nodes if n.kind == "root"), None)
    root_id = str(root.id) if root else str(uuid.uuid4())

    last_id = 0
    story = _scripted_story(root_id, str(session_id))
    for type_, payload in story:
        event = await emit_event(db, session_id, type_, payload)
        last_id = event.id
    return DebugEmitResponse(emitted=len(story), last_event_id=last_id)
