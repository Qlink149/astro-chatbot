"""Post-gate door: at most one gate; meter language gone."""
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
from kisna_chatbot.prompts.samara_reading import (
    SAMARA_BEAT4_DEEP_PROMPT,
    SAMARA_FOLLOWUP_SYSTEM_PROMPT,
)
from kisna_chatbot.utils.samara_beats import BEAT_POST_FREE_DEEP, looks_like_broke_objection
from kisna_chatbot.utils.samara_gate import count_gate_messages

MIN_CHART = {
    "meta": {"birth_year": 1995, "current_age": 30, "chart_type": "birth"},
    "rashi": {},
    "dasha": {"mahadasha": []},
    "turning_points": [
        {"window_label_en": "mid-2026", "start": "2026-06-01", "age_start": 30, "age_end": 32, "theme_en": "x"}
    ],
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_beat4_is_complete_demo():
    p = SAMARA_BEAT4_DEEP_PROMPT.lower()
    assert "complete" in p
    assert "do not withhold" in p or "satisfying" in p


def test_paid_prompt_requires_recommend():
    p = SAMARA_FOLLOWUP_SYSTEM_PROMPT.lower()
    assert "mujhe lagta hai" in p or "i feel you should" in p


def test_post_gate_followup_single_door_no_meter():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "english",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "chosen_topic": "money",
            "open_loop_summary": "There is a clearer filter for which idea first.",
            "credits": 0,
            "credit_ledger": [],
            "trust_score": 5,
            "bot_asked_question": False,
        }
        mock_chat = AsyncMock(return_value="should not run")
        with patch.object(mod, "complete_chat", new=mock_chat):
            out = await agent.process(
                {
                    "client_id": "samara",
                    "phone_number": "919999900099",
                    "user_profile": profile,
                    "messages": {
                        "type": "text",
                        "text": {"body": "which idea should I pick?"},
                    },
                }
            )
        mock_chat.assert_not_called()
        assert count_gate_messages(out["bot_response"]) == 1
        body = out["bot_response"][0]["text"].lower()
        assert "last credit" not in body
        assert "one free deep" not in body
        assert "coming soon" not in body

    _run(go())


def test_broke_objection_canned():
    assert looks_like_broke_objection("I don't have money, can I still chat?")
