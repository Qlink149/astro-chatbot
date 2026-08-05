"""Task 1: Beat 1 strip, month labels for 2b, upcoming_periods date guard."""

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
    SAMARA_BEAT2B_DATE_ASK_PROMPT,
    _SHARED_RULES,
)
from kisna_chatbot.utils.samara_beats import (
    dates_in_upcoming_periods,
    extract_iso_dates_from_text,
    strip_exact_dates_from_beat1,
)


def test_beat1_strip_removes_month_and_day():
    text = (
        "You carry quietly. Somewhere between 2018 and 2021 a shift began. "
        "Around March 2019 things intensified on 14 March 2019."
    )
    cleaned, violated = strip_exact_dates_from_beat1(text)
    assert violated
    assert "March 2019" not in cleaned
    assert "14 March 2019" not in cleaned
    assert "2018" in cleaned or "2021" in cleaned


def test_beat1_prompt_forbids_month_precision():
    t = SAMARA_BEAT1_IDENTITY_PROMPT.lower()
    assert "ranges only" in t or "date range" in t
    assert "month" in _SHARED_RULES.lower() or "month-level" in _SHARED_RULES.lower()


def test_beat2b_prompt_uses_month_labels():
    assert "{window_label_month}" in SAMARA_BEAT2B_DATE_ASK_PROMPT
    task = SAMARA_BEAT2B_DATE_ASK_PROMPT.split("TASK", 1)[-1]
    assert "window_label_month_hi" not in task
    assert "hindi:" not in task.lower()
    assert "month-level" in SAMARA_BEAT2B_DATE_ASK_PROMPT.lower()


def test_future_dates_must_exist_in_upcoming_periods():
    chart = {
        "upcoming_periods": [
            {"start": "2026-06-14", "end": "2027-11-02"},
            {"start": "2027-11-02", "end": "2028-05-01"},
        ]
    }
    allowed = dates_in_upcoming_periods(chart)
    spoken = "Your Venus–Ketu period begins 2026-06-14 and softens by 2027-11-02."
    found = extract_iso_dates_from_text(spoken)
    assert found
    assert found <= allowed
    invented = extract_iso_dates_from_text("Something on 2025-01-01")
    assert not (invented <= allowed)
