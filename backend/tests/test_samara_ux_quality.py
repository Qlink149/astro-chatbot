"""Samara WhatsApp UX quality guards (thinking strip, check-in, door, want-more)."""

from __future__ import annotations

from kisna_chatbot.utils.llm_output_guard import strip_llm_meta
from kisna_chatbot.utils.samara_beats import (
    BTN_WANT_MORE,
    beat1_confirm_buttons,
    beat2a_confirm_buttons,
    is_beat2c_skip_token,
    parse_want_more_choice,
    theme_texture_phrase,
    want_more_buttons,
)
from kisna_chatbot.utils.samara_gate import door_gate_body


def test_strip_llm_meta_removes_thinking_before_separator():
    leak = (
        "Got it. The user confirmed the turning point but didn't describe what happened. "
        "I'll invite briefly once—just asking if they want to share what shifted—"
        "without pushing. I'll keep it warm, short, and conversational.\n\n"
        "---\n\n"
        "Samajh gayi. Something did shift around then. If you feel like sharing "
        "what it was, main sun rahi hoon — otherwise we can move ahead from here."
    )
    out = strip_llm_meta(leak)
    assert "Got it" not in out
    assert "The user confirmed" not in out
    assert "I'll invite" not in out
    assert "Samajh gayi" in out
    assert "main sun rahi hoon" in out


def test_strip_llm_meta_drops_leading_meta_lines_without_separator():
    leak = (
        "The user confirmed the turning point.\n"
        "I'll keep it warm.\n"
        "Something shifted for you around then — want to share what it was?"
    )
    out = strip_llm_meta(leak)
    assert "The user confirmed" not in out
    assert "Something shifted" in out


def test_beat1_single_checkin_strips_llm_confirm():
    qr = beat1_confirm_buttons(
        "You think fast, decide quickly.\nDoes that feel right?",
        lang="english",
        profile={},
    )
    text = qr["text"]
    assert "Does that feel right" not in text
    assert text.count("?") == 1


def test_beat2a_single_checkin():
    qr = beat2a_confirm_buttons(
        "Between 17 and 21 you carried a lot alone.\nAm I reading you right?",
        lang="english",
        profile={"last_checkin_phrase_id": 0},
    )
    text = qr["text"]
    assert text.count("?") == 1
    assert "Am I reading you right?" not in text or text.strip().endswith(
        tuple(
            (
                "Am I reading you right?",
                "Does that land?",
                "Am I on the right track?",
                "Does this feel familiar?",
            )
        )
    )


def test_want_more_parse_ack_more_enough():
    assert (
        parse_want_more_choice({"type": "text", "text": {"body": "Okay"}}) == "ack"
    )
    assert (
        parse_want_more_choice({"type": "text", "text": {"body": "thanks"}}) == "ack"
    )
    assert (
        parse_want_more_choice({"type": "text", "text": {"body": "Want more"}})
        == "more"
    )
    assert (
        parse_want_more_choice(
            {
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": BTN_WANT_MORE, "title": "Want more"}
                },
            }
        )
        == "more"
    )
    assert (
        parse_want_more_choice(
            {"type": "text", "text": {"body": "enough for now"}}
        )
        == "enough"
    )


def test_want_more_buttons_shape():
    qr = want_more_buttons(lang="english", body="Want to go deeper?")
    assert qr["type"] == "quickreply"
    assert len(qr["options"]) == 2
    assert any(o["postbackText"] == BTN_WANT_MORE for o in qr["options"])


def test_beat2c_skip_tokens():
    assert is_beat2c_skip_token("okay")
    assert is_beat2c_skip_token("ok")
    assert is_beat2c_skip_token("next")
    assert not is_beat2c_skip_token("Watched stranger things")
    assert not is_beat2c_skip_token("I changed jobs")


def test_theme_texture_phrases():
    phrase = theme_texture_phrase("responsibility", lang="english")
    assert "carrying" in phrase.lower()
    assert "effort vs recognition" not in phrase.lower()


def test_door_gate_body_not_fixed_canned_paragraph():
    profile = {
        "user_language": "english",
        "chosen_topic": "money",
        "chart_json": {
            "turning_points": [
                {"window_label_en": "mid 2017"},
                {"window_label_en": "early 2020"},
            ]
        },
    }
    body = door_gate_body(profile, amount_inr=39)
    assert "That answer stands on its own" not in body
    assert (
        "Which month matters most, what to lean into, and what to avoid — "
        "I can lay out that full picture when you're ready."
    ) not in body
    assert "mid 2017" in body
    assert "early 2020" in body
    assert "₹39" in body or "39" in body
    assert "money" in body.lower()
