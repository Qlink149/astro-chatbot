"""Razorpay webhook event handling (signature verified by route)."""

from __future__ import annotations

import time
from typing import Any

from kisna_chatbot.database.payments import (
    get_payment_by_link_id,
    grant_credits_for_payment,
    update_payment_by_link_id,
)
from kisna_chatbot.utils.logger_config import logger


CREDITS_PER_TEST_PAYMENT = 10


def _entity_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    # payment_link.* events nest under payload.payment_link.entity
    pl = payload.get("payment_link") or {}
    if isinstance(pl, dict) and "entity" in pl:
        return pl.get("entity") or {}
    payment = payload.get("payment") or {}
    if isinstance(payment, dict) and "entity" in payment:
        return payment.get("entity") or {}
    return {}


def handle_razorpay_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Process a verified Razorpay webhook event.

    Returns a small status dict for the HTTP response.
    """
    event_name = str(event.get("event") or "")
    entity = _entity_payload(event)
    payment_link_id = str(
        entity.get("id")
        or entity.get("payment_link_id")
        or (entity.get("notes") or {}).get("payment_link_id")
        or ""
    )

    # payment.failed may not include payment_link id — try notes / description
    if not payment_link_id and event_name.startswith("payment_link."):
        payment_link_id = str(entity.get("id") or "")

    logger.info(
        "Razorpay webhook event",
        extra={"event": event_name, "payment_link_id": payment_link_id or None},
    )

    if event_name == "payment_link.paid":
        return _handle_payment_link_paid(payment_link_id, entity, event)
    if event_name in (
        "payment_link.cancelled",
        "payment_link.expired",
        "payment.failed",
    ):
        status = {
            "payment_link.cancelled": "cancelled",
            "payment_link.expired": "expired",
            "payment.failed": "failed",
        }.get(event_name, "failed")
        if payment_link_id:
            update_payment_by_link_id(
                payment_link_id,
                {"status": status, "last_event": event_name},
            )
        return {"ok": True, "event": event_name, "status": status}

    return {"ok": True, "event": event_name, "ignored": True}


def _handle_payment_link_paid(
    payment_link_id: str,
    entity: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    if not payment_link_id:
        logger.warning("payment_link.paid missing payment_link_id")
        return {"ok": True, "event": "payment_link.paid", "warning": "missing_id"}

    existing = get_payment_by_link_id(payment_link_id) or {}
    already_paid = existing.get("status") == "paid"

    update_payment_by_link_id(
        payment_link_id,
        {
            "status": "paid",
            "paid_at": int(time.time()),
            "last_event": "payment_link.paid",
            "razorpay_paid_entity": {
                "id": entity.get("id"),
                "amount": entity.get("amount"),
                "amount_paid": entity.get("amount_paid"),
                "status": entity.get("status"),
            },
        },
    )

    phone = str(existing.get("phone_number") or "")
    client_id = str(existing.get("client_id") or "samara")
    notes = existing.get("notes") or {}
    if not phone:
        phone = str(notes.get("phone_number") or "")

    if phone and not already_paid:
        grant_credits_for_payment(
            phone_number=phone,
            client_id=client_id,
            credits=CREDITS_PER_TEST_PAYMENT,
        )
        _send_payment_confirmation(phone, client_id)

    return {
        "ok": True,
        "event": "payment_link.paid",
        "payment_link_id": payment_link_id,
        "credits_granted": bool(phone and not already_paid),
    }


def _send_payment_confirmation(phone_number: str, client_id: str) -> None:
    try:
        from kisna_chatbot.whatsapp_functions.send_text_message import (
            send_text_message_with_retry,
        )

        send_text_message_with_retry(
            phone_number=phone_number,
            bot_response={
                "type": "text",
                "text": (
                    "Payment received 🙏 Aapke account mein 10 credits add ho gaye hain. "
                    "Ab aap apne sawaal pooch sakte hain — main yahin hoon. 🌙"
                ),
            },
        )
    except Exception:
        logger.exception(
            "Failed to send payment confirmation WhatsApp",
            extra={"phone_number": phone_number, "client_id": client_id},
        )
