"""Early handling for non-text WhatsApp inbound message types."""

from typing import Literal

NonTextResult = Literal["silent"] | None

_SKIP_TYPES = frozenset({"text", "interactive"})


def handle_non_text_message(data: dict) -> NonTextResult:
    """
    Handle non-text inbound messages before the Samara pipeline runs.

    Returns:
        None — continue normal pipeline (text/interactive), after optional bot_response
        "silent" — ignore (reactions)
    """
    messages = data.get("messages") or {}
    msg_type = messages.get("type", "")

    if msg_type in _SKIP_TYPES:
        return None

    if msg_type == "reaction":
        return "silent"

    if msg_type == "sticker":
        data["bot_response"] = [
            {"type": "text", "text": "🙏✨ Bataiye, main aapke liye kya dekh sakti hoon?"}
        ]
        return None

    data["bot_response"] = [
        {
            "type": "text",
            "text": (
                "Main abhi sirf text messages padh sakti hoon 🙏 "
                "Apna sawaal ya details text mein likh kar bhejiye."
            ),
        }
    ]
    return None
