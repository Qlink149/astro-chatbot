"""Gupshup WhatsApp configuration helpers (env read at call time)."""

import os
from functools import lru_cache


def get_gupshup_source() -> str:
    """WhatsApp sender number (E.164 without +). GUPSHUP_SOURCE alone is sufficient."""
    return os.getenv("GUPSHUP_PHONE_NUMBER", "") or os.getenv("GUPSHUP_SOURCE", "")


def get_birth_details_flow_id() -> str:
    """WhatsApp Flow id for the Samara birth-details form."""
    return os.getenv("SAMARA_BIRTH_FLOW_ID", "").strip()


@lru_cache(maxsize=1)
def build_phone_number_id_map() -> dict[str, str]:
    """
    Map Meta phone_number_id from webhook metadata to client_id slug.

    Only non-empty env values are included.
    """
    mapping: dict[str, str] = {}
    samara_id = os.getenv("SAMARA_PHONE_NUMBER_ID", "").strip()
    if samara_id:
        mapping[samara_id] = "samara"
    return mapping


def refresh_phone_number_id_map() -> None:
    """Clear cached phone_number_id map (e.g. after env changes in tests)."""
    build_phone_number_id_map.cache_clear()
