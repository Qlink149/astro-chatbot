"""Send WhatsApp interactive list messages via Gupshup."""

from __future__ import annotations

import json

import httpx

from kisna_chatbot.constants import GUPSHUP_SOURCE, GUPSHUP_URL
from kisna_chatbot.utils.env_load import gupshup_api_key, gupshup_app_name
from kisna_chatbot.utils.logger_config import logger


def _clip(text: str, max_len: int) -> str:
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if len(raw) <= max_len:
        return raw
    return raw[:max_len].rstrip(" ,")


def send_list_message(phone_number: str, bot_response: dict):
    """
    Send a Gupshup list message.

    bot_response keys:
      title (header), body, msgid, button (CTA ≤20),
      items: [{title, options: [{type, title, description?, postbackText}]}]
    """
    body = str(bot_response.get("body") or bot_response.get("text") or "").strip()
    header = _clip(str(bot_response.get("title") or "Choose"), 60) or "Choose"
    msgid = str(bot_response.get("msgid") or "samara_list")
    button = _clip(str(bot_response.get("button") or "View options"), 20) or "View"
    items = bot_response.get("items") or []
    if not body or not items:
        raise ValueError("list message requires body and items")

    # Sanitize options (Meta: ≤10 rows total, title ≤24, description ≤72)
    clean_items = []
    total_rows = 0
    for section in items:
        if not isinstance(section, dict):
            continue
        opts_in = section.get("options") or []
        opts = []
        for opt in opts_in:
            if not isinstance(opt, dict):
                continue
            title = _clip(str(opt.get("title") or ""), 24)
            if not title:
                continue
            row = {
                "type": "text",
                "title": title,
                "postbackText": str(opt.get("postbackText") or title)[:200],
            }
            desc = _clip(str(opt.get("description") or ""), 72)
            if desc:
                row["description"] = desc
            opts.append(row)
            total_rows += 1
            if total_rows >= 10:
                break
        if opts:
            clean_items.append(
                {
                    "title": _clip(str(section.get("title") or "Options"), 24),
                    "options": opts,
                }
            )
        if total_rows >= 10:
            break

    if not clean_items:
        raise ValueError("list message had 0 valid rows")

    logger.info(
        "Sending list message",
        extra={
            "phone_number": phone_number,
            "msgid": msgid,
            "row_count": total_rows,
        },
    )

    payload = {
        "type": "list",
        "title": header,
        "body": body,
        "msgid": msgid,
        "globalButtons": [{"type": "text", "title": button}],
        "items": clean_items,
    }
    footer = str(bot_response.get("footer") or "").strip()
    if footer:
        payload["footer"] = footer[:60]

    data = {
        "message": json.dumps(payload),
        "source": GUPSHUP_SOURCE,
        "destination": f"{phone_number}",
        "src.name": gupshup_app_name,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    try:
        response = httpx.post(url=GUPSHUP_URL, headers=headers, data=data, timeout=30)
    except Exception as e:
        logger.error(
            "Error sending list message",
            extra={"phone_number": phone_number, "error": str(e)},
        )
        raise

    body_json = response.json() if response.content else {}
    logger.info(
        "List message API response",
        extra={
            "phone_number": phone_number,
            "status_code": response.status_code,
            "response": body_json,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Gupshup list send failed: HTTP {response.status_code} — {body_json}"
        )
    return body_json
