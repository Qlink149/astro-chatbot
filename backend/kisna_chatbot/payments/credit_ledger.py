"""Append-only credit ledger for Samara.

Balance is derived from ledger entries (grant / debit / refund).
A mirrored `credits` int on the user doc is kept in sync for the admin UI.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pymongo import ReturnDocument

from kisna_chatbot.database.collections import users
from kisna_chatbot.utils.logger_config import logger

LedgerType = Literal["grant", "debit", "refund"]


def _ledger_balance(entries: list[dict]) -> int:
    bal = 0
    for e in entries or []:
        t = e.get("type")
        amt = int(e.get("amount") or 0)
        if t in ("grant", "refund"):
            bal += amt
        elif t == "debit":
            bal -= amt
    return max(0, bal)


def get_credit_balance(profile: dict | None) -> int:
    """Derive balance from ledger; fall back to legacy credits int."""
    if not profile:
        return 0
    entries = profile.get("credit_ledger")
    if isinstance(entries, list) and entries:
        return _ledger_balance(entries)
    return max(0, int(profile.get("credits") or 0))


def _append_ledger_entry(
    *,
    phone_number: str,
    client_id: str,
    entry: dict[str, Any],
    payment_id_unique: str | None = None,
) -> dict | None:
    """Append a ledger entry and sync cached credits.

    If payment_id_unique is set, refuse to grant twice for the same payment_id
    (idempotent Razorpay retries).
    """
    query: dict[str, Any] = {"phone_number": phone_number, "client_id": client_id}
    if payment_id_unique:
        # Only insert grant if this payment_id is not already in the ledger
        query["credit_ledger.payment_id"] = {"$ne": payment_id_unique}

    now = int(time.time())
    entry = {**entry, "timestamp": entry.get("timestamp") or now}
    if payment_id_unique:
        entry["payment_id"] = payment_id_unique

    try:
        # Read-modify-write with optional idempotency filter
        user = users.find_one({"phone_number": phone_number, "client_id": client_id})
        if not user:
            logger.warning(
                "ledger append: user not found",
                extra={"phone_number": phone_number, "client_id": client_id},
            )
            return None

        if payment_id_unique:
            existing = user.get("credit_ledger") or []
            if any(
                isinstance(e, dict) and e.get("payment_id") == payment_id_unique
                for e in existing
            ):
                logger.info(
                    "ledger grant skipped — payment_id already granted",
                    extra={"payment_id": payment_id_unique, "phone_number": phone_number},
                )
                return user

        entries = list(user.get("credit_ledger") or [])
        entries.append(entry)
        balance = _ledger_balance(entries)
        return users.find_one_and_update(
            {"phone_number": phone_number, "client_id": client_id},
            {
                "$set": {
                    "credit_ledger": entries,
                    "credits": balance,
                    "credits_updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
    except Exception:
        logger.exception(
            "append_ledger_entry failed",
            extra={"phone_number": phone_number, "client_id": client_id},
        )
        return None


def grant_credits(
    *,
    phone_number: str,
    client_id: str,
    amount: int,
    source: str,
    payment_id: str | None = None,
) -> dict | None:
    """Append a grant entry. Idempotent when payment_id is provided."""
    return _append_ledger_entry(
        phone_number=phone_number,
        client_id=client_id,
        entry={
            "type": "grant",
            "amount": int(amount),
            "source": source,
            "payment_id": payment_id,
        },
        payment_id_unique=payment_id,
    )


def debit_credit(
    *,
    phone_number: str,
    client_id: str,
    amount: int = 1,
    source: str = "deep_answer",
) -> dict | None:
    """Append a debit after successful answer delivery. Never call on LLM failure."""
    user = users.find_one({"phone_number": phone_number, "client_id": client_id})
    if not user:
        return None
    if get_credit_balance(user) < amount:
        logger.warning(
            "debit_credit refused — insufficient balance",
            extra={"phone_number": phone_number, "balance": get_credit_balance(user)},
        )
        return None
    return _append_ledger_entry(
        phone_number=phone_number,
        client_id=client_id,
        entry={
            "type": "debit",
            "amount": int(amount),
            "source": source,
            "payment_id": None,
        },
    )


def refund_credits(
    *,
    phone_number: str,
    client_id: str,
    amount: int,
    source: str = "refund",
    payment_id: str | None = None,
) -> dict | None:
    return _append_ledger_entry(
        phone_number=phone_number,
        client_id=client_id,
        entry={
            "type": "refund",
            "amount": int(amount),
            "source": source,
            "payment_id": payment_id,
        },
    )
