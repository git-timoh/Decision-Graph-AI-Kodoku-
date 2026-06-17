"""LLM client abstraction: `LLMClient` protocol plus fake and LiteLLM backends."""
from __future__ import annotations

from kodoku.llm.base import LLMClient
from kodoku.llm.fake import FakeLLMClient
from kodoku.llm.litellm_client import LiteLLMClient

__all__ = ["LLMClient", "FakeLLMClient", "LiteLLMClient"]
