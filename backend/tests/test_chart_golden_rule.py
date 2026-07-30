"""Golden-rule regression: reading text must not invent chart facts.

Given a fixed chart_json, every sign / nakshatra / planet / dasha claim in the
reading must already appear in that JSON. The LLM never calculates charts.
"""

from __future__ import annotations

import pytest

from kisna_chatbot.utils.chart_claim_guard import (
    ChartClaimViolation,
    assert_reading_respects_chart,
    allowed_chart_facts,
)

# Fixed fixture — mirrors a real compute_chart() shape without needing Swiss Ephemeris.
FIXED_CHART = {
    "meta": {
        "has_birth_time": True,
        "chart_type": "full",
        "birth_year": 1990,
        "current_age": 35,
        "birth_date": "1990-05-15",
    },
    "lagna": {"sign_en": "Virgo", "sign_hi": "Kanya", "sign_index": 5},
    "rashi": {"sign_en": "Cancer", "sign_hi": "Karka", "sign_index": 3},
    "surya_rashi": {"sign_en": "Taurus", "sign_hi": "Vrishabha", "sign_index": 1},
    "nakshatra": {"name": "Pushya", "index": 7, "pada": 2},
    "planets": {
        "Sun": {"sign_en": "Taurus", "sign_hi": "Vrishabha", "name_hi": "Surya"},
        "Moon": {"sign_en": "Cancer", "sign_hi": "Karka", "name_hi": "Chandra"},
        "Mars": {"sign_en": "Capricorn", "sign_hi": "Makara", "name_hi": "Mangal"},
        "Mercury": {"sign_en": "Taurus", "sign_hi": "Vrishabha", "name_hi": "Budha"},
        "Jupiter": {"sign_en": "Gemini", "sign_hi": "Mithuna", "name_hi": "Guru"},
        "Venus": {"sign_en": "Aries", "sign_hi": "Mesha", "name_hi": "Shukra"},
        "Saturn": {"sign_en": "Capricorn", "sign_hi": "Makara", "name_hi": "Shani"},
        "Rahu": {"sign_en": "Aquarius", "sign_hi": "Kumbha", "name_hi": "Rahu"},
        "Ketu": {"sign_en": "Leo", "sign_hi": "Simha", "name_hi": "Ketu"},
    },
    "dasha_timeline": [
        {
            "planet_en": "Saturn",
            "planet_hi": "Shani",
            "age_start": 18,
            "age_end": 36,
            "starts_before_birth": False,
            "is_relevant": True,
            "phase": "past",
        },
        {
            "planet_en": "Mercury",
            "planet_hi": "Budha",
            "age_start": 36,
            "age_end": 53,
            "starts_before_birth": False,
            "is_relevant": True,
            "phase": "current",
        },
    ],
}


def test_allowed_facts_extracted_from_fixed_chart():
    allowed = allowed_chart_facts(FIXED_CHART)
    assert "virgo" in allowed["signs"]
    assert "cancer" in allowed["signs"]
    assert "pushya" in allowed["nakshatras"]
    assert "saturn" in allowed["dasha_lords"]
    assert "mercury" in allowed["planets"]
    # Scorpio is nowhere on this chart
    assert "scorpio" not in allowed["signs"]


def test_valid_reading_passes_golden_rule():
    reading = (
        "Aapka Lagna Virgo (Kanya) hai, Moon Cancer mein Pushya nakshatra par. "
        "Saturn dasha ne adulthood mein structure diya, ab Mercury chal raha hai."
    )
    assert_reading_respects_chart(FIXED_CHART, reading)


def test_invented_lagna_fails_golden_rule():
    reading = "Aapka Lagna Scorpio hai — bahut intense personality."
    with pytest.raises(ChartClaimViolation) as exc:
        assert_reading_respects_chart(FIXED_CHART, reading)
    assert "scorpio" in exc.value.invented.get("signs", set())


def test_invented_nakshatra_fails_golden_rule():
    reading = "Aap Rohini nakshatra ke ho, isliye creativity strong hai."
    with pytest.raises(ChartClaimViolation) as exc:
        assert_reading_respects_chart(FIXED_CHART, reading)
    assert "rohini" in exc.value.invented.get("nakshatras", set())


def test_invented_planet_sign_fails_golden_rule():
    # Pisces is not on this chart as any planet sign / lagna / rashi
    reading = "Jupiter Pisces mein baitha hai — soft heart."
    with pytest.raises(ChartClaimViolation) as exc:
        assert_reading_respects_chart(FIXED_CHART, reading)
    assert "pisces" in exc.value.invented.get("signs", set())


def test_no_time_chart_rejects_lagna_claim():
    chart = {
        **FIXED_CHART,
        "lagna": None,
        "meta": {**FIXED_CHART["meta"], "has_birth_time": False, "chart_type": "surya_kundli"},
    }
    reading = "Aapka Lagna Virgo hai."
    with pytest.raises(ChartClaimViolation) as exc:
        assert_reading_respects_chart(chart, reading)
    assert "virgo" in exc.value.invented.get("signs", set())
