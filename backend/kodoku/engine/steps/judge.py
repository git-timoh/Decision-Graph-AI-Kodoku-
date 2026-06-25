"""LLM-judge decide step: comparatively select keep/prune across siblings.

`decide_with_judge` calls the LLM judge and falls back to the deterministic
`decide()` on ANY failure (LLM error, bad JSON, ids not an exact cover of the
candidates, or empty keep), so the threshold floor is always reachable and the
engine never crashes on a bad judge response.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from string import Template
from uuid import UUID

from pydantic import BaseModel

from kodoku.engine.steps.decide import Decision, decide
from kodoku.engine.steps.parse import parse_json
from kodoku.llm.base import LLMClient

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "judge.md"
_SYSTEM = "You are a rigorous strategic planning assistant that replies with strict JSON."


@dataclass(frozen=True, slots=True)
class JudgeCandidate:
    id: UUID
    title: str
    content: str
    score: float
    critique: str
    dimensions: dict[str, float]


@dataclass(frozen=True, slots=True)
class JudgeOutcome:
    decision: Decision
    rationale: str
    source: str  # "judge" | "threshold_fallback"


class _JudgeResult(BaseModel):
    keep: list[UUID]
    prune: list[UUID]
    rationale: str


def _render_candidates(candidates: list[JudgeCandidate]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- id={c.id} | score={c.score} | dimensions={c.dimensions}\n"
            f"  title: {c.title}\n"
            f"  content: {c.content}\n"
            f"  critique: {c.critique}"
        )
    return "\n".join(lines)


async def judge_decide(
    llm: LLMClient,
    *,
    goal: str,
    candidates: list[JudgeCandidate],
    depth: int,
    max_depth: int,
) -> tuple[Decision, str]:
    """Ask the LLM to comparatively keep/prune. Raises on invalid/unusable output."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = Template(template).safe_substitute(
        goal=goal,
        candidates_block=_render_candidates(candidates),
    )
    result = await parse_json(llm, system=_SYSTEM, prompt=prompt, model_cls=_JudgeResult)

    candidate_ids = {c.id for c in candidates}
    keep = [cid for cid in result.keep if cid in candidate_ids]
    keep_set = set(keep)
    submitted = set(result.keep) | set(result.prune)
    # An id in BOTH keep and prune is contradictory: the prompt asks for exactly
    # one bucket each. Reject (→ threshold fallback) rather than silently keeping it.
    overlap = set(result.keep) & set(result.prune)
    if submitted != candidate_ids or overlap or not keep:
        raise ValueError(
            "judge result is not an exact, disjoint, non-empty cover of candidates"
        )

    # Preserve input order; derive prune from the cover so it always matches.
    keep_ordered = [c.id for c in candidates if c.id in keep_set]
    prune_ordered = [c.id for c in candidates if c.id not in keep_set]
    expand = list(keep_ordered) if depth < max_depth else []
    return Decision(keep=keep_ordered, prune=prune_ordered, expand=expand), result.rationale


async def decide_with_judge(
    llm: LLMClient,
    *,
    goal: str,
    candidates: list[JudgeCandidate],
    depth: int,
    max_depth: int,
) -> JudgeOutcome:
    """Judge with total fallback to the deterministic `decide()`."""
    try:
        decision, rationale = await judge_decide(
            llm, goal=goal, candidates=candidates, depth=depth, max_depth=max_depth
        )
        return JudgeOutcome(decision=decision, rationale=rationale, source="judge")
    except Exception as exc:  # noqa: BLE001 — fallback must be total
        logger.warning("judge decide failed, falling back to threshold: %s", exc)
        scored = [(c.id, c.score) for c in candidates]
        decision = decide(scored, depth=depth, max_depth=max_depth)
        return JudgeOutcome(decision=decision, rationale="", source="threshold_fallback")
