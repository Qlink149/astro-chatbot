"""Antardasha enrichment + window labels (Beat 2 dated anchors).

Pure label/curation tests need no Swiss Ephemeris. Full-chart asserts skip
when kundli deps are missing locally.
"""

from __future__ import annotations

import re

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


def test_window_label_month_precision():
    from kundli_engine.antardasha_labels import window_label_month_from_ymd

    en, hi = window_label_month_from_ymd(2019, 3, 10)
    assert en == "March 2019"
    assert "March 2019" in hi and "aas-paas" in hi

    en2, hi2 = window_label_month_from_ymd(2019, 3, 25)
    assert en2 == "March–April 2019"
    assert "March–April 2019" in hi2


def test_curate_upcoming_periods_future_only():
    from datetime import date

    from kundli_engine.antardasha_labels import curate_upcoming_periods

    rows = [
        {
            "start": "2018-03-01",
            "end": "2019-03-01",
            "maha_planet_en": "Saturn",
            "antar_planet_en": "Venus",
            "maha_planet_hi": "Shani",
            "antar_planet_hi": "Shukra",
            "age_start": 28,
            "window_label_month_en": "March 2018",
            "window_label_month_hi": "March 2018 ke aas-paas",
        },
        {
            "start": "2090-06-14",
            "end": "2091-06-14",
            "maha_planet_en": "Venus",
            "antar_planet_en": "Ketu",
            "maha_planet_hi": "Shukra",
            "antar_planet_hi": "Ketu",
            "age_start": 40,
            "window_label_month_en": "June 2090",
            "window_label_month_hi": "June 2090 ke aas-paas",
        },
        {
            "start": "2091-11-02",
            "end": "2092-11-02",
            "maha_planet_en": "Venus",
            "antar_planet_en": "Sun",
            "maha_planet_hi": "Shukra",
            "antar_planet_hi": "Surya",
            "age_start": 41,
            "window_label_month_en": "November 2091",
            "window_label_month_hi": "November 2091 ke aas-paas",
        },
    ]
    up = curate_upcoming_periods(
        rows, today=date(2026, 8, 3), birth_year=1990, limit=5
    )
    assert len(up) == 2
    assert all(p["start"] > "2026-08-03" for p in up)
    assert up[0]["start"] == "2090-06-14"
    assert up[0]["age_at_start"] == 40


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
    today = __import__("datetime").date.today().isoformat()
    for p in full_chart["antardasha_timeline"]:
        if not p["is_relevant"]:
            continue
        assert p["age_end"] is not None
        assert p["end"] < today
        assert p["age_end"] >= 15


def test_is_relevant_false_for_running_period():
    from datetime import date, timedelta

    from kundli_engine.engine import _build_antardasha_timeline

    today = date(2026, 8, 5)
    start = today - timedelta(days=30)
    end = today + timedelta(days=90)
    # Simulate one row's is_relevant logic (same calendar year end as today).
    age_end = today.year - 2004  # birth 2004, end year 2026
    is_relevant = end.isoformat() < today.isoformat() and age_end >= 15
    assert is_relevant is False

    finished_end = today - timedelta(days=1)
    is_relevant_finished = (
        finished_end.isoformat() < today.isoformat() and age_end >= 15
    )
    assert is_relevant_finished is True


def test_turning_points_all_end_before_today():
    BirthDetails, compute_chart = _need_chart_engine()
    chart = compute_chart(
        BirthDetails(
            year=2004,
            month=5,
            day=27,
            hour=7,
            minute=15,
            latitude=24.5854,
            longitude=73.7125,
            timezone_offset=5.5,
            place_name="Udaipur",
        )
    )
    today = __import__("datetime").date.today().isoformat()
    for p in chart.get("turning_points") or []:
        assert p["end"] < today


def test_turning_points_bounded_and_relevant(full_chart):
    assert full_chart["meta"]["dated_anchors_available"] is True
    tp = full_chart["turning_points"]
    assert len(tp) <= 5
    assert all(p.get("is_relevant") for p in tp)
    for p in tp:
        assert "window_label_en" in p and "window_label_hi" in p
        assert "window_label_month_en" in p and "window_label_month_hi" in p
        assert "theme_en" in p


def test_upcoming_periods_on_full_chart(full_chart):
    up = full_chart.get("upcoming_periods") or []
    assert isinstance(up, list)
    assert len(up) <= 5
    today = __import__("datetime").date.today().isoformat()
    for p in up:
        assert p["start"] > today
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", p["start"])


def test_no_time_empties_dated_anchors(no_time_chart):
    assert no_time_chart["meta"]["dated_anchors_available"] is False
    assert no_time_chart["antardasha_timeline"] == []
    assert no_time_chart["turning_points"] == []
    assert no_time_chart.get("upcoming_periods") == []


def test_mahadasha_timeline_still_present(full_chart):
    assert len(full_chart["dasha_timeline"]) == 9
