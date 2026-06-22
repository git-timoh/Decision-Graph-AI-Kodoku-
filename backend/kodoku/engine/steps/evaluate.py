"""Evaluate step: ask the LLM to score a single candidate node."""
from __future__ import annotations

from pathlib import Path
from string import Template

from pydantic import BaseModel

from kodoku.engine.steps.parse import parse_json
from kodoku.llm.base import LLMClient

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "evaluate.md"
_SYSTEM = "You are a rigorous strategic planning assistant that replies with strict JSON."


class EvaluationResult(BaseModel):
    score: float
    critique: str
    dimensions: dict[str, float]


async def evaluate(
    llm: LLMClient,
    *,
    goal: str,
    candidate_title: str,
    candidate_content: str,
) -> EvaluationResult:
    """Score a single candidate node against the goal, clamping the score to [0, 10]."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    # safe_substitute (not .format): user-supplied text may contain `{`/`}`.
    prompt = Template(template).safe_substitute(
        goal=goal,
        candidate_title=candidate_title,
        candidate_content=candidate_content,
    )
    result = await parse_json(llm, system=_SYSTEM, prompt=prompt, model_cls=EvaluationResult)
    clamped_score = max(0.0, min(10.0, result.score))
    return result.model_copy(update={"score": clamped_score})
