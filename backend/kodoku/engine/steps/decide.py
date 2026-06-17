"""Decide step: deterministically classify scored candidates into keep/prune/expand."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

# ponytail: tune later / make config-driven if needed.
KEEP_THRESHOLD = 6.0


@dataclass(frozen=True, slots=True)
class Decision:
    keep: list[UUID]
    prune: list[UUID]
    expand: list[UUID]


def decide(scored: list[tuple[UUID, float]], *, depth: int, max_depth: int) -> Decision:
    """Classify scored candidates into keep/prune/expand, preserving input order.

    `keep` is every id scoring at or above `KEEP_THRESHOLD`; if none qualify, the
    single highest-scoring id is kept so synthesis always has material. `prune`
    is everything not kept. `expand` mirrors `keep` unless `depth >= max_depth`.
    """
    keep = [node_id for node_id, score in scored if score >= KEEP_THRESHOLD]

    if not keep:
        best_id, _ = max(scored, key=lambda item: item[1])
        keep = [best_id]

    keep_set = set(keep)
    prune = [node_id for node_id, _ in scored if node_id not in keep_set]
    expand = list(keep) if depth < max_depth else []

    return Decision(keep=keep, prune=prune, expand=expand)
