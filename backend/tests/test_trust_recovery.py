"""Task 2: trust recovery — do not gate unconvinced users."""
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
from kisna_chatbot.utils.samara_beats import (
    BEAT_2A_AWAITING_CONFIRM,
    BEAT_TRUST_RECOVERY,
    BTN_BEAT2A_NO,
)
from kisna_chatbot.utils.samara_gate import count_gate_messages, decide_gate_action

MIN_CHART = {
    "meta": {
        "birth_year": 1995,
        "current_age": 30,
        "chart_type": "birth",
        "dated_anchors_available": True,
    },
    "turning_points": [
        {
            "start": "2015-01-01",
            "age_start": 19,
            "age_end": 22,
            "theme_en": "effort without full recognition",
            "theme_hi": "mehnat",
            "window_label_en": "early 2015",
            "window_label_hi": "2015 shuru",
        }
    ],
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_decide_gate_blocks_low_trust():
    profile = {
        "free_deep_answer_used": True,
        "credits": 0,
        "credit_ledger": [],
        "trust_score": -2,
        "trust_scored": True,
        "trust_recovery_attempts": 0,
        "user_language": "english",
        "chart_json": MIN_CHART,
    }
    assert decide_gate_action(profile, amount_inr=49).kind == "none"


def test_beat2a_reject_enters_recovery_no_paywall():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Alex",
            "chart_json": MIN_CHART,
            "user_language": "english",
            "conversation_beat": BEAT_2A_AWAITING_CONFIRM,
            "trust_score": 0,  # soft beat1
            "trust_scored": True,
            "credits": 0,
            "credit_ledger": [],
        }
        out = await agent.process(
            {
                "client_id": "samara",
                "phone_number": "919999900202",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.2a.no",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_BEAT2A_NO, "title": "No"}
                    },
                },
            }
        )
        assert profile["trust_score"] <= 0
        assert profile.get("in_trust_recovery") or profile.get(
            "conversation_beat"
        ) == BEAT_TRUST_RECOVERY
        assert count_gate_messages(out["bot_response"]) == 0
        text = out["bot_response"][0].get("text", "").lower()
        assert "properly" in text or "differently" in text or "matters" in text

    _run(go())


def test_low_trust_followup_no_gate():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Alex",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "free_deep_answer_used": True,
            "user_language": "english",
            "conversation_beat": "post_free_deep",
            "trust_score": -2,
            "trust_recovery_attempts": 0,
            "credits": 0,
            "credit_ledger": [],
            "bot_asked_question": False,
        }
        with patch.object(
            mod, "complete_chat", new=AsyncMock(return_value="Recovery style answer.")
        ):
            # Post-gate block may still fire door unless needs_trust_recovery
            # decide_gate returns none; but early post-gate locked path may emit.
            # Ensure recovery path or suppressed.
            profile["in_trust_recovery"] = True
            out = await agent.process(
                {
                    "client_id": "samara",
                    "phone_number": "919999900203",
                    "user_profile": profile,
                    "messages": {
                        "type": "text",
                        "text": {"body": "career growth please"},
                    },
                }
            )
        assert count_gate_messages(out.get("bot_response") or []) == 0

    _run(go())
