"""Razorpay webhook event handling (signature verified by route)."""

from __future__ import annotations

import time
from typing import Any

from kisna_chatbot.database.payments import (
    get_payment_by_link_id,
    grant_credits_for_payment,
    update_payment_by_link_id,
)
from kisna_chatbot.utils.funnel_events import emit_funnel_event
from kisna_chatbot.utils.logger_config import logger
from kisna_chatbot.utils.pwyw_amount import (
    credits_for_amount,
    format_inr,
    min_payment_inr,
)


def _entity_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    pl = payload.get("payment_link") or {}
    if isinstance(pl, dict) and "entity" in pl:
        return pl.get("entity") or {}
    payment = payload.get("payment") or {}
    if isinstance(payment, dict) and "entity" in payment:
        return payment.get("entity") or {}
    return {}


def _razorpay_payment_id(entity: dict[str, Any], event: dict[str, Any]) -> str:
    """Stable id for ledger idempotency (prefer payment entity id)."""
    payload = event.get("payload") or {}
    payment = payload.get("payment") or {}
    if isinstance(payment, dict):
        pe = payment.get("entity") if "entity" in payment else payment
        if isinstance(pe, dict) and pe.get("id"):
            return str(pe["id"])
    for key in ("payment_id", "id"):
        val = entity.get(key)
        if val and str(val).startswith("pay_"):
            return str(val)
    payments = entity.get("payments") or {}
    if isinstance(payments, dict):
        for pid in payments.keys():
            if str(pid).startswith("pay_"):
                return str(pid)
    return str(entity.get("id") or "")


def _paid_amount_paise(entity: dict[str, Any], event: dict[str, Any]) -> int | None:
    """Paid amount in paise from payment_link or payment entity."""
    for key in ("amount_paid", "amount"):
        raw = entity.get(key)
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    payload = event.get("payload") or {}
    payment = payload.get("payment") or {}
    pe = payment.get("entity") if isinstance(payment, dict) and "entity" in payment else payment
    if isinstance(pe, dict) and pe.get("amount") is not None:
        try:
            return int(pe["amount"])
        except (TypeError, ValueError):
            return None
    return None


def handle_razorpay_event(event: dict[str, Any]) -> dict[str, Any]:
    event_name = str(event.get("event") or "")
    entity = _entity_payload(event)
    payment_link_id = str(
        entity.get("id")
        or entity.get("payment_link_id")
        or (entity.get("notes") or {}).get("payment_link_id")
        or ""
    )

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
    payment_id = _razorpay_payment_id(entity, event) or payment_link_id

    already_granted = existing.get("credits_granted_payment_id") == payment_id

    paid_paise = _paid_amount_paise(entity, event)
    expected_paise = existing.get("amount_paise")
    try:
        expected_paise_i = int(expected_paise) if expected_paise is not None else None
    except (TypeError, ValueError):
        expected_paise_i = None

    min_paise = int(round(min_payment_inr() * 100))
    amount_ok = True
    if paid_paise is None:
        logger.error(
            "PAYMENT_AMOUNT_ALERT: missing paid amount on webhook",
            extra={"payment_link_id": payment_link_id, "payment_id": payment_id},
        )
        amount_ok = False
    elif expected_paise_i is not None and abs(paid_paise - expected_paise_i) > 1:
        logger.error(
            "PAYMENT_AMOUNT_ALERT: paid amount mismatch vs stored link",
            extra={
                "payment_link_id": payment_link_id,
                "payment_id": payment_id,
                "paid_paise": paid_paise,
                "expected_paise": expected_paise_i,
            },
        )
        amount_ok = False
    elif paid_paise < min_paise:
        logger.error(
            "PAYMENT_AMOUNT_ALERT: paid below PWYW minimum",
            extra={
                "payment_link_id": payment_link_id,
                "payment_id": payment_id,
                "paid_paise": paid_paise,
                "min_paise": min_paise,
            },
        )
        amount_ok = False

    update_payment_by_link_id(
        payment_link_id,
        {
            "status": "paid" if amount_ok else "paid_amount_rejected",
            "paid_at": int(time.time()),
            "last_event": "payment_link.paid",
            "razorpay_payment_id": payment_id,
            "razorpay_paid_entity": {
                "id": entity.get("id"),
                "amount": entity.get("amount"),
                "amount_paid": entity.get("amount_paid"),
                "status": entity.get("status"),
            },
            "verified_paid_paise": paid_paise,
            "amount_verify_ok": amount_ok,
        },
    )

    if not amount_ok:
        return {
            "ok": True,
            "event": "payment_link.paid",
            "payment_link_id": payment_link_id,
            "payment_id": payment_id,
            "credits_granted": False,
            "amount_rejected": True,
        }

    phone = str(existing.get("phone_number") or "")
    client_id = str(existing.get("client_id") or "samara")
    notes = existing.get("notes") or {}
    if not phone:
        phone = str(notes.get("phone_number") or "")

    verified_inr = (paid_paise or 0) / 100.0
    credits = credits_for_amount(verified_inr)

    credits_granted = False
    if phone and not already_granted:
        from kisna_chatbot.payments.credit_ledger import get_credit_balance
        from kisna_chatbot.database.collections import users

        before_user = users.find_one(
            {"phone_number": phone, "client_id": client_id}
        ) or {}
        before_bal = get_credit_balance(before_user)

        updated = grant_credits_for_payment(
            phone_number=phone,
            client_id=client_id,
            credits=credits,
            payment_id=payment_id,
        )
        after_bal = get_credit_balance(updated or before_user)
        credits_granted = after_bal > before_bal

        update_payment_by_link_id(
            payment_link_id,
            {
                "credits_granted_payment_id": payment_id,
                "credits_granted": credits,
            },
        )

        if credits_granted:
            emit_funnel_event("payment_succeeded", phone_number=phone)
            _send_payment_confirmation_and_resume(
                phone,
                client_id,
                amount_inr=verified_inr,
                credits=credits,
            )

    return {
        "ok": True,
        "event": "payment_link.paid",
        "payment_link_id": payment_link_id,
        "payment_id": payment_id,
        "credits_granted": credits_granted,
        "credits": credits,
    }


def _send_payment_confirmation_and_resume(
    phone_number: str,
    client_id: str,
    *,
    amount_inr: float,
    credits: int,
) -> None:
    """Confirm payment and resume the pending / open-loop question."""
    try:
        from kisna_chatbot.database.collections import users
        from kisna_chatbot.whatsapp_functions.send_text_message import (
            send_text_message_with_retry,
        )

        from kisna_chatbot.utils.samara_beats import text_responses

        amt = format_inr(amount_inr)
        confirm_msg = (
            f"₹{amt} mila — {credits} sawaal add ho gaye 🙏 "
            "Main wahi baat aage badhati hoon — aapko sawaal dobara nahi likhna. 🌙"
        )
        for chunk in text_responses(confirm_msg):
            send_text_message_with_retry(
                phone_number=phone_number,
                bot_response=chunk,
            )

        user = users.find_one(
            {"phone_number": phone_number, "client_id": client_id}
        ) or {}
        pending = (user.get("pending_deep_question") or "").strip()
        open_loop = (user.get("open_loop_summary") or "").strip()
        topic = user.get("chosen_topic") or ""
        resume_q = pending or (
            f"Please continue from this open loop about {topic}: {open_loop[:400]}"
            if open_loop
            else ""
        )
        if not resume_q:
            return

        users.update_one(
            {"phone_number": phone_number, "client_id": client_id},
            {"$set": {"pending_deep_question": None, "paywall_deferred": False}},
        )

        # Deliver paid answer synchronously in this worker (debit on success).
        import asyncio
        from kisna_chatbot.processors.samara_reading_agent import (
            deliver_paid_deep_answer,
        )

        profile = users.find_one(
            {"phone_number": phone_number, "client_id": client_id}
        ) or user

        async def _run():
            return await deliver_paid_deep_answer(
                profile=profile,
                phone_number=phone_number,
                question=resume_q,
            )

        try:
            result = asyncio.run(_run())
        except RuntimeError:
            # Nested loop (unlikely on Vercel webhook) — schedule best-effort
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(_run())
            finally:
                loop.close()

        if not result:
            return

        text, updated_profile = result
        users.update_one(
            {"phone_number": phone_number, "client_id": client_id},
            {
                "$set": {
                    "credits": updated_profile.get("credits"),
                    "credit_ledger": updated_profile.get("credit_ledger"),
                    "followup_questions_asked": updated_profile.get(
                        "followup_questions_asked"
                    ),
                    "open_loop_summary": updated_profile.get("open_loop_summary"),
                    "conversation_beat": updated_profile.get("conversation_beat"),
                }
            },
        )
        for chunk in text_responses(text):
            send_text_message_with_retry(
                phone_number=phone_number,
                bot_response=chunk,
            )
        emit_funnel_event("paid_answer_delivered", phone_number=phone_number)
    except Exception:
        logger.exception(
            "Failed payment confirmation / resume",
            extra={"phone_number": phone_number, "client_id": client_id},
        )
