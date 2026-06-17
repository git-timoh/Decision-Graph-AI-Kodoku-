"""LLM client abstraction: `LLMClient` protocol plus fake and LiteLLM backends."""
from __future__ import annotations

from typing import TYPE_CHECKING

from kodoku.llm.base import LLMClient
from kodoku.llm.fake import FakeLLMClient

if TYPE_CHECKING:
    from kodoku.llm.litellm_client import LiteLLMClient

__all__ = ["LLMClient", "FakeLLMClient", "LiteLLMClient"]


def __getattr__(name: str) -> object:
    if name == "LiteLLMClient":
        from kodoku.llm.litellm_client import LiteLLMClient

        return LiteLLMClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
