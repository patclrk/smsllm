"""LLM provider adapters.

A thin internal interface (``LLMAdapter``) normalizes providers. The OpenAI-compatible
adapter is the default and covers most providers via config alone; Anthropic and Gemini
have dedicated adapters for their distinct schemas.
"""

from .base import ChatMessage, GenParams, LLMAdapter, LLMError
from .registry import get_adapter

__all__ = ["ChatMessage", "GenParams", "LLMAdapter", "LLMError", "get_adapter"]
