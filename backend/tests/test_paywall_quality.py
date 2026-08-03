"""Tasks 3, 6, 7: free deep complete, beat quality, English lock."""
from __future__ import annotations

import os
import re

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
    SAMARA_BEAT2A_THEME_PROMPT,
    SAMARA_BEAT4_DEEP_PROMPT,
    _SHARED_RULES,
)
from kisna_chatbot.utils.samara_beats import beat2a_quality_points
from kisna_chatbot.processors.samara_reading_agent import (
    ENOUGH_ACK_EN,
    GREETING_TEXT_EN,
    PAYWALL_TEXT_EN,
)


def test_beat4_requires_complete_demo():
    p = SAMARA_BEAT4_DEEP_PROMPT.lower()
    assert "both" in p or "two parts" in p
    assert "complete statement" in p
    assert "cliff" not in p or "not withhold" in p or "do not withhold" in p
    assert "turning_points" in p


def test_beat1_requires_personality_and_past_range():
    t = SAMARA_BEAT1_IDENTITY_PROMPT.lower()
    assert "must include both" in t or "must include" in t
    assert "soft_past_range" in t
    assert "falsifiable" in t or "date range" in t
    assert "body hurt" in _SHARED_RULES.lower() or "health" in _SHARED_RULES.lower()
    assert "where does your body hurt" in _SHARED_RULES.lower()


def test_shared_rules_forbid_health_hooks():
    r = _SHARED_RULES.lower()
    assert "no health" in r or "body verification" in r or "body hurt" in r
    assert "falsifiable" in r


def test_beat2a_requires_age_or_skip_helper():
    t = SAMARA_BEAT2A_THEME_PROMPT.lower()
    assert "age range" in t or "between" in t
    chart = {
        "turning_points": [
            {
                "age_start": 19,
                "age_end": 22,
                "theme_en": "effort without recognition",
            }
        ]
    }
    assert len(beat2a_quality_points(chart)) == 1
    assert beat2a_quality_points({"turning_points": [{"theme_en": "x"}]}) == []


def test_english_canned_no_conversational_hindi():
    forbidden = re.compile(r"\b(aapke|kar dijiye|likh dijiye|main hoon)\b", re.I)
    for sample in (GREETING_TEXT_EN, ENOUGH_ACK_EN, PAYWALL_TEXT_EN):
        assert not forbidden.search(sample), sample


def test_shared_rules_english_no_hinglish_sentences():
    assert "hinglish sentences" in _SHARED_RULES.lower() or "not write hinglish" in _SHARED_RULES.lower()
