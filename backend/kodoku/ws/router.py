"""Server-push WebSocket endpoint. Clients never send commands here — all
writes go through REST so the engine stays the single writer. We only read
to detect disconnects.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kodoku.ws.manager import manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: UUID) -> None:
    await manager.connect(session_id, websocket)
    try:
        while True:
            # Server-push only; ignore anything the client sends. This await
            # is purely how Starlette surfaces the disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
