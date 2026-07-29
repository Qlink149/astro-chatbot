"""Shared create-payment-link flow used by HTTP API and WhatsApp PAY trigger."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from kisna_chatbot.database.payments import save_payment
from kisna_chatbot.payments.razorpay_client import create_payment_link
from kisna_chatbot.utils.logger_config import logger


def test_payment_amount_inr() -> float:
    raw = (os.getenv("SAMARA_TEST_PAYMENT_AMOUNT_INR") or "49").strip()
    try:
        return float(raw)
    except ValueError:
        return 49.0


def create_and_store_payment_link(
    *,
    order_id: str,
    amount_in_rupees: float,
    currency: str = "INR",
    customer: dict[str, Any],
    notes: Optional[dict[str, Any]] = None,
    phone_number: Optional[str] = None,
    client_id: str = "samara",
    description: Optional[str] = None,
) -> dict[str, str]:
    """
    Create Razorpay payment link, persist to Mongo, return ids + short_url.

    Returns: { payment_link_id, short_url, order_id }
    """
    notes = dict(notes or {})
    notes.setdefault("order_id", order_id)
    if phone_number:
        notes.setdefault("phone_number", phone_number)
    notes.setdefault("client_id", client_id)

    result = create_payment_link(
        order_id=order_id,
        amount_in_rupees=amount_in_rupees,
        currency=currency,
        customer=customer,
        notes=notes,
        description=description,
    )

    payment_link_id = str(result.get("id") or "")
    short_url = str(result.get("short_url") or "")
    if not payment_link_id or not short_url:
        raise RuntimeError(f"Razorpay response missing id/short_url: {result!r}")

    amount_paise = int(result.get("amount") or int(round(amount_in_rupees * 100)))
    save_payment(
        {
            "payment_link_id": payment_link_id,
            "short_url": short_url,
            "order_id": order_id,
            "amount_paise": amount_paise,
            "currency": currency.upper(),
            "status": str(result.get("status") or "created"),
            "phone_number": phone_number or customer.get("contact") or "",
            "client_id": client_id,
            "customer": customer,
            "notes": notes,
            "razorpay_raw": {
                "id": payment_link_id,
                "short_url": short_url,
                "status": result.get("status"),
                "amount": amount_paise,
            },
            "created_at": int(time.time()),
        }
    )
    logger.info(
        "Payment link stored",
        extra={
            "payment_link_id": payment_link_id,
            "order_id": order_id,
            "phone_number": phone_number,
        },
    )
    return {
        "payment_link_id": payment_link_id,
        "short_url": short_url,
        "order_id": order_id,
    }


def make_samara_order_id(phone_number: str) -> str:
    return f"samara_{phone_number}_{int(time.time())}"[:40]
