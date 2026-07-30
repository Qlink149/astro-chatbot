"""Purpose → model routing for Samara (Sonnet vs Haiku).

Rule of thumb: if the message's job is to make someone feel something → Sonnet.
If its job is to move state / classify → Haiku.
"""

from __future__ import annotations

from typing import Literal

from kisna_chatbot.ai.config import get_ai_settings

SamaraPurpose = Literal[
    "beat1",
    "beat2",
    "beat2a",
    "beat2b",
    "beat2c",
    "beat4",
    "paid_deep",
    "muhurat",
    "distress",
    "intent",
    "language",
    "summary",
]

_SONNET_PURPOSES = frozenset(
    {
        "beat1",
        "beat2",
        "beat2a",
        "beat2b",
        "beat2c",
        "beat4",
        "paid_deep",
    }
)


def haiku_model_id() -> str:
    settings = get_ai_settings()
    return settings.get("anthropic_chat_model_haiku") or settings["anthropic_chat_model"]


def sonnet_model_id() -> str:
    return get_ai_settings()["anthropic_chat_model_sonnet"]


def samara_model_for(purpose: SamaraPurpose) -> tuple[str, str | None]:
    """Return (primary_model, fallback_model_or_None)."""
    haiku = haiku_model_id()
    if purpose in _SONNET_PURPOSES:
        return sonnet_model_id(), haiku
    return haiku, None


def uses_sonnet(purpose: SamaraPurpose) -> bool:
    return purpose in _SONNET_PURPOSES
