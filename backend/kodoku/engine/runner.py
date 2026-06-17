"""In-process registry of running engine tasks, plus cooperative interrupt.

There is exactly one module-level `runner` singleton. The API layer starts a
run with `runner.start(session_id, engine.run())`, can request a cooperative
stop with `runner.interrupt(session_id)`, and the engine polls
`runner.should_stop(session_id)` between iterations. No threads — just asyncio
tasks and a stop-set.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class SessionRunner:
    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task[Any]] = {}
        self._stop: set[UUID] = set()

    def start(self, session_id: UUID, coro: Coroutine[Any, Any, Any]) -> None:
        """Schedule `coro` as a tracked task, cleaning up on completion."""
        task = asyncio.create_task(coro)
        self._tasks[session_id] = task

        def _cleanup(task: asyncio.Task[Any]) -> None:
            self._tasks.pop(session_id, None)
            self._stop.discard(session_id)
            if not task.cancelled() and (exc := task.exception()) is not None:
                logger.exception(
                    "engine run failed for session %s", session_id, exc_info=exc
                )

        task.add_done_callback(_cleanup)

    def should_stop(self, session_id: UUID) -> bool:
        return session_id in self._stop

    def interrupt(self, session_id: UUID) -> bool:
        """Flag the session to stop; return whether a task was running."""
        self._stop.add(session_id)
        return session_id in self._tasks

    def is_running(self, session_id: UUID) -> bool:
        return session_id in self._tasks

    async def join(self, session_id: UUID) -> None:
        """Await the session's task if present (test helper)."""
        task = self._tasks.get(session_id)
        if task is not None:
            await task


runner = SessionRunner()
