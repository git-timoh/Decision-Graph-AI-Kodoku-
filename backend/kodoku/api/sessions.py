"""REST API for sessions."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import (
    SessionCreate,
    SessionCreateResponse,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)
from kodoku.db.session import get_db
from kodoku.export.memo import _slug, render_markdown
from kodoku.repo.sessions import (
    SessionBundle,
    SessionMutationNotAllowed,
    SessionNotFound,
    SessionRepository,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _repo(db: AsyncSession = Depends(get_db)) -> SessionRepository:  # noqa: B008
    return SessionRepository(db)


def _to_detail(bundle: SessionBundle) -> SessionDetailResponse:
    """Assemble the full session DTO (session + graph) from a repo bundle."""
    return SessionDetailResponse.model_validate({
        **SessionResponse.model_validate(bundle.session).model_dump(),
        "nodes": bundle.nodes,
        "evaluations": bundle.evaluations,
        "checkpoints": bundle.checkpoints,
    })


@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreate,
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> SessionCreateResponse:
    session = await repo.create(payload)
    return SessionCreateResponse(session_id=session.id)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> list[SessionListItem]:
    rows = await repo.list_summaries()
    return [SessionListItem.model_validate(r) for r in rows]


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> SessionDetailResponse:
    try:
        bundle = await repo.get_bundle(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    return _to_detail(bundle)


@router.get("/{session_id}/export")
async def export_session(
    session_id: UUID,
    format: Literal["md", "json"] = "md",
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> Response:
    try:
        bundle = await repo.get_bundle(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    slug = _slug(bundle.session.title)
    short = str(session_id)[:8]
    if format == "json":
        content = _to_detail(bundle).model_dump_json()
        media_type = "application/json"
        ext = "json"
    else:
        content = render_markdown(bundle)
        media_type = "text/markdown"
        ext = "md"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="kodoku-{slug}-{short}.{ext}"',
        },
    )


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: UUID,
    payload: SessionUpdate,
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> SessionResponse:
    try:
        await repo.update(session_id, payload)
        session = await repo.get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except SessionMutationNotAllowed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SessionResponse.model_validate(session)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_session(
    session_id: UUID,
    repo: SessionRepository = Depends(_repo),  # noqa: B008
) -> None:
    try:
        await repo.delete(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
