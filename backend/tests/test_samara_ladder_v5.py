"""Ladder v5 — test-me beat, forced-choice 2a, answerable 2c second window,
name-your-three before the free Beat 4, and the ₹-tap paywall route.

Guards the routing bugs the teardown found: a question Samara asks must land
in a state that can receive the answer.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

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

from kisna_chatbot.main import app  # noqa: F401 — env/logger init before agent

import kisna_chatbot.processors.samara_reading_agent as mod
from kisna_chatbot.utils.samara_beats import (
    BEAT_1_AWAITING_CONFIRM,
    BEAT_2A_AWAITING_CONFIRM,
    BEAT_2B_AWAITING_CONFIRM,
    BEAT_2C_SECOND_WINDOW,
    BEAT_AWAITING_ITEMS,
    BEAT_AWAITING_TOPIC,
    BEAT_TEST_ME_YEAR,
    BTN_BEAT1_YES,
    BTN_BEAT2A_OPT_A,
    BTN_BEAT2A_NEITHER,
    BTN_TOPIC_MONEY,
    beat2a_choice_options,
    parse_user_items,
)

CHART = {
    "meta": {
        "birth_year": 2004,
        "current_age": 22,
        "chart_type": "full",
        "has_birth_time": True,
        "dated_anchors_available": True,
    },
    "dasha_timeline": [
        {"planet_en": "Ketu", "phase": "past", "is_relevant": True},
        {"planet_en": "Venus", "phase": "current", "is_relevant": True},
    ],
    "antardasha_timeline": [
        {
            "start": "2023-03-28",
            "end": "2024-05-06",
            "maha_planet_en": "Ketu",
            "antar_planet_en": "Saturn",
            "window_label_month_en": "March–April 2023",
            "window_label_month_hi": "March–April 2023 ke aas-paas",
        }
    ],
    "turning_points": [
        {
            "start": "2023-03-28",
            "age_start": 19,
            "age_end": 20,
            "theme_en": "responsibility",
            "theme_hi": "zimmedari",
            "window_label_en": "early 2023",
            "window_label_month_en": "March–April 2023",
            "window_label_month_hi": "March–April 2023 ke aas-paas",
        },
        {
            "start": "2024-05-06",
            "age_start": 20,
            "age_end": 21,
            "theme_en": "drive",
            "theme_hi": "urja",
            "window_label_en": "mid 2024",
            "window_label_month_en": "May 2024",
            "window_label_month_hi": "May 2024 ke aas-paas",
        },
    ],
    "upcoming_periods": [{"start": "2028-10-10", "antar_planet_en": "Sun"}],
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _profile(**over):
    base = {
        "username": "Aarav",
        "preferred_name": "Aarav",
        "chat_history": [],
        "chart_json": CHART,
        "user_language": "english",
        "credits": 0,
        "credit_ledger": [],
        "trust_score": 2,
    }
    base.update(over)
    return base


def _btn(pid, title=""):
    return {
        "type": "interactive",
        "interactive": {"button_reply": {"id": pid, "title": title}},
    }


def _text(body):
    return {"type": "text", "text": {"body": body}}


def _envelope(profile, messages):
    return {
        "client_id": "samara",
        "phone_number": "919999999999",
        "user_profile": profile,
        "messages": messages,
    }


def _process(profile, messages, llm=None):
    agent = mod.SamaraReadingAgent()
    llm = llm or AsyncMock(return_value="Chart line one.\nChart line two.")
    with patch.object(mod.SamaraReadingAgent, "_llm", new=llm):
        return _run(agent.process(_envelope(profile, messages)))


# ── Test-me beat ─────────────────────────────────────────────────────────────


def test_beat1_confirm_goes_to_the_dated_ladder_not_test_me():
    """Beat 2b must land an unprompted month BEFORE the user names any year —
    otherwise every date Samara says is one the user supplied first."""
    profile = _profile(conversation_beat=BEAT_1_AWAITING_CONFIRM)
    out = _process(profile, _btn(BTN_BEAT1_YES, "yes"))
    assert profile["conversation_beat"] == BEAT_2A_AWAITING_CONFIRM
    joined = " ".join(
        r.get("text", "") for r in out["bot_response"] if isinstance(r, dict)
    ).lower()
    assert "test me" not in joined
    assert not profile.get("test_me_offered")


def test_test_me_is_offered_after_beat2c_completes():
    agent = mod.SamaraReadingAgent()
    profile = _profile(
        beat2_pending_window=CHART["turning_points"][1],
        beat2c_second_offered=True,  # second window already spent
        confirmed_events=[],
    )
    data = {"messages": _text("x"), "bot_response": []}
    with patch.object(
        mod.SamaraReadingAgent, "_llm", new=AsyncMock(return_value="Reflect line.")
    ):
        out = _run(
            agent._send_beat2c(
                data, profile, "919999999999", "in-9",
                description="switched courses", bare_haan=False,
            )
        )
    assert profile["conversation_beat"] == BEAT_TEST_ME_YEAR
    assert profile["test_me_offered"] is True
    assert out["bot_response"][-1]["msgid"] == "samara_test_me"
    body = out["bot_response"][-1]["text"].lower()
    assert "test me" in body
    # Samara names the period, never the event.
    assert "what happened" in body
    # The reflect still goes out ahead of the offer.
    assert out["bot_response"][0]["text"] == "Reflect line."


def test_test_me_beat_receives_a_typed_year():
    """The bug: this reply used to be swallowed by the topic picker."""
    profile = _profile(
        conversation_beat=BEAT_TEST_ME_YEAR, test_me_offered=True
    )
    out = _process(profile, _text("2023"))
    joined = " ".join(
        r.get("text", "") for r in out["bot_response"] if isinstance(r, dict)
    )
    assert "March–April 2023" in joined
    assert profile["test_me_count"] == 1
    assert profile["conversation_beat"] == BEAT_TEST_ME_YEAR  # more challenges left


def test_consecutive_challenges_do_not_reuse_the_same_sentence():
    """Two identical templates in a row expose the mad-lib and burn the feature."""
    agent = mod.SamaraReadingAgent()
    rows = [
        {
            "start": f"{y}-03-01",
            "end": f"{y + 1}-03-01",
            "maha_planet_en": "Venus",
            "antar_planet_en": "Saturn",
            "window_label_month_en": f"March {y}",
            "window_label_month_hi": f"March {y} ke aas-paas",
        }
        for y in (2021, 2022, 2023)
    ]
    profile = _profile(chart_json={"antardasha_timeline": rows})
    bodies = []
    for year in (2021, 2022, 2023):
        data: dict = {}
        agent._handle_test_me_year(data, profile, "919999999999", str(year))
        bodies.append(data["bot_response"][0]["text"])
    # Strip the year so we compare the sentence shape, not the data.
    shapes = [b.replace("2021", "Y").replace("2022", "Y").replace("2023", "Y") for b in bodies]
    assert len(set(shapes)) == 3
    assert profile["test_me_years"] == [2021, 2022, 2023]


def test_second_window_skips_a_year_already_spent_on_test_me():
    agent = mod.SamaraReadingAgent()
    profile = _profile(
        beat2_pending_window=CHART["turning_points"][1],   # May 2024
        test_me_years=[2023],                              # already shown
        test_me_used=True,                                 # isolate the window logic
        confirmed_events=[],
    )
    data = {"messages": _text("x"), "bot_response": []}
    with patch.object(
        mod.SamaraReadingAgent, "_llm", new=AsyncMock(return_value="Reflect line.")
    ):
        _run(
            agent._send_beat2c(
                data, profile, "919999999999", "in-3",
                description="switched courses", bare_haan=False,
            )
        )
    # Only 2023 was left to offer, and it's burned — go straight to topics.
    assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
    assert not profile.get("beat2c_second_pending")


def test_test_me_skip_goes_to_topics():
    profile = _profile(conversation_beat=BEAT_TEST_ME_YEAR, test_me_offered=True)
    out = _process(profile, _text("skip"))
    assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
    assert out["bot_response"][-1]["msgid"] == "samara_topic_pick"


def test_test_me_non_year_text_does_not_trap_the_user():
    profile = _profile(conversation_beat=BEAT_TEST_ME_YEAR, test_me_offered=True)
    _process(profile, _text("what does that even mean"))
    assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC


def test_third_challenge_answers_then_hands_over_to_topics():
    profile = _profile(
        conversation_beat=BEAT_TEST_ME_YEAR,
        test_me_offered=True,
        test_me_count=2,
    )
    out = _process(profile, _text("2023"))
    joined = " ".join(
        r.get("text", "") for r in out["bot_response"] if isinstance(r, dict)
    )
    assert "March–April 2023" in joined  # answered, not swallowed
    assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
    assert out["bot_response"][-1]["msgid"] == "samara_topic_pick"


def test_year_typed_at_topic_picker_is_answered_not_discarded():
    profile = _profile(
        conversation_beat=BEAT_AWAITING_TOPIC,
        test_me_offered=True,
        test_me_count=0,
    )
    out = _process(profile, _text("what about 2023"))
    joined = " ".join(
        r.get("text", "") for r in out["bot_response"] if isinstance(r, dict)
    )
    assert "March–April 2023" in joined
    # Picker still offered so the ladder keeps moving.
    assert any(r.get("msgid") == "samara_topic_pick" for r in out["bot_response"])


# ── Forced-choice Beat 2a ────────────────────────────────────────────────────


def test_beat2a_choice_options_are_two_distinct_short_labels():
    from kisna_chatbot.utils.samara_beats import beat2a_quality_points

    labels = beat2a_choice_options(
        beat2a_quality_points(CHART), lang="english"
    )
    assert len(labels) == 2
    assert labels[0] != labels[1]
    assert all(len(x) <= 20 for x in labels)


def test_forced_choice_gives_no_politeness_trust_credit():
    profile = _profile(
        conversation_beat=BEAT_2A_AWAITING_CONFIRM,
        beat2a_choice_labels=["Held it together", "No finish line"],
        trust_score=2,
    )
    _process(profile, _btn(BTN_BEAT2A_OPT_A, "held it together"))
    # Picking between two textures is not agreement — score must not inflate.
    assert profile["trust_score"] == 2
    assert profile["beat2a_chosen_texture"] == "Held it together"
    assert profile["conversation_beat"] == BEAT_2B_AWAITING_CONFIRM


def test_forced_choice_keeps_a_real_rejection_path():
    """'Neither' must still be a negative signal — forced choice is not a trap."""
    profile = _profile(
        conversation_beat=BEAT_2A_AWAITING_CONFIRM,
        beat2a_choice_labels=["Held it together", "No finish line"],
        trust_score=4,
    )
    _process(profile, _btn(BTN_BEAT2A_NEITHER, "neither, really"))
    assert profile["trust_score"] == 2
    assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC


def test_forced_choice_neither_can_still_trigger_trust_recovery():
    profile = _profile(
        conversation_beat=BEAT_2A_AWAITING_CONFIRM,
        beat2a_choice_labels=["Held it together", "No finish line"],
        trust_score=2,
        trust_scored=True,
    )
    _process(profile, _btn(BTN_BEAT2A_NEITHER, "neither, really"))
    assert profile["trust_score"] == 0
    assert profile["conversation_beat"] == "trust_recovery"


# ── Beat 2c second window is answerable ──────────────────────────────────────


def test_second_window_question_lands_in_a_state_that_can_answer_it():
    agent = mod.SamaraReadingAgent()
    profile = _profile(
        conversation_beat="beat2c_awaiting_detail",
        beat2_pending_window=CHART["turning_points"][1],
        confirmed_events=[{"start_date": "2024-05-06"}],
    )
    data = {"messages": _text("switched courses"), "bot_response": []}
    with patch.object(
        mod.SamaraReadingAgent,
        "_llm",
        new=AsyncMock(return_value="That fits the window.\nAnd March–April 2023?"),
    ):
        out = _run(
            agent._send_beat2c(
                data,
                profile,
                "919999999999",
                "in-1",
                description="switched courses",
                bare_haan=False,
            )
        )
    assert profile["conversation_beat"] == BEAT_2C_SECOND_WINDOW
    assert profile["beat2c_second_pending"]["start"] == "2023-03-28"
    # No topic picker buried under the open question.
    assert not any(
        r.get("msgid") == "samara_topic_pick" for r in out["bot_response"]
    )


def test_second_window_answer_is_recorded_then_test_me_offer():
    profile = _profile(
        conversation_beat=BEAT_2C_SECOND_WINDOW,
        beat2c_second_offered=True,
        beat2c_second_pending=CHART["turning_points"][0],
        confirmed_events=[],
        trust_score=2,
    )
    _process(profile, _text("changed my course, family was not happy"))
    events = profile["confirmed_events"]
    assert len(events) == 1
    assert "family was not happy" in events[0]["user_description"]
    assert profile["trust_score"] == 5  # +2 confirm, +1 description
    # 2c is complete → year challenge, which then hands over to topics.
    assert profile["conversation_beat"] == BEAT_TEST_ME_YEAR


def test_second_window_is_offered_at_most_once():
    agent = mod.SamaraReadingAgent()
    profile = _profile(
        beat2_pending_window=CHART["turning_points"][1],
        beat2c_second_offered=True,
        test_me_used=True,  # challenge already spent → straight to topics
    )
    data = {"messages": _text("x"), "bot_response": []}
    with patch.object(
        mod.SamaraReadingAgent, "_llm", new=AsyncMock(return_value="Reflect line.")
    ):
        out = _run(
            agent._send_beat2c(
                data, profile, "919999999999", "in-2",
                description="x", bare_haan=False,
            )
        )
    assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
    assert any(r.get("msgid") == "samara_topic_pick" for r in out["bot_response"])


# ── Name your three → Beat 4 ─────────────────────────────────────────────────


def test_parse_user_items_keeps_the_users_own_words():
    items = parse_user_items("reels page, print business idea and freelance design")
    assert items == ["reels page", "print business idea", "freelance design"]
    assert parse_user_items("") == []
    # Caps at three so the prompt never receives a laundry list.
    assert len(parse_user_items("one, two, three, four, five")) == 3
    # Single characters aren't projects.
    assert parse_user_items("a, b, c") == []
    # Hinglish separator.
    assert parse_user_items("reels aur printing") == ["reels", "printing"]


def test_topic_pick_asks_for_items_before_the_free_deep_answer():
    profile = _profile(conversation_beat=BEAT_AWAITING_TOPIC)
    out = _process(profile, _btn(BTN_TOPIC_MONEY, "money"))
    assert profile["conversation_beat"] == BEAT_AWAITING_ITEMS
    assert profile["chosen_topic"] == "money"
    body = out["bot_response"][-1]["text"]
    assert "half-doing" in body.lower()
    # RULE 6: nothing has been gated — the free answer is still ahead.
    assert not profile.get("free_deep_answer_used")


def test_items_reach_beat4_prompt_verbatim_and_free():
    profile = _profile(
        conversation_beat=BEAT_AWAITING_ITEMS, chosen_topic="money"
    )
    llm = AsyncMock(return_value="Money read.\nSecond line.")
    _process(profile, _text("reels page, print idea, freelance design"), llm=llm)
    assert profile["user_items"] == [
        "reels page",
        "print idea",
        "freelance design",
    ]
    instruction = llm.await_args.kwargs["instruction"]
    assert "reels page" in instruction
    assert "print idea" in instruction
    # Far-window honesty is handed to the prompt, not invented by it.
    assert "far" in instruction
    assert profile["free_deep_answer_used"] is True


def test_items_skip_still_delivers_the_free_answer():
    profile = _profile(
        conversation_beat=BEAT_AWAITING_ITEMS, chosen_topic="money"
    )
    _process(profile, _text("skip"))
    assert profile["user_items"] == []
    assert profile["free_deep_answer_used"] is True


# ── ₹ tap on the door ────────────────────────────────────────────────────────


def test_rupee_tap_goes_straight_to_a_payment_link():
    profile = _profile(
        conversation_beat="post_free_deep",
        free_deep_answer_used=True,
        bot_asked_question=True,  # cliff QR was outstanding
    )
    agent = mod.SamaraReadingAgent()
    with patch.object(
        mod.SamaraReadingAgent,
        "_create_pwyw_payment_link",
        new=AsyncMock(side_effect=lambda d, p, ph, amt: {**d, "amount": amt}),
    ):
        out = _run(
            agent.process(_envelope(profile, _btn("samara_pwyw_amt_99", "₹99")))
        )
    # A tap is a decision, never free text answering the previous question.
    assert out.get("amount") == 99.0
