"""Send WhatsApp interactive CTA URL (Pay Now → external link) via Gupshup Partner v3."""

from __future__ import annotations

import httpx

from kisna_chatbot.utils.env_load import gupshup_app_id, gupshup_token
from kisna_chatbot.utils.logger_config import logger


def send_cta_url(phone_number: str, bot_response: dict):
    """
    Send interactive cta_url message.

    bot_response keys: text (body), display_text (button), url, optional footer.
    """
    body_text = str(bot_response.get("text") or "").strip()
    display_text = str(bot_response.get("display_text") or "Pay Now").strip()[:20]
    url = str(bot_response.get("url") or "").strip()
    footer = str(bot_response.get("footer") or "").strip()
    if footer and footer.lower() in ("samara by clara", "samara, by clara"):
        footer = ""  # no brand footer on every CTA

    if not body_text or not url:
        raise ValueError("cta_url requires text and url")

    logger.info(
        "Sending CTA URL message",
        extra={"phone_number": phone_number, "display_text": display_text},
    )
    api_url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/v3/message"
    headers = {
        "Authorization": f"{gupshup_token}",
        "Content-Type": "application/json",
    }
    data = {
        "recipient_type": "individual",
        "messaging_product": "whatsapp",
        "to": f"{phone_number}",
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body_text},
            **({"footer": {"text": footer}} if footer else {}),
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": display_text,
                    "url": url,
                },
            },
        },
    }

    try:
        response = httpx.post(api_url, headers=headers, json=data, timeout=30)
    except Exception as e:
        logger.error(
            "Error sending CTA URL",
            extra={"phone_number": phone_number, "error": str(e)},
        )
        raise

    body = response.json() if response.content else {}
    logger.info(
        "CTA URL API response",
        extra={"status_code": response.status_code, "body": body},
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Gupshup CTA URL send failed: HTTP {response.status_code} — {body}"
        )
    # Normalize for response_manager confirmation check
    if isinstance(body, dict) and "status" not in body:
        body = {**body, "status": "submitted"}
    return body
