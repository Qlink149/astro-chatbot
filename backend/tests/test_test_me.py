"""Test-me year challenge against engine antardasha."""

from __future__ import annotations

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

from kisna_chatbot.main import app  # noqa: F401 — init env/logger before agent

from kundli_engine.antardasha_labels import lookup_antardasha_covering_year
from kisna_chatbot.processors.samara_reading_agent import SamaraReadingAgent


def test_lookup_antardasha_covering_year():
    rows = [
        {
            "start": "2018-01-01",
            "end": "2019-06-01",
            "antar_planet_en": "Venus",
            "window_label_month_en": "January 2018",
        },
        {
            "start": "2019-06-01",
            "end": "2020-12-01",
            "antar_planet_en": "Saturn",
            "window_label_month_en": "June 2019",
        },
    ]
    hit = lookup_antardasha_covering_year(rows, 2019)
    assert hit is not None
    assert hit["antar_planet_en"] in ("Venus", "Saturn")
    assert lookup_antardasha_covering_year(rows, 1990) is None


def test_second_challenge_flag():
    agent = SamaraReadingAgent()
    profile = {"test_me_used": True, "user_language": "english", "chart_json": {}}
    data: dict = {}
    out = agent._handle_test_me_year(data, profile, "919999999999", "what about 2015")
    assert out is not None
    text = out["bot_response"][0]["text"].lower()
    assert "one challenge" in text or "enough" in text


def test_no_event_assertion_in_offer_copy():
    agent = SamaraReadingAgent()
    profile = {
        "confirmed_events": [{"x": 1}],
        "user_language": "hindi",
    }
    offer = agent._maybe_test_me_offer(profile)
    assert offer
    assert "claim" in offer.lower() or "kya hua" in offer.lower()
    assert profile.get("test_me_offered") is True
    assert agent._maybe_test_me_offer(profile) is None


def test_year_reply_uses_engine_only_no_event_claim():
    agent = SamaraReadingAgent()
    profile = {
        "user_language": "english",
        "test_me_offered": True,
        "chart_json": {
            "antardasha_timeline": [
                {
                    "start": "2015-03-01",
                    "end": "2016-03-01",
                    "maha_planet_en": "Saturn",
                    "antar_planet_en": "Venus",
                    "window_label_month_en": "March 2015",
                    "window_label_month_hi": "March 2015 ke aas-paas",
                }
            ]
        },
    }
    data: dict = {}
    out = agent._handle_test_me_year(data, profile, "919999999999", "what about 2015?")
    text = out["bot_response"][0]["text"]
    assert "March 2015" in text
    assert "won't claim what happened" in text.lower() or "claim" in text.lower()
    assert profile.get("test_me_used") is True
