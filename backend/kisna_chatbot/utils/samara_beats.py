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
BEAT_AWAITING_NAME = "awaiting_name"
BEAT_1_AWAITING_CONFIRM = "beat1_awaiting_confirm"
BEAT_2_AWAITING_ADVANCE = "beat2_awaiting_advance"  # undated fallback only
BEAT_2A_AWAITING_CONFIRM = "beat2a_awaiting_confirm"
BEAT_2B_AWAITING_CONFIRM = "beat2b_awaiting_confirm"
BEAT_2B_ALT_AWAITING = "beat2b_alt_awaiting"
BEAT_2C_AWAITING_DETAIL = "beat2c_awaiting_detail"
BEAT_AWAITING_TOPIC = "awaiting_topic"
BEAT_POST_FREE_DEEP = "post_free_deep"
BEAT_RETURNING_MENU = "returning_menu"
BEAT_TRUST_RECOVERY = "trust_recovery"

ACTIVE_INTRO_BEATS = frozenset(
    {
        BEAT_AWAITING_LANGUAGE,
        BEAT_AWAITING_NAME,
        BEAT_1_AWAITING_CONFIRM,
        BEAT_2_AWAITING_ADVANCE,
        BEAT_2A_AWAITING_CONFIRM,
        BEAT_2B_AWAITING_CONFIRM,
        BEAT_2B_ALT_AWAITING,
        BEAT_2C_AWAITING_DETAIL,
        BEAT_AWAITING_TOPIC,
    }
)

MAX_LINES_PER_MESSAGE = 6
MAX_DATED_WINDOWS_PER_SESSION = 2

# Button postbacks
BTN_BEAT1_YES = "samara_beat1_yes"
BTN_BEAT1_SOFT = "samara_beat1_soft"
BTN_BEAT2_NEXT = "samara_beat2_next"
BTN_BEAT2A_YES = "samara_beat2a_yes"
BTN_BEAT2A_NO = "samara_beat2a_no"
BTN_BEAT2B_YES = "samara_beat2b_yes"
BTN_BEAT2B_NO = "samara_beat2b_no"
BTN_TOPIC_CAREER = "samara_topic_career"
BTN_TOPIC_LOVE = "samara_topic_love"
BTN_TOPIC_MONEY = "samara_topic_money"
BTN_TOPIC_FAMILY = "samara_topic_family"
BTN_TOPIC_DECISION = "samara_topic_decision"
BTN_RET_CONTINUE = "samara_ret_continue"
BTN_RET_NEW = "samara_ret_new"
BTN_RET_MUHURAT = "samara_ret_muhurat"
BTN_PAYWALL_PAY = "samara_paywall_pay"
BTN_PAYWALL_LATER = "samara_paywall_later"
BTN_WANT_MORE = "samara_want_more"
BTN_ENOUGH_FOR_NOW = "samara_enough_for_now"

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

TOPIC_LABELS_EN = {
    "career": "career",
    "love": "love & marriage",
    "money": "money",
    "family": "family",
    "decision": "a big decision",
}

TOPIC_LABELS_HI = {
    "career": "career",
    "love": "shaadi-pyaar",
    "money": "paisa",
    "family": "ghar-parivaar",
    "decision": "bade faisle",
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


def beat2a_confirm_buttons(body: str, *, lang: str) -> dict:
    if lang == "english":
        yes_t, no_t = "Yes, that's right", "No, not really"
    else:
        yes_t, no_t = "Haan, sahi hai", "Nahi, aisa nahi"
    return _quickreply(
        body,
        "samara_beat2a_confirm",
        [
            {"type": "text", "title": yes_t[:20], "postbackText": BTN_BEAT2A_YES},
            {"type": "text", "title": no_t[:20], "postbackText": BTN_BEAT2A_NO},
        ],
    )


def beat2b_confirm_buttons(body: str, *, lang: str) -> dict:
    if lang == "english":
        yes_t, no_t = "Yes, something did", "No"
    else:
        yes_t, no_t = "Haan, hua tha", "Nahi"
    return _quickreply(
        body,
        "samara_beat2b_confirm",
        [
            {"type": "text", "title": yes_t[:20], "postbackText": BTN_BEAT2B_YES},
            {"type": "text", "title": no_t[:20], "postbackText": BTN_BEAT2B_NO},
        ],
    )


def parse_beat2a_confirm(messages: dict) -> str | None:
    """Return 'yes' | 'no' | None."""
    pid, title = _extract_postback(messages)
    if pid == BTN_BEAT2A_YES or title in (
        "haan, sahi hai",
        "haan sahi hai",
        "yes, that's right",
        "yes thats right",
        "yes",
        "haan",
    ):
        return "yes"
    if pid == BTN_BEAT2A_NO or title in (
        "nahi, aisa nahi",
        "nahi aisa nahi",
        "no, not really",
        "no not really",
        "nahi",
        "no",
    ):
        return "no"
    return None


def parse_beat2b_confirm(messages: dict) -> tuple[str | None, str]:
    """Return (result, free_text).

    result: 'yes' | 'no' | 'text' | None
    free_text: user description when they typed instead of tapping.
    """
    pid, title = _extract_postback(messages)
    if pid == BTN_BEAT2B_YES or title in (
        "haan, hua tha",
        "haan hua tha",
        "yes, something did",
        "yes something did",
    ):
        return "yes", ""
    if pid == BTN_BEAT2B_NO or title in ("nahi", "no"):
        return "no", ""
    if isinstance(messages, dict) and messages.get("type") == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip()
        if not body:
            return None, ""
        low = body.lower()
        if low in ("nahi", "no", "nahin", "nope"):
            return "no", ""
        if low in ("haan", "haan hua tha", "yes", "yes something did"):
            return "yes", ""
        # Free-text description = confirmation with detail
        return "text", body
    return None, ""


def dated_anchors_available(chart: dict | None) -> bool:
    meta = (chart or {}).get("meta") or {}
    return bool(meta.get("dated_anchors_available"))


def beat2a_quality_points(chart: dict | None) -> list[dict]:
    """Turning points usable for Beat 2a (age span ≤7 + theme). Empty → skip 2a."""
    out: list[dict] = []
    for p in (chart or {}).get("turning_points") or []:
        if not isinstance(p, dict):
            continue
        a0 = p.get("age_start")
        a1 = p.get("age_end")
        try:
            if a0 is None or a1 is None:
                continue
            a0i, a1i = int(a0), int(a1)
            if a1i < 15:
                continue
            if (a1i - a0i) > 7:
                continue
        except (TypeError, ValueError):
            continue
        if not (p.get("theme_en") or p.get("theme_hi")):
            continue
        out.append(
            {
                "age_start": a0i,
                "age_end": a1i,
                "theme_en": p.get("theme_en"),
                "theme_hi": p.get("theme_hi"),
                "window_label_en": p.get("window_label_en"),
                "window_label_hi": p.get("window_label_hi"),
            }
        )
    return out


def next_turning_point(profile: dict, chart: dict | None) -> dict | None:
    """Pick strongest unused turning point not in rejected_windows."""
    points = list((chart or {}).get("turning_points") or [])
    if not points:
        return None
    rejected = {
        str(r.get("start_date") or r.get("start") or "")
        for r in (profile.get("rejected_windows") or [])
        if isinstance(r, dict)
    }
    offered = set(profile.get("beat2_offered_starts") or [])
    # Prefer newest preferred points already curated; walk newest-first then
    # fall back chronological. turning_points are oldest→newest.
    for p in reversed(points):
        start = str(p.get("start") or "")
        if start and start not in rejected and start not in offered:
            return p
    return None


def topic_picker_buttons(*, lang: str) -> dict:
    if lang == "english":
        text = "Which area should we look at more closely?"
        options = [
            ("Career", BTN_TOPIC_CAREER),
            ("Love & marriage", BTN_TOPIC_LOVE),
            ("Money", BTN_TOPIC_MONEY),
        ]
    else:
        text = "Kaunsa ek area aur gehraai se dekhna hai?"
        options = [
            ("Career", BTN_TOPIC_CAREER),
            ("Shaadi-Pyaar", BTN_TOPIC_LOVE),
            ("Paisa", BTN_TOPIC_MONEY),
        ]
    return _quickreply(
        text,
        "samara_topic_pick",
        [
            {"type": "text", "title": t[:20], "postbackText": p}
            for t, p in options
        ],
        caption="Career / Love / Money — tap one",
    )


def topic_label_for(*, topic_key: str | None, lang: str) -> str:
    if not topic_key:
        return ""
    key = str(topic_key).strip().lower()
    if lang == "english":
        return TOPIC_LABELS_EN.get(key, TOPIC_LABELS.get(key, key))
    return TOPIC_LABELS_HI.get(key, TOPIC_LABELS.get(key, key))


def returning_menu_buttons(
    *, lang: str, name: str, last_topic_label: str | None = None
) -> dict:
    name_bit = f", {name}" if name and name != "dost" else ""
    topic = (last_topic_label or "").strip()
    if lang == "english":
        if topic:
            text = (
                f"Welcome back{name_bit} 🌙 Last time we talked about your {topic}. "
                "What would you like to look at today?"
            )
        else:
            text = (
                f"Welcome back{name_bit}. "
                "Where would you like to continue?"
            )
        opts = [
            ("Continue earlier", BTN_RET_CONTINUE),
            ("New question", BTN_RET_NEW),
            ("Today's muhurat", BTN_RET_MUHURAT),
        ]
    else:
        if topic:
            text = (
                f"Wapas aaye{name_bit}, achha laga 🌙 "
                f"Pichli baar humne aapke {topic} ki baat ki thi. "
                "Aaj kya dekhna chahenge?"
            )
        else:
            text = (
                f"Namaste phir se{name_bit} 🙏 "
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


def paywall_buttons(*, lang: str, body: str, amount_inr: float | None = None) -> dict:
    from kisna_chatbot.payments.service import test_payment_amount_inr

    amt = amount_inr if amount_inr is not None else test_payment_amount_inr()
    amt_s = str(int(amt)) if float(amt).is_integer() else f"{amt:g}"
    if lang == "english":
        pay_t = f"See more — ₹{amt_s}"[:20]
        later_t = "Later"
    else:
        pay_t = f"Haan — ₹{amt_s}"[:20]
        later_t = "Baad mein"
    return _quickreply(
        body,
        "samara_paywall",
        [
            {"type": "text", "title": pay_t, "postbackText": BTN_PAYWALL_PAY},
            {"type": "text", "title": later_t, "postbackText": BTN_PAYWALL_LATER},
        ],
        caption="Choose one",
    )


def want_more_buttons(*, lang: str, body: str) -> dict:
    """After free surface cliff — invite without burning another LLM call."""
    if lang == "english":
        yes_t, no_t = "Yes, tell me", "I'm good for now"
    else:
        yes_t, no_t = "Haan, batao", "Abhi theek hai"
    return _quickreply(
        body,
        "samara_want_more",
        [
            {"type": "text", "title": yes_t[:20], "postbackText": BTN_WANT_MORE},
            {"type": "text", "title": no_t[:20], "postbackText": BTN_ENOUGH_FOR_NOW},
        ],
        caption="Choose one",
    )


def parse_want_more_choice(messages: dict) -> str | None:
    """Return 'more' | 'enough' | None from cliff QR or free-text."""
    pid, title = _extract_postback(messages)
    if pid == BTN_WANT_MORE:
        return "more"
    if pid == BTN_ENOUGH_FOR_NOW:
        return "enough"
    body = title or ""
    if not body and isinstance(messages, dict) and messages.get("type") == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip().lower()
    body = (body or "").strip().lower()
    if not body:
        return None
    more_phrases = (
        "haan batao",
        "haan, batao",
        "aur batao",
        "aur jaanna",
        "tell me more",
        "yes tell me",
        "want to know more",
        "woh sunna",
        "filter batao",
        "aage batao",
    )
    enough_phrases = (
        "abhi theek",
        "i'm good",
        "im good",
        "theek hai abhi",
        "baad mein sochung",
        "enough for now",
    )
    if any(p in body for p in more_phrases):
        return "more"
    if any(p in body for p in enough_phrases):
        return "enough"
    return None


_BROKE_PHRASES = (
    "don't have money",
    "dont have money",
    "no money",
    "paas paise nahi",
    "paise nahi",
    "paisa nahi",
    "afford nahi",
    "can't pay",
    "cant pay",
    "broke",
    "free mein",
    "free me chat",
    "bina pay",
)


def looks_like_broke_objection(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(p in t for p in _BROKE_PHRASES)


def parse_pay_intent(messages: dict) -> bool:
    """Natural-language pay / unlock intent (not only exact PAY)."""
    pid, title = _extract_postback(messages)
    if pid == BTN_PAYWALL_PAY:
        return True
    body = title
    if not body and isinstance(messages, dict) and messages.get("type") == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip().lower()
    body = (body or "").strip().lower()
    if not body:
        return False
    if body == "pay":
        return True
    keywords = (
        "unlock",
        "payment",
        "pay now",
        "credits kharid",
        "credit kharid",
        "paise de",
        "payment kar",
    )
    if body in ("haan", "ha", "yes", "ok", "okay") and False:
        # bare haan alone is too ambiguous — only with pay context elsewhere
        return False
    return any(k in body for k in keywords) or body in (
        "unlock",
        "pay now",
        "payment",
    )


def parse_paywall_choice(messages: dict) -> str | None:
    """Return 'pay' | 'later' | None from paywall buttons."""
    pid, title = _extract_postback(messages)
    if pid == BTN_PAYWALL_LATER or title in ("baad mein", "baad me", "later"):
        return "later"
    if pid == BTN_PAYWALL_PAY:
        return "pay"
    if title in ("pay now", "pay") or title.startswith("see more") or (
        title.startswith("haan") and "₹" in title
    ):
        return "pay"
    return None


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


_YES_WORDS = frozenset({
    "haan", "ha", "yes", "ok", "okay", "theek hai", "theek", "sahi",
    "bilkul", "haan bhai", "haan ji", "ji", "yeah", "yep", "yup",
    "sure", "of course",
})
_NO_WORDS = frozenset({
    "nahi", "nhi", "no", "nahin", "nope", "nahi yaar", "nahi bhai",
    "no thanks", "nahi ji",
})

_RESTART_PHRASES = frozenset({
    "start over", "restart", "galat details", "dobara shuru",
    "meri details change", "reset", "naye details",
})

_LANG_SWITCH_EN = frozenset({
    "english mein bhejo", "switch to english", "english me",
    "english mein", "in english", "english please",
})
_LANG_SWITCH_HI = frozenset({
    "hindi mein", "hindi me", "hindi mein bhejo", "switch to hindi",
    "hinglish mein", "hinglish me", "in hindi",
})

ACK_RE_OFFER_TEXT_HI = (
    "Main samajh gayi 🙏 Neeche diye buttons mein se choose kijiye."
)
ACK_RE_OFFER_TEXT_EN = (
    "Got it 🙏 Please choose from the options below."
)


def _normalize_freetext(text: str) -> str:
    return (text or "").strip().lower().rstrip("!.?")


def parse_yes_no_freetext(text: str) -> str | None:
    """Return 'yes' | 'no' | None from casual free-text."""
    t = _normalize_freetext(text)
    if not t:
        return None
    if t in _YES_WORDS:
        return "yes"
    if t in _NO_WORDS:
        return "no"
    return None


def detect_restart_intent(text: str) -> bool:
    t = _normalize_freetext(text)
    return t in _RESTART_PHRASES


def detect_language_switch(text: str) -> str | None:
    """Return 'english' | 'hindi' | None."""
    t = _normalize_freetext(text)
    if t in _LANG_SWITCH_EN:
        return "english"
    if t in _LANG_SWITCH_HI:
        return "hindi"
    return None


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
    freetext = parse_yes_no_freetext(title)
    if freetext == "yes":
        return "yes"
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


def soft_past_range_from_chart(chart: dict | None) -> dict[str, Any] | None:
    """Engine-derived multi-year range for Beat 1 soft past opener.

    Years come only from relevant dasha rows. Never invent. Skip when the
    user is still young (<15) or no adult-relevant past/current window exists.
    Prefer a past window spanning at least 2 calendar years; clamp narration
    spans to ~7 years for the soft opener (ladder still does tighter asks).
    """
    meta = (chart or {}).get("meta") or {}
    try:
        current_age = int(meta.get("current_age"))
    except (TypeError, ValueError):
        return None
    if current_age < 15:
        return None

    candidates: list[dict[str, Any]] = []
    for p in relevant_dasha_slice(chart):
        start = str(p.get("start") or "")
        end = str(p.get("end") or "") or None
        if len(start) < 4:
            continue
        try:
            y0 = int(start[:4])
            y1 = int(end[:4]) if end and len(end) >= 4 else y0
        except ValueError:
            continue
        if y1 < y0:
            y0, y1 = y1, y0
        # Soft opener wants a RANGE, not a single year.
        if y1 <= y0:
            continue
        # Cap displayed span ~7 years (still a range, not an exact day).
        if (y1 - y0) > 7:
            y1 = y0 + 7
        age_start = p.get("lived_from_age")
        try:
            if age_start is not None and int(age_start) < 15:
                # Shift the spoken window to adult years inside the dasha.
                birth_year = meta.get("birth_year")
                if birth_year is None:
                    continue
                y0 = max(y0, int(birth_year) + 15)
                if y1 <= y0:
                    continue
        except (TypeError, ValueError):
            pass
        phase = p.get("phase")
        if phase not in ("past", "current"):
            continue
        candidates.append(
            {
                "year_start": y0,
                "year_end": y1,
                "planet_en": p.get("planet_en"),
                "planet_hi": p.get("planet_hi"),
                "phase": phase,
                "range_label_en": f"somewhere between {y0} and {y1}",
                "range_label_hi": f"{y0} se {y1} ke beech",
            }
        )

    if not candidates:
        return None
    # Prefer a completed past chapter; else current.
    past = [c for c in candidates if c.get("phase") == "past"]
    pick = past[-1] if past else candidates[-1]
    return pick


# Exact calendar-day patterns — forbidden in Beat 1 (ranges only).
_EXACT_DAY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bon\s+\d{1,2}(?:st|nd|rd|th)?\s+"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\s*,?\s*\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b"),
    re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4}\b",
        re.IGNORECASE,
    ),
)


def strip_exact_dates_from_beat1(text: str | None) -> tuple[str, bool]:
    """Remove exact-day date claims from Beat 1 copy. Returns (clean, violated)."""
    if not text:
        return "", False
    cleaned = text
    violated = False
    for pattern in _EXACT_DAY_PATTERNS:
        if pattern.search(cleaned):
            violated = True
            cleaned = pattern.sub("", cleaned)
    if not violated:
        return text, False
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip(" ,.-")
    return cleaned, True


def needs_conversational_name(profile: dict) -> bool:
    """True when we should ask 'Aapko kya bulaun?' before Beat 1."""
    if (profile.get("preferred_name") or "").strip():
        return False
    raw = (profile.get("username") or "").strip()
    if not raw or raw.lower() in ("dost", "user", "unknown", "whatsapp user"):
        return True
    if raw.isdigit():
        return True
    return False


def display_user_name(profile: dict) -> str:
    return (
        (profile.get("preferred_name") or "").strip()
        or (profile.get("username") or "").strip()
        or "dost"
    )
