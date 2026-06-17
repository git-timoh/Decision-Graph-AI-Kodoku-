"""Generic helper: call an `LLMClient` for JSON and parse it into a Pydantic model."""
from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from kodoku.llm.base import LLMClient

ModelT = TypeVar("ModelT", bound=BaseModel)


class StepError(RuntimeError):
    """Raised when the LLM fails to return valid JSON after all retries."""


async def parse_json(
    llm: LLMClient,
    *,
    system: str,
    prompt: str,
    model_cls: type[ModelT],
    retries: int = 2,
) -> ModelT:
    """Call `llm.complete(json_object=True)` and validate the reply as `model_cls`.

    On `ValidationError`/`json.JSONDecodeError`, re-prompts up to `retries` times,
    appending the prior error to the prompt. Raises `StepError` once retries are
    exhausted.
    """
    current_prompt = prompt
    last_error: Exception | None = None

    for _ in range(retries + 1):
        reply = await llm.complete(system=system, prompt=current_prompt, json_object=True)
        try:
            return model_cls.model_validate_json(reply)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            current_prompt = (
                f"{prompt}\n\nYour previous reply was invalid: {exc}. "
                "Return ONLY valid JSON matching the schema."
            )

    raise StepError(
        f"Failed to parse {model_cls.__name__} after {retries} retries: {last_error}"
    ) from last_error
