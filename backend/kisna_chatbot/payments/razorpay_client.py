"""Razorpay helpers — payment links via REST + webhook HMAC verify.

Uses httpx (not the razorpay SDK) so Vercel/Python 3.12+ does not depend on
pkg_resources/setuptools from the legacy razorpay package.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any, Optional

import httpx

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


def _key_id() -> str:
    return (os.getenv("RAZORPAY_KEY_ID") or "").strip().strip('"').strip("'")


def _key_secret() -> str:
    return (os.getenv("RAZORPAY_KEY_SECRET") or "").strip().strip('"').strip("'")


def webhook_secret() -> str:
    return (os.getenv("RAZORPAY_WEBHOOK_SECRET") or "").strip().strip('"').strip("'")


def keys_configured() -> bool:
    return bool(_key_id() and _key_secret())


def _auth_header() -> str:
    key_id, key_secret = _key_id(), _key_secret()
    if not key_id or not key_secret:
        raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not configured")
    token = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def normalize_contact(contact: str | None) -> str | None:
    """Razorpay prefers E.164-ish contact; WhatsApp wa_id is usually 91XXXXXXXXXX."""
    if not contact:
        return None
    digits = "".join(ch for ch in str(contact) if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+91{digits}"
    if str(contact).startswith("+"):
        return str(contact).strip()
    return f"+{digits}"


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

    customer_payload = {
        k: v
        for k, v in {
            "name": (customer.get("name") or "Samara user")[:100],
            "email": customer.get("email"),
            "contact": normalize_contact(customer.get("contact")),
        }.items()
        if v
    }

    payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": currency.upper(),
        "accept_partial": False,
        "reference_id": order_id[:40],
        "description": description or f"Samara credits — INR {amount_in_rupees:g}",
        "customer": customer_payload,
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {str(k): str(v) for k, v in (notes or {}).items()},
    }

    logger.info(
        "Creating Razorpay payment link",
        extra={
            "order_id": order_id,
            "amount_paise": amount_paise,
            "currency": currency,
            "key_id_prefix": _key_id()[:12] if _key_id() else None,
        },
    )

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{RAZORPAY_API_BASE}/payment_links",
            headers={
                "Authorization": _auth_header(),
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if resp.status_code >= 400:
        # Surface Razorpay error body for ops (no secrets).
        raise RuntimeError(
            f"Razorpay payment_link create failed HTTP {resp.status_code}: {resp.text[:500]}"
        )

    result = resp.json()
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected Razorpay response: {result!r}")
    return result
