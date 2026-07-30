"""Beat UI helpers for Samara WhatsApp conversation.

Buttons, postback parsing, message splitting, and beat constants.
LLM never calculates charts here — only presentation helpers.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── Beat states on user_profile["conversation_beat"] ─────────────────────────
BEAT_AWAITING_LANGUAGE = "awaiting_language"
BEAT_1_AWAITING_CONFIRM = "beat1_awaiting_confirm"
BEAT_2_AWAITING_ADVANCE = "beat2_awaiting_advance"
BEAT_AWAITING_TOPIC = "awaiting_topic"
BEAT_POST_FREE_DEEP = "post_free_deep"
BEAT_RETURNING_MENU = "returning_menu"

ACTIVE_INTRO_BEATS = frozenset(
    {
        BEAT_AWAITING_LANGUAGE,
        BEAT_1_AWAITING_CONFIRM,
        BEAT_2_AWAITING_ADVANCE,
        BEAT_AWAITING_TOPIC,
    }
)

MAX_LINES_PER_MESSAGE = 6

# Button postbacks
BTN_BEAT1_YES = "samara_beat1_yes"
BTN_BEAT1_SOFT = "samara_beat1_soft"
BTN_BEAT2_NEXT = "samara_beat2_next"
BTN_TOPIC_CAREER = "samara_topic_career"
BTN_TOPIC_LOVE = "samara_topic_love"
BTN_TOPIC_MONEY = "samara_topic_money"
BTN_TOPIC_FAMILY = "samara_topic_family"
BTN_TOPIC_DECISION = "samara_topic_decision"
BTN_RET_CONTINUE = "samara_ret_continue"
BTN_RET_NEW = "samara_ret_new"
BTN_RET_MUHURAT = "samara_ret_muhurat"

TOPIC_BY_POSTBACK = {
    BTN_TOPIC_CAREER: "career",
    BTN_TOPIC_LOVE: "love",
    BTN_TOPIC_MONEY: "money",
    BTN_TOPIC_FAMILY: "family",
    BTN_TOPIC_DECISION: "decision",
}

TOPIC_LABELS = {
    "career": "Career",
    "love": "Shaadi-Pyaar",
    "money": "Paisa",
    "family": "Ghar-Parivaar",
    "decision": "Bada Faisla",
}


def inbound_message_id(messages: dict | None) -> str:
    if not isinstance(messages, dict):
        return ""
    return str(messages.get("id") or "").strip()


def claim_beat_transition(
    profile: dict,
    *,
    expected_beats: tuple[str | None, ...],
    next_beat: str,
    inbound_id: str,
) -> bool:
    """Idempotent beat advance. Returns False if duplicate or wrong state.

    Duplicate Gupshup delivery (same inbound id) must not advance or skip.
    """
    if inbound_id and profile.get("beat_last_inbound_id") == inbound_id:
        return False
    current = profile.get("conversation_beat")
    if current not in expected_beats:
        return False
    profile["conversation_beat"] = next_beat
    if inbound_id:
        profile["beat_last_inbound_id"] = inbound_id
    return True


def mark_beat_send(profile: dict, beat: str, inbound_id: str = "") -> None:
    """Record that we sent a beat (state after outbound)."""
    profile["conversation_beat"] = beat
    if inbound_id:
        profile["beat_last_inbound_id"] = inbound_id


def split_whatsapp_text(text: str, max_lines: int = MAX_LINES_PER_MESSAGE) -> list[str]:
    """Split long reading text into WhatsApp-sized chunks (~max_lines each)."""
    raw = (text or "").strip()
    if not raw:
        return []
    lines = raw.split("\n")
    # If few lines but very long paragraphs, also break on blank lines / sentences.
    chunks: list[str] = []
    buf: list[str] = []
    for line in lines:
        buf.append(line)
        if len(buf) >= max_lines:
            chunks.append("\n".join(buf).strip())
            buf = []
    if buf:
        chunks.append("\n".join(buf).strip())
    # Further split any oversized single chunk by sentences.
    final: list[str] = []
    for chunk in chunks:
        if chunk.count("\n") < max_lines and len(chunk) < 900:
            final.append(chunk)
            continue
        sentences = re.split(r"(?<=[.!?।])\s+", chunk)
        part: list[str] = []
        for s in sentences:
            trial = (" ".join(part + [s])).strip()
            if part and (trial.count("\n") >= max_lines or len(trial) > 900):
                final.append(" ".join(part).strip())
                part = [s]
            else:
                part.append(s)
        if part:
            final.append(" ".join(part).strip())
    return [c for c in final if c]


def text_responses(text: str) -> list[dict]:
    return [{"type": "text", "text": chunk} for chunk in split_whatsapp_text(text)]


def _quickreply(
    text: str,
    msgid: str,
    options: list[dict],
    caption: str = "Choose one",
) -> dict:
    return {
        "type": "quickreply",
        "text": text,
        "caption": caption,
        "msgid": msgid,
        "options": options,
    }


def beat1_confirm_buttons(body: str, *, lang: str) -> dict:
    if lang == "english":
        yes_t, soft_t = "Yes, exactly", "A little bit"
    else:
        yes_t, soft_t = "Haan, bilkul", "Thoda sa"
    return _quickreply(
        body,
        "samara_beat1_confirm",
        [
            {"type": "text", "title": yes_t, "postbackText": BTN_BEAT1_YES},
            {"type": "text", "title": soft_t, "postbackText": BTN_BEAT1_SOFT},
        ],
    )


def beat2_next_button(body: str, *, lang: str) -> dict:
    title = "Tell me more" if lang == "english" else "Aage batao"
    return _quickreply(
        body,
        "samara_beat2_next",
        [{"type": "text", "title": title, "postbackText": BTN_BEAT2_NEXT}],
    )


def topic_picker_buttons(*, lang: str) -> dict:
    if lang == "english":
        text = "Which one area should we look at more closely?"
        labels = {
            "career": "Career",
            "love": "Love & marriage",
            "money": "Money",
            "family": "Home & family",
            "decision": "Big decision",
        }
    else:
        text = "Kaunsa ek area aur gehraai se dekhna hai?"
        labels = TOPIC_LABELS
    return _quickreply(
        text,
        "samara_topic_pick",
        [
            {
                "type": "text",
                "title": labels["career"][:20],
                "postbackText": BTN_TOPIC_CAREER,
            },
            {
                "type": "text",
                "title": labels["love"][:20],
                "postbackText": BTN_TOPIC_LOVE,
            },
            {
                "type": "text",
                "title": labels["money"][:20],
                "postbackText": BTN_TOPIC_MONEY,
            },
            {
                "type": "text",
                "title": labels["family"][:20],
                "postbackText": BTN_TOPIC_FAMILY,
            },
            {
                "type": "text",
                "title": labels["decision"][:20],
                "postbackText": BTN_TOPIC_DECISION,
            },
        ],
        caption="Pick one topic",
    )


def returning_menu_buttons(*, lang: str, name: str) -> dict:
    if lang == "english":
        text = (
            f"Welcome back{', ' + name if name and name != 'dost' else ''}. "
            "Where would you like to continue?"
        )
        opts = [
            ("Continue earlier", BTN_RET_CONTINUE),
            ("New question", BTN_RET_NEW),
            ("Today's muhurat", BTN_RET_MUHURAT),
        ]
    else:
        text = (
            f"Namaste phir se{', ' + name if name and name != 'dost' else ''} 🙏 "
            "Aaj kahan se shuru karein?"
        )
        opts = [
            ("Wahi baat aage", BTN_RET_CONTINUE),
            ("Naya sawaal", BTN_RET_NEW),
            ("Aaj ka muhurat", BTN_RET_MUHURAT),
        ]
    return _quickreply(
        text,
        "samara_returning",
        [{"type": "text", "title": t[:20], "postbackText": p} for t, p in opts],
    )


def _extract_postback(messages: dict) -> tuple[str, str]:
    """Return (postback_id, title_lower) from interactive/button/text."""
    if not isinstance(messages, dict):
        return "", ""
    mtype = messages.get("type")
    if mtype == "interactive":
        inter = messages.get("interactive") or {}
        br = inter.get("button_reply") or {}
        raw_id = str(br.get("id") or "")
        title = str(br.get("title") or "").strip().lower()
        try:
            parsed = json.loads(raw_id) if raw_id else None
            if isinstance(parsed, dict):
                raw_id = str(
                    parsed.get("msgid")
                    or parsed.get("postbackText")
                    or raw_id
                )
        except (json.JSONDecodeError, TypeError):
            pass
        return raw_id, title
    if mtype == "button":
        btn = messages.get("button") or {}
        return str(btn.get("payload") or "").strip(), str(btn.get("text") or "").strip().lower()
    if mtype == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip()
        return "", body.lower()
    return "", ""


def parse_beat1_confirm(messages: dict) -> str | None:
    """Return 'yes' | 'soft' | None."""
    pid, title = _extract_postback(messages)
    if pid == BTN_BEAT1_YES or title in (
        "haan, bilkul",
        "haan bilkul",
        "yes, exactly",
        "yes exactly",
        "haan",
        "yes",
    ):
        return "yes"
    if pid == BTN_BEAT1_SOFT or title in (
        "thoda sa",
        "a little bit",
        "thoda",
        "a little",
    ):
        return "soft"
    return None


def parse_beat2_advance(messages: dict) -> bool:
    pid, title = _extract_postback(messages)
    if pid == BTN_BEAT2_NEXT:
        return True
    return title in ("aage batao", "tell me more", "aage", "next")


def parse_topic_choice(messages: dict) -> str | None:
    pid, title = _extract_postback(messages)
    if pid in TOPIC_BY_POSTBACK:
        return TOPIC_BY_POSTBACK[pid]
    # Title / plain text fallbacks
    mapping = {
        "career": "career",
        "shaadi-pyaar": "love",
        "shaadi": "love",
        "pyaar": "love",
        "love": "love",
        "love & marriage": "love",
        "paisa": "money",
        "money": "money",
        "ghar-parivaar": "family",
        "ghar": "family",
        "home & family": "family",
        "family": "family",
        "bada faisla": "decision",
        "big decision": "decision",
        "faisla": "decision",
    }
    return mapping.get(title)


def parse_returning_choice(messages: dict) -> str | None:
    """Return 'continue' | 'new' | 'muhurat' | None."""
    pid, title = _extract_postback(messages)
    if pid == BTN_RET_CONTINUE or title in (
        "wahi baat aage",
        "continue earlier",
        "continue",
    ):
        return "continue"
    if pid == BTN_RET_NEW or title in ("naya sawaal", "new question", "naya"):
        return "new"
    if pid == BTN_RET_MUHURAT or title in (
        "aaj ka muhurat",
        "today's muhurat",
        "muhurat",
    ):
        return "muhurat"
    return None


def looks_like_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or len(t) > 40:
        return False
    greetings = (
        "hi",
        "hello",
        "hey",
        "namaste",
        "namaskar",
        "hola",
        "good morning",
        "good evening",
        "good afternoon",
        "start",
        "menu",
    )
    return t in greetings or t.rstrip("!.") in greetings


def relevant_dasha_slice(chart: dict | None) -> list[dict[str, Any]]:
    """Engine-side filter helper for prompts — only is_relevant periods."""
    timeline = (chart or {}).get("dasha_timeline") or []
    return [p for p in timeline if isinstance(p, dict) and p.get("is_relevant")]
