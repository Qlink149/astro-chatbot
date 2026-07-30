"""Antardasha enrichment + window labels (Beat 2 dated anchors).

Pure label/curation tests need no Swiss Ephemeris. Full-chart asserts skip
when kundli deps are missing locally.
"""

from __future__ import annotations

import pytest

from kundli_engine.antardasha_labels import (
    curate_turning_points,
    window_label_from_ymd,
)


@pytest.mark.parametrize(
    "month,en_prefix,hi_frag",
    [
        (1, "early", "shuruaat"),
        (4, "early", "shuruaat"),
        (5, "mid", "beech"),
        (8, "mid", "beech"),
        (9, "late", "ant"),
        (12, "late", "ant"),
    ],
)
def test_window_label_month_mapping(month, en_prefix, hi_frag):
    en, hi = window_label_from_ymd(2011, month)
    assert en == f"{en_prefix} 2011"
    assert "2011" in hi and hi_frag in hi


def test_curate_turning_points_max_five_and_relevant_only():
    rows = []
    for i, planet in enumerate(
        ["Saturn", "Rahu", "Ketu", "Jupiter", "Mars", "Venus", "Mercury"]
    ):
        rows.append({
            "antar_planet_en": planet,
            "antar_planet_hi": planet,
            "maha_planet_en": "Saturn",
            "maha_planet_hi": "Shani",
            "start": f"201{i}-03-01",
            "end": f"201{i}-09-01",
            "age_start": 20 + i,
            "age_end": 21 + i,
            "starts_before_birth": False,
            "is_relevant": True,
            "window_label_en": f"early 201{i}",
            "window_label_hi": f"201{i} ke shuruaat",
        })
    rows.append({
        "antar_planet_en": "Saturn",
        "start": "1995-01-01",
        "end": "1996-01-01",
        "age_start": 5,
        "age_end": 6,
        "is_relevant": False,
        "window_label_en": "early 1995",
        "window_label_hi": "1995 ke shuruaat",
        "maha_planet_en": "Moon",
        "maha_planet_hi": "Chandra",
        "antar_planet_hi": "Shani",
        "starts_before_birth": False,
    })
    points = curate_turning_points(rows, limit=5)
    assert len(points) <= 5
    assert all(p["is_relevant"] for p in points)
    assert all("theme_en" in p and "theme_hi" in p for p in points)
    starts = [p["start"] for p in points]
    assert starts == sorted(starts)


def test_curate_prefers_classic_shift_planets():
    rows = [
        {
            "antar_planet_en": "Venus",
            "antar_planet_hi": "Shukra",
            "maha_planet_en": "Moon",
            "maha_planet_hi": "Chandra",
            "start": "2010-01-01",
            "end": "2011-01-01",
            "age_start": 20,
            "age_end": 21,
            "is_relevant": True,
            "starts_before_birth": False,
            "window_label_en": "early 2010",
            "window_label_hi": "2010 ke shuruaat",
        },
        {
            "antar_planet_en": "Saturn",
            "antar_planet_hi": "Shani",
            "maha_planet_en": "Moon",
            "maha_planet_hi": "Chandra",
            "start": "2012-06-01",
            "end": "2013-06-01",
            "age_start": 22,
            "age_end": 23,
            "is_relevant": True,
            "starts_before_birth": False,
            "window_label_en": "mid 2012",
            "window_label_hi": "2012 ke beech",
        },
    ]
    points = curate_turning_points(rows, limit=1)
    assert len(points) == 1
    assert points[0]["antar_planet_en"] == "Saturn"
    assert points[0]["theme_en"] == "responsibility"


def _need_chart_engine():
    pytest.importorskip("swisseph")
    pytest.importorskip("jhora")
    from kundli_engine import BirthDetails, compute_chart

    return BirthDetails, compute_chart


@pytest.fixture(scope="module")
def full_chart():
    BirthDetails, compute_chart = _need_chart_engine()
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
    BirthDetails, compute_chart = _need_chart_engine()
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


def test_antardasha_chronological_non_overlapping(full_chart):
    tl = full_chart["antardasha_timeline"]
    assert len(tl) > 0
    for i in range(len(tl) - 1):
        assert tl[i]["start"] <= tl[i + 1]["start"]
        assert tl[i]["end"] <= tl[i + 1]["start"]


def test_relevant_antardasha_constraints(full_chart):
    current_age = full_chart["meta"]["current_age"]
    for p in full_chart["antardasha_timeline"]:
        if not p["is_relevant"]:
            continue
        assert p["age_end"] is not None
        assert p["age_end"] <= current_age
        assert p["age_end"] >= 15


def test_turning_points_bounded_and_relevant(full_chart):
    assert full_chart["meta"]["dated_anchors_available"] is True
    tp = full_chart["turning_points"]
    assert len(tp) <= 5
    assert all(p.get("is_relevant") for p in tp)
    for p in tp:
        assert "window_label_en" in p and "window_label_hi" in p
        assert "theme_en" in p


def test_no_time_empties_dated_anchors(no_time_chart):
    assert no_time_chart["meta"]["dated_anchors_available"] is False
    assert no_time_chart["antardasha_timeline"] == []
    assert no_time_chart["turning_points"] == []


def test_mahadasha_timeline_still_present(full_chart):
    assert len(full_chart["dasha_timeline"]) == 9
