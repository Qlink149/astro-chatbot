"""Multi-provider AI layer (OpenAI + Groq + Anthropic)."""

from kisna_chatbot.ai.config import get_public_config, resolve_provider
from kisna_chatbot.ai.types import AgentName, ProviderName

__all__ = [
    "AgentName",
    "ProviderName",
    "complete_chat",
    "get_chat_provider",
    "get_public_config",
    "resolve_provider",
]


def __getattr__(name: str):
    if name == "complete_chat":
        from kisna_chatbot.ai.factory import complete_chat

        return complete_chat
    if name == "get_chat_provider":
        from kisna_chatbot.ai.factory import get_chat_provider

        return get_chat_provider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
