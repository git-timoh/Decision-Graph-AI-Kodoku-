"""Rebuild the BFS frontier from the DB instead of hardcoding `[root_id]`.

This is the single source of truth for "which nodes are still expandable",
used both to seed a fresh run and to resume a paused/checkpointed session. A
node is expandable iff it is `ACTIVE` or `KEPT`, not a `SYNTHESIS` node, within
`max_depth`, and has no children yet (i.e. it hasn't been expanded). Reusing
this on every `run()` call — rather than always seeding `[root_id]` — is what
fixes the shipped bug where re-running a session re-expands an
already-expanded root and duplicates its candidate nodes.
"""
from __future__ import annotations

from collections import deque
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.db.models import Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import NodeKind, NodeStatus


async def rebuild_frontier(db: AsyncSession, session: SessionModel) -> deque[UUID]:
    """Select expandable node ids for `session`, ordered by `(depth, created_at)`."""
    max_depth = session.config["max_depth"]

    expanded_parents = (
        select(Node.parent_id)
        .where(Node.session_id == session.id, Node.parent_id.is_not(None))
        .distinct()
    )

    stmt = (
        select(Node.id)
        .where(
            Node.session_id == session.id,
            Node.status.in_((NodeStatus.ACTIVE.value, NodeStatus.KEPT.value)),
            Node.kind != NodeKind.SYNTHESIS.value,
            Node.depth < max_depth,
            Node.id.not_in(expanded_parents),
        )
        .order_by(Node.depth.asc(), Node.created_at.asc())
    )
    ids = (await db.execute(stmt)).scalars().all()
    return deque(ids)
