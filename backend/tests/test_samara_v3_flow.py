"""Smoke tests for Samara beat-based conversation (Phase 1)."""
import os

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

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import kisna_chatbot.processors.samara_reading_agent as mod
from kisna_chatbot.utils.samara_beats import (
    BEAT_1_AWAITING_CONFIRM,
    BEAT_2_AWAITING_ADVANCE,
    BEAT_AWAITING_TOPIC,
    BEAT_POST_FREE_DEEP,
    BTN_BEAT1_YES,
    BTN_BEAT2_NEXT,
    BTN_TOPIC_CAREER,
    claim_beat_transition,
    split_whatsapp_text,
)


def _run(coro):
    return asyncio.run(coro)


MIN_CHART = {
    "meta": {
        "birth_year": 1990,
        "current_age": 35,
        "has_birth_time": True,
        "chart_type": "full",
    },
    "lagna": {"sign_en": "Virgo", "sign_hi": "Kanya"},
    "rashi": {"sign_en": "Cancer", "sign_hi": "Karka"},
    "nakshatra": {"name": "Pushya", "pada": 2},
    "dasha_timeline": [
        {
            "planet_en": "Saturn",
            "is_relevant": True,
            "age_start": 20,
            "age_end": 36,
            "phase": "past",
        }
    ],
}


@pytest.fixture(autouse=True)
def _mute_funnel():
    with patch("kisna_chatbot.processors.samara_reading_agent.emit_funnel_event"):
        yield


def test_split_whatsapp_respects_line_budget():
    text = "\n".join(f"line {i}" for i in range(14))
    chunks = split_whatsapp_text(text, max_lines=6)
    assert len(chunks) >= 2
    assert all(c.count("\n") <= 5 for c in chunks)


def test_claim_beat_transition_idempotent():
    profile = {"conversation_beat": BEAT_1_AWAITING_CONFIRM}
    assert claim_beat_transition(
        profile,
        expected_beats=(BEAT_1_AWAITING_CONFIRM,),
        next_beat=BEAT_2_AWAITING_ADVANCE,
        inbound_id="wamid.1",
    )
    assert profile["conversation_beat"] == BEAT_2_AWAITING_ADVANCE
    profile["conversation_beat"] = BEAT_1_AWAITING_CONFIRM
    assert not claim_beat_transition(
        profile,
        expected_beats=(BEAT_1_AWAITING_CONFIRM,),
        next_beat=BEAT_2_AWAITING_ADVANCE,
        inbound_id="wamid.1",
    )


def test_birth_details_asks_language_before_reading():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {"username": "Rahul", "chat_history": []}
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "type": "interactive",
                "interactive": {
                    "nfm_reply": {
                        "response_json": json.dumps(
                            {
                                "flow_kind": "birth_details",
                                "birth_date": "1990-05-15",
                                "birth_time": "07:25",
                                "unknown_time": [],
                                "birth_place": "jaipur",
                            }
                        )
                    }
                },
            },
        }
        fake_birth = MagicMock()
        BirthDetails = MagicMock(return_value=fake_birth)
        compute_chart = MagicMock(return_value=MIN_CHART)
        with patch.object(mod, "geocode_place", return_value=(26.9, 75.8)), patch.object(
            mod, "timezone_offset_for", return_value=5.5
        ), patch.object(mod, "_kundli", return_value=(BirthDetails, compute_chart)):
            out = await agent.process(data)
        assert profile.get("chart_json")
        assert profile.get("user_language") is None
        assert profile.get("conversation_beat") == "awaiting_language"
        resp = out["bot_response"]
        assert len(resp) == 1 and resp[0]["type"] == "quickreply"
        ids = [o["postbackText"] for o in resp[0]["options"]]
        assert "samara_lang_en" in ids and "samara_lang_hi" in ids

    _run(go())


def test_language_button_triggers_beat1_not_long_reading():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "conversation_beat": "awaiting_language",
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="You feel thoughtful.\nDoes this ring true?"),
        ) as mock_cc:
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.lang1",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": "samara_lang_en", "title": "English"}
                    },
                },
            }
            out = await agent.process(data)
            assert mock_cc.await_args.kwargs.get("model")
        assert profile["user_language"] == "english"
        assert profile["conversation_beat"] == BEAT_1_AWAITING_CONFIRM
        assert profile["free_reading_used"] is True
        assert out["bot_response"][-1]["type"] == "quickreply"
        ids = [o["postbackText"] for o in out["bot_response"][-1]["options"]]
        assert BTN_BEAT1_YES in ids

    _run(go())


def test_duplicate_language_webhook_does_not_regenerate_beat1():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "conversation_beat": "awaiting_language",
        }
        mock_cc = AsyncMock(return_value="Identity line.")
        with patch.object(mod, "complete_chat", new=mock_cc):
            msg = {
                "id": "wamid.dup",
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": "samara_lang_en", "title": "English"}
                },
            }
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": msg,
            }
            await agent.process(data)
            assert mock_cc.await_count == 1
            # Fresh webhook payload (pipeline builds a new data dict each time)
            data2 = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": msg,
            }
            out2 = await agent.process(data2)
            assert mock_cc.await_count == 1
            assert out2["bot_response"][0]["type"] == "skip"

    _run(go())


def test_beat1_confirm_sends_beat2():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_1_AWAITING_CONFIRM,
            "free_reading_used": True,
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="Around age 28-33 a heavy chapter."),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.b1",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_BEAT1_YES, "title": "Haan, bilkul"}
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2_AWAITING_ADVANCE
        assert out["bot_response"][-1]["type"] == "quickreply"
        assert BTN_BEAT2_NEXT in [
            o["postbackText"] for o in out["bot_response"][-1]["options"]
        ]

    _run(go())


def test_beat2_advance_shows_topic_picker():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2_AWAITING_ADVANCE,
            "free_reading_used": True,
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "id": "wamid.b2",
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": BTN_BEAT2_NEXT, "title": "Aage batao"}
                },
            },
        }
        out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
        assert out["bot_response"][0]["type"] == "quickreply"
        assert len(out["bot_response"][0]["options"]) == 5

    _run(go())


def test_topic_choice_sends_free_deep_and_sets_flag():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "english",
            "conversation_beat": BEAT_AWAITING_TOPIC,
            "free_reading_used": True,
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(
                return_value=(
                    "Career looks active now.\n"
                    "The open question is when the next shift lands."
                )
            ),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.topic",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_TOPIC_CAREER, "title": "Career"}
                    },
                },
            }
            out = await agent.process(data)
        assert profile["free_deep_answer_used"] is True
        assert profile["conversation_beat"] == BEAT_POST_FREE_DEEP
        assert profile["chosen_topic"] == "career"
        assert out["bot_response"][0]["type"] == "text"

    _run(go())


def test_followup_is_not_paywalled():
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
            "credits": 0,
        }
        with patch.object(
            mod, "complete_chat", new=AsyncMock(return_value="[follow-up answer]")
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "type": "text",
                    "text": {"body": "what about my career?"},
                },
            }
            out = await agent.process(data)
        assert "[follow-up answer]" in out["bot_response"][0]["text"]
        assert "credits chahiye" not in out["bot_response"][0]["text"]

    _run(go())


def test_returning_greeting_shows_continuity_menu():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "hindi",
            "conversation_beat": BEAT_POST_FREE_DEEP,
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {"type": "text", "text": {"body": "Namaste"}},
        }
        out = await agent.process(data)
        assert out["bot_response"][0]["type"] == "quickreply"
        titles = [o["title"] for o in out["bot_response"][0]["options"]]
        assert any("Wahi" in t or "baat" in t for t in titles)

    _run(go())


def test_samara_general_client_id_routes_to_anthropic_when_key_set(monkeypatch):
    from kisna_chatbot.ai import config as cfg
    from kisna_chatbot.ai.factory import _samara_uses_anthropic
    from kisna_chatbot.ai.types import AgentName

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    cfg.refresh_ai_settings()
    assert _samara_uses_anthropic(AgentName.GENERAL, "samara") is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
    cfg.refresh_ai_settings()
    assert _samara_uses_anthropic(AgentName.GENERAL, "samara") is True
    assert _samara_uses_anthropic(AgentName.GENERAL, "kisna") is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    cfg.refresh_ai_settings()
