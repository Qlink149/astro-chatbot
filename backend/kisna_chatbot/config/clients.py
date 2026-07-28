"""
Client configuration registry for the Samara WhatsApp astrology bot.
"""

import os
from functools import lru_cache

from kisna_chatbot.config.base import ClientConfig

# Ensure .env is loaded before any ClientConfig is built.
from kisna_chatbot.utils import env_load as _env_load  # noqa: F401

SAMARA_INTENT_CATEGORIES = [
    "general",
    "reading",
    "human_handoff",
]


def _samara_config() -> ClientConfig:
    return ClientConfig(
        client_id="samara",
        brand_name="Samara by Clara",
        brand_voice="warm, mystical, reassuring Hinglish jyotishi",
        intent_categories=SAMARA_INTENT_CATEGORIES,
    )


@lru_cache(maxsize=1)
def _registry() -> dict[str, ClientConfig]:
    return {
        "samara": _samara_config(),
    }


def get_client_config(client_id: str) -> ClientConfig:
    """
    Return configuration for a client_id slug (case-insensitive).

    Raises:
        ValueError: If client_id does not match any registered client.
    """
    normalized = (client_id or "").strip().lower() or "samara"
    configs = _registry()
    if normalized in configs:
        return configs[normalized]
    valid_ids = list(configs.keys())
    raise ValueError(
        f"Unknown client_id: {client_id!r}. Valid ids: {valid_ids}"
    )


def refresh_client_registry() -> None:
    """Clear cached configs (e.g. after env changes in tests)."""
    _registry.cache_clear()
