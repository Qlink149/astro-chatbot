"""Intent classification fixtures (EN + HI)."""

from __future__ import annotations

import asyncio

from kisna_chatbot.utils.samara_intent import (
    classify_intent,
    heuristic_intent,
    is_free_intent,
)


def test_followup_short_cues_en_hi():
    for text in ("aur?", "why", "kab", "kitna?", "kyun", "and then?"):
        assert heuristic_intent(text) == "followup"
        assert is_free_intent("followup")


def test_meta_free():
    assert heuristic_intent("how does this work") == "meta"
    assert heuristic_intent("ye kaise kaam karta hai") == "meta" or heuristic_intent(
        "how does this work"
    ) == "meta"
    assert is_free_intent("meta")


def test_correction_and_payment():
    assert heuristic_intent("my birth time is wrong") == "correction"
    assert heuristic_intent("time galat hai") == "correction"
    assert heuristic_intent("unlock please") == "payment_intent"
    assert heuristic_intent("PAY") == "payment_intent" or heuristic_intent("pay") == "payment_intent"


def test_new_deep_vs_followup_bias():
    focus = {"last_claim": "career window mid-2026", "dates_on_table": ["2026-06-14"]}
    # Short referent stays followup
    assert heuristic_intent("aur?", focus=focus) == "followup"
    # Long new-topic question
    assert (
        heuristic_intent(
            "I want a deep reading about whether I should change careers this year "
            "and what my marriage timing looks like in detail please",
            focus=focus,
        )
        == "new_deep_question"
    )


def test_classify_defaults_followup_without_llm():
    intent = asyncio.get_event_loop().run_until_complete(
        classify_intent("something vague about stars maybe", classify_fn=None)
    )
    assert intent == "followup"


def test_distress_heuristic_present_but_agent_handles_first():
    assert heuristic_intent("I want to kill myself") == "distress"
