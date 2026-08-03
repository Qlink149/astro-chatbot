"""Anthropic Claude chat provider.

Used ONLY for the Samara client's reading agent, per SAMARA_FIX_V3_FINAL:
- primary provider for samara + AgentName.GENERAL when ANTHROPIC_API_KEY is set
- other clients unchanged (they keep OpenAI/Groq via the existing factory)
- transparent fallback to the previously-configured provider on transient errors
"""

from __future__ import annotations

import asyncio
import time

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    BadRequestError,
    RateLimitError,
)

from kisna_chatbot.ai.types import (
    CompletionRequest,
    CompletionResult,
    ProviderName,
)
from kisna_chatbot.utils.logger_config import logger

DEFAULT_TIMEOUT = 45.0
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0


class AnthropicChatProvider:
    """Minimal Anthropic Messages provider matching the ChatProvider shape.

    Reads ANTHROPIC_API_KEY from env (never hardcoded). If missing, raises on
    first call so the fallback wrapper transparently switches to the secondary
    provider.
    """

    provider_name = ProviderName.ANTHROPIC

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        self._client = AsyncAnthropic(api_key=api_key, timeout=DEFAULT_TIMEOUT)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        start = time.perf_counter()
        # Anthropic Messages API separates the system prompt from the messages.
        api_messages = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in request.messages
        ]

        logger.info(
            "Anthropic chat request",
            extra={
                "agent": request.agent.value,
                "provider": self.provider_name.value,
                "model": self._model,
            },
        )

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                create_kwargs = {
                    "model": self._model,
                    "system": request.instruction,
                    "messages": api_messages,
                    "max_tokens": max(1, int(request.max_output_tokens or 1024)),
                }
                if request.temperature is not None:
                    create_kwargs["temperature"] = float(request.temperature)
                response = await self._client.messages.create(**create_kwargs)
                # Anthropic returns a list of content blocks; join text blocks.
                parts = []
                for block in getattr(response, "content", []) or []:
                    text_val = getattr(block, "text", None)
                    if text_val:
                        parts.append(text_val)
                text = "".join(parts).strip()

                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
                completion_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
                latency_ms = int((time.perf_counter() - start) * 1000)

                logger.info(
                    "Anthropic chat success",
                    extra={
                        "agent": request.agent.value,
                        "model": self._model,
                        "latency_ms": latency_ms,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    },
                )
                return CompletionResult(
                    text=text,
                    provider=self.provider_name,
                    model=self._model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                last_error = e
                logger.warning(
                    "Transient Anthropic API error, retrying",
                    extra={"attempt": attempt, "error": str(e)},
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
            except (BadRequestError, APIStatusError) as e:
                raise
            except Exception as e:
                logger.error("Anthropic chat error", extra={"error": str(e)})
                raise

        raise last_error or RuntimeError("Anthropic chat failed after retries")


def create_anthropic_chat_provider(api_key: str, model: str) -> AnthropicChatProvider:
    return AnthropicChatProvider(api_key=api_key, model=model)
