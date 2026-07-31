"""Unit coverage for founder-flow reconciliation (Tasks 2–7)."""
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

from kisna_chatbot.prompts.samara_reading import (
    SAMARA_BEAT1_IDENTITY_PROMPT,
    SAMARA_BEAT4_DEEP_PROMPT,
    _SHARED_RULES,
)
from kisna_chatbot.utils.samara_beats import (
    BEAT_AWAITING_NAME,
    BEAT_POST_FREE_DEEP,
    display_user_name,
    needs_conversational_name,
    returning_menu_buttons,
    soft_past_range_from_chart,
    strip_exact_dates_from_beat1,
    topic_label_for,
)
import kisna_chatbot.processors.samara_reading_agent as mod


def _run(coro):
    return asyncio.run(coro)


MIN_CHART = {
    "meta": {
        "has_birth_time": True,
        "chart_type": "full",
        "birth_year": 1990,
        "current_age": 35,
        "dated_anchors_available": True,
    },
    "lagna": {"rashi_en": "Aries"},
    "rashi": {"en": "Taurus"},
    "nakshatra": {"en": "Rohini"},
    "dasha_timeline": [
        {
            "planet_en": "Saturn",
            "planet_hi": "Shani",
            "start": "2018-01-01",
            "end": "2021-06-01",
            "age_start": 28,
            "age_end": 31,
            "lived_from_age": 28,
            "phase": "past",
            "is_relevant": True,
            "starts_before_birth": False,
        }
    ],
    "turning_points": [],
}


def test_shared_rules_meaning_not_mechanics():
    r = _SHARED_RULES.lower()
    assert "meaning" in r and "mechanics" in r
    assert "decision" in r
    assert "isn't from your birth chart" in r or "isn't a chart reading" in r


def test_shared_rules_age_correlation_bands():
    r = _SHARED_RULES.lower()
    assert "12–18" in _SHARED_RULES or "12-18" in r or "~12" in r
    assert "foundations" in r or "studies" in r
    assert "legacy" in r
    assert "minor" in r


def test_shared_rules_relationship_invitation_never_status():
    r = _SHARED_RULES.lower()
    assert "invitation" in r or "status claim" in r
    assert "you are married" in r
    assert "affair" in r or "cheating" in r
    assert "never find" in r


def test_beat1_allows_soft_date_range_not_exact_day():
    t = SAMARA_BEAT1_IDENTITY_PROMPT.lower()
    assert "soft_past_range" in t
    assert "range" in t
    assert "exact" in t or "never a single exact" in t
    assert "14 march" in t or "calendar day" in t


def test_beat4_timeline_ranges():
    t = SAMARA_BEAT4_DEEP_PROMPT.lower()
    assert "range" in t or "window" in t
    assert "exact calendar day" in t or "never an exact" in t


def test_soft_past_range_from_chart_multi_year():
    rng = soft_past_range_from_chart(MIN_CHART)
    assert rng is not None
    assert rng["year_start"] == 2018
    assert rng["year_end"] == 2021
    assert "2018" in rng["range_label_en"] and "2021" in rng["range_label_en"]


def test_soft_past_range_skipped_for_young_user():
    young = {
        **MIN_CHART,
        "meta": {**MIN_CHART["meta"], "current_age": 12},
    }
    assert soft_past_range_from_chart(young) is None


def test_strip_exact_dates_from_beat1():
    raw = "You grew a lot on 14 March 2019 during a quiet chapter."
    clean, hit = strip_exact_dates_from_beat1(raw)
    assert hit is True
    assert "14 March 2019" not in clean
    assert "2019-03-14" not in clean

    ok, hit2 = strip_exact_dates_from_beat1(
        "Somewhere between 2018 and 2021 a quieter chapter began."
    )
    assert hit2 is False
    assert "2018" in ok


def test_returning_menu_references_last_topic():
    hi = returning_menu_buttons(
        lang="hindi", name="Rahul", last_topic_label="career"
    )
    assert "career" in hi["text"].lower()
    assert "pichli baar" in hi["text"].lower() or "wapas" in hi["text"].lower()

    en = returning_menu_buttons(
        lang="english", name="Rahul", last_topic_label="career"
    )
    assert "career" in en["text"].lower()
    assert "last time" in en["text"].lower()


def test_topic_label_for_lang():
    assert "love" in topic_label_for(topic_key="love", lang="english").lower()
    assert "shaadi" in topic_label_for(topic_key="love", lang="hindi").lower()


def test_needs_conversational_name():
    assert needs_conversational_name({"username": "dost"}) is True
    assert needs_conversational_name({"username": "919876543210"}) is True
    assert needs_conversational_name({"username": "Priya"}) is False
    assert needs_conversational_name(
        {"username": "dost", "preferred_name": "Priya"}
    ) is False
    assert display_user_name({"preferred_name": "Priya", "username": "x"}) == "Priya"


def test_returning_greeting_with_chosen_topic():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "hindi",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "chosen_topic": "career",
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900101",
            "user_profile": profile,
            "messages": {"type": "text", "text": {"body": "Namaste"}},
        }
        out = await agent.process(data)
        text = out["bot_response"][0]["text"]
        assert "career" in text.lower()
        assert "wapas" in text.lower() or "pichli" in text.lower()

    _run(go())


def test_language_then_name_ask_when_generic_username():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "dost",
            "chart_json": MIN_CHART,
            "conversation_beat": "awaiting_language",
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900102",
            "user_profile": profile,
            "messages": {
                "type": "interactive",
                "interactive": {
                    "button_reply": {
                        "id": mod.LANG_BTN_HINDI,
                        "title": "Hindi",
                    }
                },
            },
        }
        out = await agent.process(data)
        assert profile.get("user_language") == "hindi"
        assert profile.get("conversation_beat") == BEAT_AWAITING_NAME
        assert "bulaun" in out["bot_response"][0]["text"].lower()

    _run(go())


def test_name_reply_then_beat1():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "dost",
            "preferred_name": None,
            "chart_json": MIN_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_AWAITING_NAME,
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900103",
            "user_profile": profile,
            "messages": {"type": "text", "text": {"body": "Ananya"}},
        }
        with patch.object(
            agent, "_llm", new=AsyncMock(return_value="Tum ek gehra sochne wale insan ho.")
        ):
            out = await agent.process(data)
        assert profile.get("preferred_name") == "Ananya"
        assert out["bot_response"]
        assert profile.get("conversation_beat") != BEAT_AWAITING_NAME

    _run(go())
