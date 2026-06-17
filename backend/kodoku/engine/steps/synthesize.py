"""Synthesize step: stream a final recommendation grounded in the kept nodes."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from kodoku.llm.base import LLMClient

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "synthesize.md"
_SYSTEM = "You are a rigorous strategic planning assistant that replies in plain prose."


def synthesize(
    llm: LLMClient,
    *,
    goal: str,
    kept: list[tuple[str, str]],
) -> AsyncIterator[str]:
    """Stream the final recommendation synthesized from the kept (title, content) ideas."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    kept_ideas = "\n".join(f"- {title}: {content}" for title, content in kept)
    prompt = template.format(goal=goal, kept_ideas=kept_ideas)
    return llm.stream(system=_SYSTEM, prompt=prompt)
