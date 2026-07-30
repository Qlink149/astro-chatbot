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


NUDGE_TEXT_HI = (
    "Namaste 🙏 Samara, by Clara. "
    "Aapki kundli wali baat abhi bhi yahin hai — jab ready ho, "
    "'pay' ya 'unlock' likh dena aur main wahi se aage badhaungi. "
    "Bilkul koi rush nahi. 🌙"
)
NUDGE_TEXT_EN = (
    "Namaste 🙏 Samara, by Clara. "
    "Your chart reading is still right here — when you're ready, "
    "type 'pay' or 'unlock' and I'll continue right where we left off. "
    "No rush at all. 🌙"
)


def _send_nudge(phone_number: str, template_name: str) -> None:
    """Send approved Gupshup template if SAMARA_NUDGE_TEMPLATE is set;
    else fall back to a soft text (may fail outside 24h window)."""
    from kisna_chatbot.whatsapp_functions.send_text_message import (
        send_text_message_with_retry,
    )

    if template_name:
        try:
            _send_template_message(phone_number, template_name)
            logger.info(
                "Samara nudge template sent",
                extra={"template": template_name, "phone_number": phone_number},
            )
            return
        except Exception:
            logger.exception(
                "Samara nudge template failed, falling back to text",
                extra={"template": template_name, "phone_number": phone_number},
            )

    send_text_message_with_retry(
        phone_number=phone_number,
        bot_response={"type": "text", "text": NUDGE_TEXT_HI},
    )


def _send_template_message(phone_number: str, template_name: str) -> None:
    """Send a pre-approved Gupshup template message."""
    import requests
    from kisna_chatbot.constants import GUPSHUP_SOURCE

    app_name = os.environ.get("GUPSHUP_APP_NAME", "")
    api_key = os.environ.get("GUPSHUP_API_KEY", "")
    if not app_name or not api_key:
        raise RuntimeError("GUPSHUP_APP_NAME / GUPSHUP_API_KEY not set")

    payload = {
        "channel": "whatsapp",
        "source": GUPSHUP_SOURCE,
        "destination": phone_number,
        "template": '{"id":"%s","params":[]}' % template_name,
        "src.name": app_name,
    }
    headers = {"apikey": api_key, "Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(
        "https://api.gupshup.io/wa/api/v1/template/msg",
        data=payload,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
