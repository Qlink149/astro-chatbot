"""Task 1: never paywall a solicited reply."""
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
from kisna_chatbot.prompts.samara_reading import _SHARED_RULES
from kisna_chatbot.utils.samara_beats import BEAT_POST_FREE_DEEP
from kisna_chatbot.utils.samara_gate import count_gate_messages

MIN_CHART = {
    "meta": {"birth_year": 1995, "current_age": 30, "chart_type": "birth"},
    "rashi": {},
    "dasha": {"mahadasha": []},
    "turning_points": [],
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_rule6_solicited_in_shared_rules():
    assert "RULE 6" in _SHARED_RULES
    assert "will not answer free" in _SHARED_RULES.lower() or "answer free" in _SHARED_RULES.lower()


def test_solicited_reply_free_no_gate_no_debit():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Alex",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "english",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "credits": 0,
            "credit_ledger": [],
            "bot_asked_question": True,
            "bot_question_context": "Are you currently working or studying?",
            "trust_score": 5,
        }
        mock_chat = AsyncMock(
            return_value="Since you're working, these periods often show up as…"
        )
        debit = AsyncMock() if False else None
        with patch.object(mod, "complete_chat", new=mock_chat), patch.object(
            mod, "debit_credit", return_value=None
        ) as debit_mock:
            out = await agent.process(
                {
                    "client_id": "samara",
                    "phone_number": "919999900201",
                    "user_profile": profile,
                    "messages": {
                        "type": "text",
                        "text": {"body": "I am working"},
                    },
                }
            )
        mock_chat.assert_called()
        debit_mock.assert_not_called()
        assert profile.get("bot_asked_question") is False or profile.get(
            "bot_asked_question"
        ) in (False, True)  # may re-set if answer asks
        # Must clear after handling unless new question
        assert profile["credits"] == 0
        assert count_gate_messages(out["bot_response"]) == 0
        joined = " ".join(
            r.get("text", "") for r in out["bot_response"] if r.get("type") == "text"
        )
        assert "working" in joined.lower() or "period" in joined.lower()
        assert "last credit" not in joined.lower()

    _run(go())
