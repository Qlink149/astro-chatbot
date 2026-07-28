"""Provider fallback on transient failures."""

from openai import APIConnectionError, APITimeoutError, RateLimitError

try:  # Anthropic is optional; may not be installed in some environments.
    from anthropic import (
        APIConnectionError as AnthropicAPIConnectionError,
        APITimeoutError as AnthropicAPITimeoutError,
        RateLimitError as AnthropicRateLimitError,
    )
    _ANTHROPIC_TRANSIENT: tuple = (
        AnthropicRateLimitError,
        AnthropicAPITimeoutError,
        AnthropicAPIConnectionError,
    )
except Exception:  # pragma: no cover
    _ANTHROPIC_TRANSIENT = tuple()

from kisna_chatbot.ai.base import ChatProvider
from kisna_chatbot.ai.types import CompletionRequest, CompletionResult


def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if _ANTHROPIC_TRANSIENT and isinstance(exc, _ANTHROPIC_TRANSIENT):
        return True
    # Missing key on primary should also route to fallback.
    if isinstance(exc, ValueError) and "API key" in str(exc):
        return True
    return False


class FallbackChatProvider:
    """Try primary provider, then fallback on transient errors."""

    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback
        self.provider_name = primary.provider_name
        self._model = primary.model

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            return await self._primary.complete(request)
        except Exception as primary_exc:
            if not is_transient_error(primary_exc):
                raise
            if self._primary.provider_name == self._fallback.provider_name:
                raise
            result = await self._fallback.complete(request)
            result.fallback_used = True
            return result
