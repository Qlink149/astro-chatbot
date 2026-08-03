"""Conversation focus object tests."""

from __future__ import annotations

from kisna_chatbot.utils.samara_focus import (
    focus_prompt_block,
    update_focus_after_bot,
    update_focus_from_user,
)


def test_focus_updates_after_bot():
    profile: dict = {}
    update_focus_after_bot(
        profile,
        text="Career window opens mid-2026.",
        claim="career window opens mid-2026",
        dates=["2026-06-14"],
        awaiting="confirmation_of_2019_anchor",
        topic="career",
    )
    focus = profile["conversation_focus"]
    assert focus["topic"] == "career"
    assert "career window" in focus["last_claim"]
    assert "2026-06-14" in focus["dates_on_table"]
    assert focus["awaiting"] == "confirmation_of_2019_anchor"


def test_focus_user_facts_keep_own_words():
    profile: dict = {"conversation_focus": {"user_facts": []}}
    update_focus_from_user(profile, text="I feel unrecognised at work")
    assert "unrecognised" in profile["conversation_focus"]["user_facts"][0]


def test_focus_prompt_block_includes_claim():
    profile = {
        "conversation_focus": {
            "topic": "career",
            "last_claim": "career window opens mid-2026",
            "dates_on_table": ["2026-06-14"],
            "open_loop": "which direction",
            "user_facts": ["working"],
            "awaiting": None,
            "last_archetype": "read",
        }
    }
    block = focus_prompt_block(profile)
    assert "career window opens mid-2026" in block
    assert "2026-06-14" in block
    assert "last_claim" in block
