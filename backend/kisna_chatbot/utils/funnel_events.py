"""Samara product funnel event counters (Mongo).

Emitted alongside the beat conversation; surfaced on the admin Overview.
Never stores secrets — event name + optional phone only.
"""

from __future__ import annotations

import time
from typing import Any

from kisna_chatbot.database.collections import samara_funnel
from kisna_chatbot.utils.logger_config import logger

# Canonical event names (Phase 1 + Phase 2 stubs).
FUNNEL_EVENTS = (
    "birth_flow_opened",
    "birth_flow_completed",
    "language_chosen",
    "beat1_sent",
    "beat1_confirmed",
    "beat2_sent",
    "topic_chosen",
    "free_deep_answer_sent",
    "gate_shown",
    "pay_link_created",
    "payment_succeeded",
    "paid_answer_delivered",
)


def emit_funnel_event(
    event: str,
    *,
    phone_number: str | None = None,
    client_id: str = "samara",
    extra: dict[str, Any] | None = None,
) -> None:
    """Increment a global counter for `event`. Best-effort; never raises."""
    if event not in FUNNEL_EVENTS:
        logger.warning("Unknown funnel event", extra={"event": event})
    try:
        now = int(time.time())
        update: dict[str, Any] = {
            "$inc": {f"counts.{event}": 1},
            "$set": {"updated_at": now, "client_id": client_id},
            "$setOnInsert": {"created_at": now},
        }
        samara_funnel.update_one({"_id": f"funnel:{client_id}"}, update, upsert=True)
        if phone_number:
            logger.info(
                "samara_funnel_event",
                extra={
                    "event": event,
                    "phone_number": phone_number,
                    "client_id": client_id,
                    **(extra or {}),
                },
            )
    except Exception:
        logger.exception(
            "emit_funnel_event failed",
            extra={"event": event, "phone_number": phone_number},
        )


def get_funnel_counts(client_id: str = "samara") -> dict[str, int]:
    """Return all known funnel counters (0 if missing)."""
    try:
        doc = samara_funnel.find_one({"_id": f"funnel:{client_id}"}) or {}
        raw = doc.get("counts") or {}
    except Exception:
        logger.exception("get_funnel_counts failed", extra={"client_id": client_id})
        raw = {}
    return {name: int(raw.get(name) or 0) for name in FUNNEL_EVENTS}
