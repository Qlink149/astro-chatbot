import httpx

from kisna_chatbot.config.gupshup import get_birth_details_flow_id
from kisna_chatbot.utils.env_load import gupshup_app_id, gupshup_token
from kisna_chatbot.utils.logger_config import logger

SAMARA_BIRTH_FLOW_TOKEN_PREFIX = "samara_birth"


def send_birth_details_flow(phone_number: str):
    """Sends the Samara birth-details WhatsApp Flow (same transport as other Flows)."""
    flow_id = get_birth_details_flow_id()
    if not flow_id:
        logger.warning(
            "SAMARA_BIRTH_FLOW_ID not set — skipping birth details flow send",
            extra={"phone_number": phone_number},
        )
        return None

    logger.info(
        "Sending birth details flow",
        extra={"phone_number": phone_number, "flow_id": flow_id},
    )
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/v3/message"
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
            "type": "flow",
            "header": {"type": "text", "text": "Aapki Janam Kundli ✨"},
            "body": {
                "text": (
                    "Apni birth details share kijiye — date, time aur place of birth. "
                    "Main aapki asli Vedic kundli banakar ek warm, personal reading dungi. 🌙"
                )
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": f"{SAMARA_BIRTH_FLOW_TOKEN_PREFIX}${flow_id}",
                    "flow_id": flow_id,
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Share Birth Details",
                },
            },
        },
    }

    try:
        response = httpx.post(url, headers=headers, json=data, timeout=30)
    except Exception as e:
        logger.error(
            "Error sending birth details flow",
            extra={"phone_number": phone_number, "error": str(e)},
        )
        raise

    body = response.json()
    logger.info(
        "Birth details flow API response",
        extra={"status_code": response.status_code, "body": body},
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Gupshup flow send failed: HTTP {response.status_code} — {body}"
        )
    return body
