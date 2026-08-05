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


def test_challenge_cap_reached():
    agent = SamaraReadingAgent()
    profile = {"test_me_used": True, "user_language": "english", "chart_json": {}}
    data: dict = {}
    out = agent._handle_test_me_year(data, profile, "919999999999", "what about 2015")
    assert out is not None
    text = out["bot_response"][0]["text"].lower()
    assert "enough" in text


def test_three_challenges_allowed_then_capped():
    from kisna_chatbot.utils.samara_beats import MAX_TEST_ME_CHALLENGES

    agent = SamaraReadingAgent()
    rows = [
        {
            "start": f"{y}-03-01",
            "end": f"{y + 1}-03-01",
            "maha_planet_en": "Saturn",
            "antar_planet_en": "Venus",
            "window_label_month_en": f"March {y}",
            "window_label_month_hi": f"March {y} ke aas-paas",
        }
        for y in (2015, 2016, 2017, 2018)
    ]
    profile = {
        "user_language": "english",
        "test_me_offered": True,
        "chart_json": {"antardasha_timeline": rows},
    }
    for i, year in enumerate((2015, 2016, 2017), start=1):
        data: dict = {}
        agent._handle_test_me_year(data, profile, "919999999999", str(year))
        assert profile["test_me_count"] == i
        text = data["bot_response"][0]["text"]
        assert f"March {year}" in text
        assert str(year) in text
    assert profile["test_me_count"] == MAX_TEST_ME_CHALLENGES
    assert agent._test_me_available(profile) is False
    data = {}
    agent._handle_test_me_year(data, profile, "919999999999", "2018")
    assert "enough" in data["bot_response"][0]["text"].lower()


def test_missing_year_is_an_honest_miss_never_a_bluff():
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
                }
            ]
        },
    }
    data: dict = {}
    agent._handle_test_me_year(data, profile, "919999999999", "1990")
    text = data["bot_response"][0]["text"].lower()
    assert "don't have a clear antardasha window for 1990" in text
    assert "make one up" in text
    # A miss must not burn a challenge.
    assert int(profile.get("test_me_count") or 0) == 0


def test_test_me_unavailable_without_engine_rows():
    agent = SamaraReadingAgent()
    assert agent._test_me_available({"chart_json": {}}) is False
    assert (
        agent._test_me_available(
            {"chart_json": {"antardasha_timeline": [{"start": "2015-01-01"}]}}
        )
        is True
    )


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
    assert _disclaims_the_event(text)
    assert int(profile.get("test_me_count") or 0) == 1


# Every rotation variant must hand the event back to the user.
_EVENT_DISCLAIMERS = (
    "yours to say, not mine",
    "not going to guess",
    "your call whether it fits",
    "aapki baat hai, meri nahi",
    "guess nahi karungi",
    "fit hota hai ya nahi",
)


def _disclaims_the_event(text: str) -> bool:
    return any(d in text.lower() for d in _EVENT_DISCLAIMERS)


def test_every_challenge_variant_disclaims_the_event():
    agent = SamaraReadingAgent()
    rows = [
        {
            "start": f"{y}-03-01",
            "end": f"{y + 1}-03-01",
            "maha_planet_en": "Saturn",
            "antar_planet_en": "Venus",
            "window_label_month_en": f"March {y}",
            "window_label_month_hi": f"March {y} ke aas-paas",
        }
        for y in (2015, 2016, 2017)
    ]
    for lang in ("english", "hindi"):
        profile = {
            "user_language": lang,
            "test_me_offered": True,
            "chart_json": {"antardasha_timeline": rows},
        }
        for year in (2015, 2016, 2017):
            data: dict = {}
            agent._handle_test_me_year(data, profile, "919999999999", str(year))
            body = data["bot_response"][0]["text"]
            assert _disclaims_the_event(body), (lang, year, body)
