"""Tests for non-text WhatsApp inbound handling (Samara)."""

import os

os.environ.setdefault("ENV_MODE", "dev")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt")
os.environ.setdefault("SYSTEM_API_KEY", "test-api")
os.environ.setdefault("GUPSHUP_APP_ID", "test")
os.environ.setdefault("GUPSHUP_TOKEN", "test")
os.environ.setdefault("GUPSHUP_APP_NAME", "test")
os.environ.setdefault("GUPSHUP_API_KEY", "test")

from kisna_chatbot.processors.non_text_handler import handle_non_text_message


def _base_data(msg_type: str, **extra) -> dict:
    messages = {"type": msg_type, "from": "919999999999", "id": "wamid.test"}
    messages.update(extra)
    return {
        "phone_number": "919999999999",
        "messages": messages,
        "user_profile": {"chat_history": []},
        "client_id": "samara",
    }


class TestNonTextHandler:
    def test_text_not_handled(self):
        data = _base_data("text", text={"body": "hello"})
        assert handle_non_text_message(data) is None
        assert "bot_response" not in data

    def test_interactive_not_handled(self):
        data = _base_data(
            "interactive",
            interactive={"type": "button_reply", "button_reply": {"title": "Hi"}},
        )
        assert handle_non_text_message(data) is None

    def test_image_reply(self):
        data = _base_data("image", image={"id": "img123"})
        assert handle_non_text_message(data) is None
        assert data["bot_response"][0]["type"] == "text"
        assert "text" in data["bot_response"][0]["text"].lower()

    def test_sticker_reply(self):
        data = _base_data("sticker", sticker={"id": "stk123"})
        handle_non_text_message(data)
        assert "🙏" in data["bot_response"][0]["text"]

    def test_reaction_silent(self):
        data = _base_data("reaction", reaction={"emoji": "👍"})
        assert handle_non_text_message(data) == "silent"
        assert "bot_response" not in data

    def test_location_asks_for_text(self):
        data = _base_data(
            "location",
            location={"latitude": 19.076, "longitude": 72.877},
        )
        assert handle_non_text_message(data) is None
        assert data["bot_response"][0]["type"] == "text"
