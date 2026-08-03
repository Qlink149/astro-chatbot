"""Chart confidence signalling."""

from __future__ import annotations

from kisna_chatbot.prompts.samara_reading import _SHARED_RULES


def test_prompt_has_confidence_rule():
    r = _SHARED_RULES.lower()
    assert "claim_confidence" in r or "confidence signalling" in r
    assert "pakke" in r or "dhundhla" in r


def test_claim_confidence_on_charts():
    pytest = __import__("pytest")
    pytest.importorskip("swisseph")
    pytest.importorskip("jhora")
    from kundli_engine import BirthDetails, compute_chart

    timed = compute_chart(
        BirthDetails(
            year=1990,
            month=5,
            day=15,
            hour=7,
            minute=25,
            latitude=24.5854,
            longitude=73.7125,
            timezone_offset=5.5,
            place_name="Udaipur",
        )
    )
    cc = timed["meta"]["claim_confidence"]
    assert cc["has_birth_time"] is True
    assert cc["houses_lagna"] == "high"

    no_time = compute_chart(
        BirthDetails(
            year=1990,
            month=5,
            day=15,
            latitude=24.5854,
            longitude=73.7125,
            timezone_offset=5.5,
            place_name="Udaipur",
        )
    )
    cc2 = no_time["meta"]["claim_confidence"]
    assert cc2["has_birth_time"] is False
    assert cc2["houses_lagna"] == "low"
