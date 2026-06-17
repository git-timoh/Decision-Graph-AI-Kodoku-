"""Expand step: ask the LLM for candidate next steps from a parent node."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from kodoku.engine.steps.parse import parse_json
from kodoku.llm.base import LLMClient

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "expand.md"
_SYSTEM = "You are a rigorous strategic planning assistant that replies with strict JSON."


class Candidate(BaseModel):
    title: str
    content: str


class ExpandResult(BaseModel):
    candidates: list[Candidate]


async def expand(
    llm: LLMClient,
    *,
    goal: str,
    parent_title: str,
    parent_content: str,
    branching_factor: int,
) -> list[Candidate]:
    """Generate up to `branching_factor` candidate next steps from a parent node."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.format(
        goal=goal,
        parent_title=parent_title,
        parent_content=parent_content,
        branching_factor=branching_factor,
    )
    result = await parse_json(llm, system=_SYSTEM, prompt=prompt, model_cls=ExpandResult)
    return result.candidates[:branching_factor]
