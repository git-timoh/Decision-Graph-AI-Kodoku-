"""In-memory WebSocket fan-out, one subscriber set per session.

Single-process, single-machine — fine for v1 (one user, persistent Fly
machine). If we ever scale to multiple backend instances this becomes a
Redis pub/sub, but YAGNI now.

ponytail: module-level singleton; swap for Redis pub/sub if we go multi-process.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: UUID, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms[session_id].add(ws)

    def disconnect(self, session_id: UUID, ws: WebSocket) -> None:
        room = self._rooms.get(session_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[session_id]

    async def broadcast(self, session_id: UUID, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._rooms.get(session_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — a dead socket shouldn't kill the fan-out
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


# Process-wide singleton shared by the WS router and the event emitter.
manager = ConnectionManager()
