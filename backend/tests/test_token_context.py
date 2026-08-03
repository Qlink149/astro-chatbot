"""Token-efficient context helpers."""

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

from kisna_chatbot.ai.types import UsageRecord
from kisna_chatbot.utils.format_chathistory import DEFAULT_HISTORY_WINDOW, get_recent_history
from kisna_chatbot.utils.slim_chart import slim_chart_for_beat


def test_history_window_default_is_six():
    assert DEFAULT_HISTORY_WINDOW == 6
    hist = []
    for i in range(20):
        hist.append({"role": "user", "content": f"u{i}"})
        hist.append({"role": "assistant", "content": f"a{i}"})
    profile = {"chat_history": hist}
    recent = get_recent_history(profile)
    assert len(recent) == 6
    roles = {t["role"] for t in recent}
    assert "user" in roles and "assistant" in roles


def test_slim_chart_omits_full_antardasha():
    chart = {
        "meta": {"has_birth_time": True},
        "rashi": {"sign_en": "Cancer"},
        "antardasha_timeline": [{"start": "x"}] * 50,
        "planets": {"Moon": {"sign_en": "Cancer", "longitude": 123.45}},
        "turning_points": [{"start": "2019-03-01"}],
        "upcoming_periods": [{"start": "2026-06-14"}],
        "houses": {
            "system": "whole_sign",
            "planet_houses": {"Moon": 1},
            "bhavas": {"1": {}},
        },
    }
    slim = slim_chart_for_beat(chart, "beat4")
    assert "antardasha_timeline" not in slim
    assert slim.get("upcoming_periods")
    assert "longitude" not in (slim.get("planets") or {}).get("Moon", {})
    assert "bhavas" not in (slim.get("houses") or {})


def test_usage_record_includes_purpose():
    rec = UsageRecord(
        client_id="samara",
        agent="general",
        provider="anthropic",
        model="claude",
        prompt_tokens=10,
        completion_tokens=5,
        estimated_cost_usd=0.0,
        latency_ms=1,
        success=True,
        purpose="beat1",
    )
    assert rec.purpose == "beat1"
