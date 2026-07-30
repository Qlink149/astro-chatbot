"""Assert compute_chart() dasha enrichment fields (Phase 0).

Engine-side only: age_start/age_end, starts_before_birth, is_relevant,
plus meta.birth_year and meta.current_age. No LLM involvement.
"""

from __future__ import annotations

import pytest

pytest.importorskip("swisseph")
pytest.importorskip("jhora")

from kundli_engine import BirthDetails, compute_chart


REQUIRED_DASHA_KEYS = {
    "age_start",
    "age_end",
    "starts_before_birth",
    "is_relevant",
    "planet_en",
    "phase",
    "lived_from_age",
}


@pytest.fixture(scope="module")
def full_chart():
    return compute_chart(
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


@pytest.fixture(scope="module")
def no_time_chart():
    return compute_chart(
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


def test_meta_exposes_birth_year_and_current_age(full_chart):
    meta = full_chart["meta"]
    assert meta["birth_year"] == 1990
    assert isinstance(meta["current_age"], int)
    assert meta["current_age"] >= 0
    assert meta["has_birth_time"] is True


def test_dasha_periods_have_enrichment_fields(full_chart):
    timeline = full_chart["dasha_timeline"]
    assert len(timeline) == 9
    for period in timeline:
        missing = REQUIRED_DASHA_KEYS - set(period.keys())
        assert not missing, f"dasha period missing keys {missing}: {period}"
        assert isinstance(period["age_start"], int)
        assert period["age_end"] is None or isinstance(period["age_end"], int)
        assert isinstance(period["starts_before_birth"], bool)
        assert isinstance(period["is_relevant"], bool)
        assert period["phase"] in ("past", "current", "future")


def test_is_relevant_excludes_childhood_only_windows(full_chart):
    """Childhood-only periods (age_end < 15) must not be marked relevant."""
    for period in full_chart["dasha_timeline"]:
        age_end = period["age_end"]
        if age_end is not None and age_end < 15:
            assert period["is_relevant"] is False, period


def test_starts_before_birth_flag_consistency(full_chart):
    birth_year = full_chart["meta"]["birth_year"]
    for period in full_chart["dasha_timeline"]:
        start_year = int(str(period["start"])[:4])
        assert period["starts_before_birth"] is (start_year < birth_year)


def test_no_time_omits_lagna_keeps_dasha_meta(no_time_chart):
    assert no_time_chart["lagna"] is None
    assert no_time_chart["meta"]["chart_type"] == "surya_kundli"
    assert "houses" not in no_time_chart
    assert no_time_chart["meta"]["birth_year"] == 1990
    assert isinstance(no_time_chart["meta"]["current_age"], int)
    assert len(no_time_chart["dasha_timeline"]) == 9


def test_full_chart_includes_houses(full_chart):
    assert "houses" in full_chart
    houses = full_chart["houses"]
    assert houses["system"] == "whole_sign"
    assert len(houses["bhavas"]) == 12
    assert "Moon" in houses["planet_houses"]
    assert 1 <= houses["planet_houses"]["Moon"] <= 12
