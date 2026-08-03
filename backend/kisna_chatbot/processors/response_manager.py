from kisna_chatbot.whatsapp_functions.media.send_audio_message import (
    send_audio_message,
)
from kisna_chatbot.whatsapp_functions.media.send_document_message import (
    send_file_message,
)
from kisna_chatbot.whatsapp_functions.media.send_image_message import (
    send_image_message,
)
from kisna_chatbot.whatsapp_functions.quick_reply.send_quick_reply import (
    send_quickreply,
)
from kisna_chatbot.whatsapp_functions.send_text_message import (
    send_text_message_with_retry,
)
from kisna_chatbot.whatsapp_functions.send_cta_url import send_cta_url
from kisna_chatbot.utils.logger_config import logger
from kisna_chatbot.utils.rate_limiter import outbound_rate_limiter
import random
import time


def _human_typing_delay_seconds(text: str) -> float:
    """Variable pause before send — human pace, capped at ~4s."""
    chars = len(text or "")
    base = 0.4 + (chars / 40.0)
    jitter = random.uniform(0.0, 0.4)
    return min(4.0, base + jitter)


class ResponseManager:
    """Singleton class to manage and send bot responses based on their type."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}
            cls._instance._register_default_handlers()
        return cls._instance

    def _register_default_handlers(self):
        self.register_handler("text", self._handle_text)
        self.register_handler("media", self._handle_media)
        self.register_handler("flow", self._handle_flow)
        self.register_handler("quickreply", self._handle_quick_reply)
        self.register_handler("cta_url", self._handle_cta_url)
        self.register_handler("skip", self._handle_skip)

    def register_handler(self, response_type, handler):
        self._handlers[response_type] = handler

    def handle_responses(self, data):
        """Iterate through bot responses and route to the appropriate handler."""
        bot_responses = data.get("bot_response", [])
        phone_number = data["phone_number"]

        for response in bot_responses:
            outbound_rate_limiter.wait_if_needed(phone_number)
            response_type = response.get("type")
            # Human-ish typing pause for text / quickreply (cap ~4s).
            if response_type in ("text", "quickreply"):
                preview = str(
                    response.get("text") or response.get("body") or ""
                )
                time.sleep(_human_typing_delay_seconds(preview))
            handler = self._handlers.get(response_type)

            if handler:
                result = handler(phone_number=phone_number, bot_response=response)
                if result:
                    if result.get("status") != "submitted":
                        logger.warning(f"Message not confirmed: {result}")
                    else:
                        logger.info("message submitted")
                        time.sleep(0.4)
            else:
                logger.error(
                    "Unknown bot_response type: %s — skipping send",
                    response_type,
                    extra={
                        "phone_number": phone_number,
                        "response_type": response_type,
                        "response": response,
                    },
                )

    def _handle_text(self, phone_number, bot_response):
        return send_text_message_with_retry(
            phone_number=phone_number, bot_response=bot_response
        )

    def _handle_quick_reply(self, phone_number, bot_response):
        return send_quickreply(phone_number=phone_number, bot_response=bot_response)

    def _handle_cta_url(self, phone_number, bot_response):
        try:
            return send_cta_url(phone_number=phone_number, bot_response=bot_response)
        except Exception as e:
            logger.exception(
                "Failed to send CTA URL",
                extra={"phone_number": phone_number, "error": str(e)},
            )
            # Fallback: plain text with the link
            url = bot_response.get("url") or ""
            text = bot_response.get("text") or "Complete your payment:"
            return send_text_message_with_retry(
                phone_number=phone_number,
                bot_response={"type": "text", "text": f"{text}\n\n{url}".strip()},
            )

    def _handle_skip(self, phone_number, bot_response):
        logger.warning(
            "Skipping bot_response send (type=skip)",
            extra={"phone_number": phone_number},
        )
        return {"status": "submitted"}

    def _handle_flow(self, phone_number, bot_response):
        flow_name = bot_response["flow"]

        if flow_name == "birth_details":
            from kisna_chatbot.whatsapp_functions.flow.send_birth_details_flow import (
                send_birth_details_flow,
            )

            try:
                result = send_birth_details_flow(phone_number=phone_number)
            except Exception as e:
                logger.exception(
                    "Failed to send birth details flow",
                    extra={"phone_number": phone_number, "error": str(e)},
                )
                result = None
            if result is None:
                return send_text_message_with_retry(
                    phone_number=phone_number,
                    bot_response={
                        "type": "text",
                        "text": (
                            "Form abhi khul nahi paya 😔 Please apni birth details "
                            "aise bhejiye: DOB (DD-MM-YYYY), time (HH:MM ya 'pata nahi'), "
                            "aur city of birth."
                        ),
                    },
                )
            return result
        raise ValueError(f"Unknown flow: {flow_name}")

    def _handle_media(self, phone_number, bot_response):
        media_type = bot_response["media_type"]
        if media_type == "image":
            return send_image_message(
                phone_number=phone_number, bot_response=bot_response
            )
        if media_type == "doc":
            return send_file_message(
                phone_number=phone_number, bot_response=bot_response
            )
        if media_type == "audio":
            return send_audio_message(
                phone_number=phone_number, bot_response=bot_response
            )
        raise ValueError(f"Unknown media type: {media_type}")
