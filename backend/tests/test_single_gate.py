"""Task 5: at most one gate message per inbound."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("ENV_MODE", "dev")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt")
os.environ.setdefault("SYSTEM_API_KEY", "test-api")
os.environ.setdefault("KISNA_PRODUCT_API", "https://example.com/products")
os.environ.setdefault("GUPSHUP_APP_ID", "test-app-id")
os.environ.setdefault("GUPSHUP_TOKEN", "test-token")
os.environ.setdefault("GUPSHUP_APP_NAME", "test-app")
os.environ.setdefault("GUPSHUP_API_KEY", "test-api-key")

from kisna_chatbot.main import app  # noqa: F401

import kisna_chatbot.processors.samara_reading_agent as mod
from kisna_chatbot.utils.samara_beats import BEAT_POST_FREE_DEEP
from kisna_chatbot.utils.samara_gate import count_gate_messages, door_gate_body

MIN_CHART = {
    "meta": {"birth_year": 1995, "current_age": 30, "chart_type": "birth"},
    "turning_points": [
        {
            "window_label_en": "mid-2026",
            "window_label_hi": "2026 beech",
            "start": "2026-06-01",
            "age_start": 30,
            "age_end": 32,
            "theme_en": "career",
        },
        {
            "window_label_en": "late-2027",
            "window_label_hi": "2027 ant",
            "start": "2027-09-01",
            "age_start": 32,
            "age_end": 34,
            "theme_en": "growth",
        },
    ],
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_door_body_has_no_meter_language():
    body = door_gate_body(
        {
            "user_language": "english",
            "chart_json": MIN_CHART,
            "chosen_topic": "career",
        },
        amount_inr=39,
    ).lower()
    assert "last credit" not in body
    assert "one free deep" not in body
    assert "mid-2026" in body or "window" in body


def test_single_gate_on_followup_when_locked():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Alex",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "free_deep_answer_used": True,
            "user_language": "english",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "trust_score": 4,
            "credits": 0,
            "credit_ledger": [],
            "bot_asked_question": False,
        }
        with patch.object(mod, "complete_chat", new=AsyncMock(return_value="x")):
            out = await agent.process(
                {
                    "client_id": "samara",
                    "phone_number": "919999900204",
                    "user_profile": profile,
                    "messages": {
                        "type": "text",
                        "text": {"body": "when will career rise?"},
                    },
                }
            )
        assert count_gate_messages(out["bot_response"]) <= 1
        joined = " ".join(str(x) for x in out["bot_response"]).lower()
        assert "last credit" not in joined
        # Should not contain both old meter phrases
        assert not (
            "last credit" in joined and "free deep" in joined
        )

    _run(go())
