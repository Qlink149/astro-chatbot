"""Mongo helpers for Razorpay payment links."""

from __future__ import annotations

import time
from typing import Any

from pymongo import ReturnDocument

from kisna_chatbot.database.collections import payments, users
from kisna_chatbot.utils.logger_config import logger


def save_payment(payment_record: dict) -> dict | None:
    """Upsert a payment document keyed by payment_link_id."""
    link_id = payment_record.get("payment_link_id")
    if not link_id:
        logger.error("save_payment missing payment_link_id")
        return None
    now = int(time.time())
    doc = {**payment_record, "updated_at": now}
    doc.setdefault("created_at", now)
    try:
        return payments.find_one_and_update(
            {"payment_link_id": link_id},
            {"$set": doc},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception:
        logger.exception("save_payment failed", extra={"payment_link_id": link_id})
        return None


def update_payment_by_link_id(
    payment_link_id: str, update_fields: dict[str, Any]
) -> dict | None:
    """Patch status / paid fields on an existing payment link record."""
    if not payment_link_id:
        return None
    fields = {**update_fields, "updated_at": int(time.time())}
    try:
        return payments.find_one_and_update(
            {"payment_link_id": payment_link_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
    except Exception:
        logger.exception(
            "update_payment_by_link_id failed",
            extra={"payment_link_id": payment_link_id},
        )
        return None


def get_payment_by_link_id(payment_link_id: str) -> dict | None:
    if not payment_link_id:
        return None
    try:
        return payments.find_one({"payment_link_id": payment_link_id})
    except Exception:
        logger.exception(
            "get_payment_by_link_id failed",
            extra={"payment_link_id": payment_link_id},
        )
        return None


def grant_credits_for_payment(
    *,
    phone_number: str,
    client_id: str,
    credits: int = 10,
    payment_id: str | None = None,
) -> dict | None:
    """Grant credits via append-only ledger after payment_link.paid.

    Idempotent on payment_id — retried webhooks must not double-grant.
    """
    from kisna_chatbot.payments.credit_ledger import grant_credits

    return grant_credits(
        phone_number=phone_number,
        client_id=client_id,
        amount=int(credits),
        source="razorpay_payment_link",
        payment_id=payment_id,
    )