"""Rajendra live-run audit regression tests."""

from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("ENV_MODE", "dev")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt")
os.environ.setdefault("SYSTEM_API_KEY", "test-api")

from kisna_chatbot.utils.llm_output_guard import enforce_language_script
from kisna_chatbot.utils.slim_chart import current_antardasha_row, slim_chart_for_beat


def test_enforce_language_script_english_rejects_devanagari():
    fb = "A real turning point around January 2023. Did something shift?"
    out = enforce_language_script(
        "January 2023 के आसपास kuch badla?",
        "english",
        fallback=fb,
    )
    assert out == fb
    assert "के" not in out


def test_slim_chart_beat4_includes_current_period():
    today = date.today()
    chart = {
        "meta": {"current_age": 30},
        "antardasha_timeline": [
            {
                "start": "2020-01-01",
                "end": "2025-01-01",
                "maha_planet_en": "Saturn",
                "antar_planet_en": "Venus",
                "window_label_month_en": "January 2020",
            },
            {
                "start": today.replace(year=today.year - 1).isoformat(),
                "end": today.replace(year=today.year + 1).isoformat(),
                "maha_planet_en": "Venus",
                "antar_planet_en": "Mercury",
                "window_label_month_en": "Current window",
            },
        ],
        "turning_points": [],
        "upcoming_periods": [],
    }
    # Fix current row to span today precisely
    cur_start = (today.replace(day=1)).isoformat()
    chart["antardasha_timeline"][-1]["start"] = cur_start
    chart["antardasha_timeline"][-1]["end"] = (
        today.replace(month=12, day=31).isoformat()
    )
    row = current_antardasha_row(chart, today=today)
    assert row is not None
    slim = slim_chart_for_beat(chart, "beat4")
    assert slim.get("current_period")
    assert slim["current_period"]["end"] >= today.isoformat()


def test_beat2b_deterministic_english_only():
    from kisna_chatbot.utils.samara_beats import beat2b_date_ask_body

    body = beat2b_date_ask_body(
        window={"window_label_month_en": "January 2023"},
        lang="english",
        user_choice="No finish line",
    )
    assert "January 2023" in body
    assert "Did something shift" in body
    assert "के" not in body
