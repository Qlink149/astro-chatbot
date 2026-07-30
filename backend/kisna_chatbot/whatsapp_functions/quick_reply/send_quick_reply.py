from kisna_chatbot.constants import GUPSHUP_SOURCE, GUPSHUP_URL
from kisna_chatbot.utils.env_load import gupshup_api_key, gupshup_app_name
from kisna_chatbot.utils.logger_config import logger
from kisna_chatbot.whatsapp_functions.send_text_message import send_text_message
import json
import httpx


def _sanitize_options(bot_response: dict) -> list:
    """Meta WhatsApp quick-reply: min 1, max 3 buttons."""
    options = bot_response.get("options") or []
    if not isinstance(options, list):
        options = [options]
    cleaned = []
    for opt in options:
        if isinstance(opt, dict) and (opt.get("title") or opt.get("text")):
            cleaned.append(opt)
    if not cleaned:
        logger.warning(
            "quick_reply had 0 valid buttons — falling back to plain text",
            extra={"raw_options": options},
        )
        return []
    if len(cleaned) > 3:
        logger.warning(
            "quick_reply had >3 buttons — truncating to 3 (Meta limit)",
            extra={"button_count": len(cleaned)},
        )
    return cleaned[:3]


def send_quickreply(phone_number, bot_response):
    """Send quick reply; enforce Meta button limits (1–3)."""
    options = _sanitize_options(bot_response)
    logger.info(
        "Sending quick reply",
        extra={
            "phone_number": phone_number,
            "button_count": len(options),
            "msgid": bot_response.get("msgid"),
        },
    )

    if not options:
        # Empty buttons is invalid (#131009) — send text instead
        text_body = {"type": "text", "text": bot_response.get("text", "")}
        if bot_response.get("caption"):
            text_body["caption"] = bot_response["caption"]
        return send_text_message(
            phone_number=phone_number, bot_response=text_body
        )

    destination = f"{phone_number}"
    url = GUPSHUP_URL

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    data = {
        "message": json.dumps(
            {
                "type": "quick_reply",
                "content": {
                    "type": "text",
                    "text": bot_response["text"],
                    "caption": bot_response.get("caption", ""),
                },
                "options": options,
                "msgid": bot_response["msgid"],
            }
        ),
        "source": GUPSHUP_SOURCE,
        "destination": destination,
        "src.name": gupshup_app_name,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Response",
            extra={
                "phone_number": phone_number,
                "response": response.json(),
            },
        )
        return response.json()
    except Exception as e:
        logger.error(
            "Error while sending postcall quick reply",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
