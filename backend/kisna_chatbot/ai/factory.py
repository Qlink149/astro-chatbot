"""Provider factory and high-level completion API."""

import time

from kisna_chatbot.ai.config import (
    get_ai_settings,
    resolve_max_tokens,
    resolve_model,
    resolve_provider,
)
from kisna_chatbot.ai.fallback import FallbackChatProvider
from kisna_chatbot.ai.groq_chat import create_groq_chat_provider
from kisna_chatbot.ai.openai_chat import create_openai_chat_provider
from kisna_chatbot.ai.anthropic_chat import create_anthropic_chat_provider
from kisna_chatbot.ai.types import (
    AgentName,
    CompletionRequest,
    CompletionResult,
    ProviderName,
)
from kisna_chatbot.ai.usage import build_usage_record, record_usage
from kisna_chatbot.utils.logger_config import logger


def _create_provider(provider: ProviderName, model: str | None = None):
    if provider == ProviderName.GROQ:
        return create_groq_chat_provider(model)
    if provider == ProviderName.ANTHROPIC:
        settings = get_ai_settings()
        return create_anthropic_chat_provider(
            api_key=settings["anthropic_api_key"],
            model=model or settings["anthropic_chat_model"],
        )
    return create_openai_chat_provider(model)


def _samara_uses_anthropic(agent: AgentName, client_id: str | None) -> bool:
    """Samara reading agent goes to Claude Sonnet when the key is present.

    Other clients (kisna, etc) are untouched. If ANTHROPIC_API_KEY is empty
    (e.g. preview env without the secret), the caller falls back to the
    original provider — this function returns False so the flow stays
    backwards-compatible.
    """
    if client_id != "samara" or agent != AgentName.GENERAL:
        return False
    return bool(get_ai_settings().get("anthropic_api_key"))


def get_chat_provider(
    agent: AgentName,
    client_id: str | None = None,
    *,
    model: str | None = None,
):
    """Return chat provider for agent, with optional fallback wrapper.

    For client_id == "samara" and AgentName.GENERAL, Anthropic Claude is the
    primary provider (via ANTHROPIC_API_KEY env). The existing per-agent
    provider (OpenAI/Groq) is used as the transparent fallback on transient
    errors, and as the sole provider when the Anthropic key is not set.

    Optional `model` overrides the Anthropic model id (e.g. Sonnet for beats).
    """
    settings = get_ai_settings()

    if _samara_uses_anthropic(agent, client_id):
        primary_model = model or settings["anthropic_chat_model"]
        anthropic_provider = _create_provider(ProviderName.ANTHROPIC, primary_model)
        secondary_name = resolve_provider(agent)
        secondary = _create_provider(secondary_name, resolve_model(secondary_name))
        return FallbackChatProvider(anthropic_provider, secondary)

    primary_name = resolve_provider(agent)
    resolved = model or resolve_model(primary_name)
    primary = _create_provider(primary_name, resolved)

    if not settings["fallback_enabled"]:
        return primary

    fallback_name = settings["fallback_provider"]
    if fallback_name == primary_name:
        return primary

    fallback = _create_provider(fallback_name, resolve_model(fallback_name))
    return FallbackChatProvider(primary, fallback)


async def complete_chat(
    *,
    agent: AgentName,
    instruction: str,
    messages: list,
    agent_display_name: str | None = None,
    tools: list | None = None,
    max_output_tokens: int | None = None,
    phone_number: str | None = None,
    client_id: str | None = None,
    model: str | None = None,
    model_fallback: str | None = None,
    temperature: float | None = None,
) -> str:
    """
    Run a chat completion for the given agent using configured provider(s).

    Returns assistant message text.
    Optional `model` / `model_fallback` select Anthropic Sonnet vs Haiku for Samara.
    On any Sonnet failure, retries once with `model_fallback` (Haiku).
    """
    async def _run(chosen_model: str | None) -> CompletionResult:
        provider = get_chat_provider(agent, client_id=client_id, model=chosen_model)
        request = CompletionRequest(
            agent=agent,
            agent_display_name=agent_display_name or agent.value,
            instruction=instruction,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens or resolve_max_tokens(agent),
            phone_number=phone_number,
            client_id=client_id,
            temperature=temperature,
        )
        return await provider.complete(request)

    success = True
    error_msg: str | None = None
    result: CompletionResult | None = None
    used_fallback_model = False

    try:
        try:
            result = await _run(model)
        except Exception as primary_exc:
            if (
                model_fallback
                and model
                and model_fallback != model
                and client_id == "samara"
            ):
                logger.warning(
                    "Samara primary model failed; retrying with fallback model",
                    extra={
                        "model": model,
                        "model_fallback": model_fallback,
                        "error": str(primary_exc),
                    },
                )
                result = await _run(model_fallback)
                used_fallback_model = True
                result.fallback_used = True
            else:
                raise
        return result.text
    except Exception as e:
        success = False
        error_msg = str(e)
        logger.exception(
            "complete_chat failed",
            extra={"agent": agent.value, "error": error_msg},
        )
        raise
    finally:
        if result is not None:
            record_usage(
                build_usage_record(
                    client_id=client_id or "samara",
                    agent=agent.value,
                    provider=result.provider.value,
                    model=result.model,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    latency_ms=result.latency_ms,
                    success=success,
                    phone_number=phone_number,
                    error=error_msg,
                    fallback_used=result.fallback_used or used_fallback_model,
                )
            )
