"""Razorpay client helpers — payment links + webhook signature verify."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Optional


def _key_id() -> str:
    return (os.getenv("RAZORPAY_KEY_ID") or "").strip()


def _key_secret() -> str:
    return (os.getenv("RAZORPAY_KEY_SECRET") or "").strip()


def webhook_secret() -> str:
    return (os.getenv("RAZORPAY_WEBHOOK_SECRET") or "").strip()


def get_razorpay_client():
    """Build razorpay.Client (lazy import — keeps webhook verify free of SDK)."""
    import razorpay

    key_id, key_secret = _key_id(), _key_secret()
    if not key_id or not key_secret:
        raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not configured")
    return razorpay.Client(auth=(key_id, key_secret))


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """HMAC-SHA256 hex digest of raw body vs X-Razorpay-Signature."""
    secret = webhook_secret()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_payment_link(
    *,
    order_id: str,
    amount_in_rupees: float,
    currency: str = "INR",
    customer: dict[str, Any],
    notes: Optional[dict[str, Any]] = None,
    description: Optional[str] = None,
) -> dict[str, Any]:
    """Create a Razorpay payment link. Amount is converted to paise."""
    from kisna_chatbot.utils.logger_config import logger

    amount_paise = int(round(float(amount_in_rupees) * 100))
    if amount_paise < 100:
        raise ValueError("amount_in_rupees must be at least 1.00 INR")

    payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": currency.upper(),
        "accept_partial": False,
        "reference_id": order_id[:40],
        "description": description
        or f"Samara credits — ₹{amount_in_rupees:g}",
        "customer": {
            k: v
            for k, v in {
                "name": customer.get("name"),
                "email": customer.get("email"),
                "contact": customer.get("contact"),
            }.items()
            if v
        },
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": notes or {},
    }

    client = get_razorpay_client()
    logger.info(
        "Creating Razorpay payment link",
        extra={
            "order_id": order_id,
            "amount_paise": amount_paise,
            "currency": currency,
        },
    )
    result = client.payment_link.create(payload)
    return result
