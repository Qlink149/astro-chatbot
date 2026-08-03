"""Token-efficient context helpers."""

from __future__ import annotations

import os

os.environ.setdefault("ENV_MODE", "dev")

from kisna_chatbot.ai.usage import build_usage_record
from kisna_chatbot.utils.format_chathistory import DEFAULT_HISTORY_WINDOW, get_recent_history
from kisna_chatbot.utils.slim_chart import slim_chart_for_beat


def test_history_window_default_is_six():
    assert DEFAULT_HISTORY_WINDOW == 6
    profile = {
        "chat_history": [
            {"role": "user", "content": f"u{i}"} for i in range(20)
        ]
    }
    # Interleave assistants for realism
    hist = []
    for i in range(20):
        hist.append({"role": "user", "content": f"u{i}"})
        hist.append({"role": "assistant", "content": f"a{i}"})
    profile["chat_history"] = hist
    recent = get_recent_history(profile)
    assert len(recent) == 6
    assert recent[0]["role"] in ("user", "assistant")
    # Both sides present in window
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
    rec = build_usage_record(
        client_id="samara",
        agent="general",
        provider="anthropic",
        model="claude",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=1,
        success=True,
        purpose="beat1",
    )
    assert rec.purpose == "beat1"
