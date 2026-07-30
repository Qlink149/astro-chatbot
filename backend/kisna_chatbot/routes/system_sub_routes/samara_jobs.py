"""Deferred Samara nudge jobs (24h after Baad mein).

Stub: cron/cron-like caller hits POST /system/samara/send-deferred-nudges
with SYSTEM_API_KEY. Sends at most one template (or text fallback) per user.
"""

from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, HTTPException

from kisna_chatbot.database.collections import users
from kisna_chatbot.routes.dependencies.system_dependencies import verify_token_or_api_key
from kisna_chatbot.utils.logger_config import logger

router = APIRouter(
    prefix="/samara",
    tags=["System - Samara jobs"],
    dependencies=[Depends(verify_token_or_api_key)],
)


@router.post("/send-deferred-nudges")
def send_deferred_nudges():
    """Send one-shot nudges for users who chose Baad mein ≥24h ago."""
    now = int(time.time())
    template = (os.environ.get("SAMARA_NUDGE_TEMPLATE") or "").strip()
    query = {
        "client_id": "samara",
        "paywall_deferred": True,
        "nudge_sent": {"$ne": True},
        "nudge_scheduled_at": {"$lte": now},
    }
    due = list(users.find(query).limit(50))
    sent = 0
    for user in due:
        phone = user.get("phone_number")
        if not phone:
            continue
        try:
            _send_nudge(phone, template)
            users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "nudge_sent": True,
                        "nudge_sent_at": now,
                        "paywall_deferred": False,
                    }
                },
            )
            sent += 1
        except Exception:
            logger.exception(
                "deferred nudge failed",
                extra={"phone_number": phone},
            )
    return {"ok": True, "due": len(due), "sent": sent, "template": template or None}


def _send_nudge(phone_number: str, template_name: str) -> None:
    """Send approved Gupshup template if configured; else a soft text (may fail outside 24h window)."""
    from kisna_chatbot.whatsapp_functions.send_text_message import (
        send_text_message_with_retry,
    )

    if template_name:
        # Placeholder for Partner template send — env holds the approved element name.
        # Until Meta approves SAMARA_NUDGE_TEMPLATE, fall through to text.
        logger.info(
            "Samara nudge template requested",
            extra={"template": template_name, "phone_number": phone_number},
        )

    send_text_message_with_retry(
        phone_number=phone_number,
        bot_response={
            "type": "text",
            "text": (
                "Namaste 🙏 Jab aap ready hon, main aapki kundli wali baat "
                "wahi se aage badha sakti hoon. 'pay' ya 'unlock' likh dena — "
                "bina kisi pressure ke. 🌙"
            ),
        },
    )
