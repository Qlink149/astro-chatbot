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
BEAT_AWAITING_PLACE_CONFIRM = "awaiting_place_confirm"
BEAT_1_AWAITING_CONFIRM = "beat1_awaiting_confirm"
BEAT_TEST_ME_YEAR = "test_me_year"  # user-driven falsifiable proof (Beat 1.5)
BEAT_2_AWAITING_ADVANCE = "beat2_awaiting_advance"  # undated fallback only
BEAT_2A_AWAITING_CONFIRM = "beat2a_awaiting_confirm"
BEAT_2B_AWAITING_CONFIRM = "beat2b_awaiting_confirm"
BEAT_2B_ALT_AWAITING = "beat2b_alt_awaiting"
BEAT_2C_AWAITING_DETAIL = "beat2c_awaiting_detail"
BEAT_2C_SECOND_WINDOW = "beat2c_second_window"  # answerable 2nd dated ask
BEAT_AWAITING_TOPIC = "awaiting_topic"
BEAT_AWAITING_ITEMS = "awaiting_items"  # "name your two or three" before Beat 4
BEAT_POST_FREE_DEEP = "post_free_deep"
BEAT_AWAITING_PWYW_AMOUNT = "awaiting_pwyw_amount"
BEAT_AWAITING_PWYW_CONFIRM = "awaiting_pwyw_confirm"
BEAT_RETURNING_MENU = "returning_menu"
BEAT_TRUST_RECOVERY = "trust_recovery"

ACTIVE_INTRO_BEATS = frozenset(
    {
        BEAT_AWAITING_LANGUAGE,
        BEAT_AWAITING_NAME,
        BEAT_AWAITING_PLACE_CONFIRM,
        BEAT_1_AWAITING_CONFIRM,
        BEAT_TEST_ME_YEAR,
        BEAT_2_AWAITING_ADVANCE,
        BEAT_2A_AWAITING_CONFIRM,
        BEAT_2B_AWAITING_CONFIRM,
        BEAT_2B_ALT_AWAITING,
        BEAT_2C_AWAITING_DETAIL,
        BEAT_2C_SECOND_WINDOW,
        BEAT_AWAITING_TOPIC,
        BEAT_AWAITING_ITEMS,
    }
)

MAX_LINES_PER_MESSAGE = 6
MAX_DATED_WINDOWS_PER_SESSION = 2
MAX_TEST_ME_CHALLENGES = 3

# Button postbacks
BTN_BEAT1_YES = "samara_beat1_yes"
BTN_BEAT1_SOFT = "samara_beat1_soft"  # legacy soft confirm (maps to mild trust)
BTN_BEAT1_NO = "samara_beat1_no"
BTN_PLACE_YES = "samara_place_yes"
BTN_PLACE_NO = "samara_place_no"
BTN_PLACE_OTHERS = "samara_place_others"  # clear-winner → open list
BTN_PLACE_CAND_0 = "samara_place_c0"
BTN_PLACE_CAND_1 = "samara_place_c1"
BTN_PLACE_CAND_2 = "samara_place_c2"
PLACE_CAND_POSTBACKS = (BTN_PLACE_CAND_0, BTN_PLACE_CAND_1, BTN_PLACE_CAND_2)
BTN_BEAT2_NEXT = "samara_beat2_next"
BTN_BEAT2A_YES = "samara_beat2a_yes"
BTN_BEAT2A_NO = "samara_beat2a_no"
# Forced-choice 2a: two textures, no approval option.
BTN_BEAT2A_OPT_A = "samara_beat2a_opt_a"
BTN_BEAT2A_OPT_B = "samara_beat2a_opt_b"
BTN_BEAT2A_NEITHER = "samara_beat2a_neither"
BTN_BEAT2B_YES = "samara_beat2b_yes"
BTN_BEAT2B_NO = "samara_beat2b_no"
BTN_TEST_ME_SKIP = "samara_test_me_skip"
BTN_ITEMS_SKIP = "samara_items_skip"
BTN_TOPIC_CAREER = "samara_topic_career"
BTN_TOPIC_LOVE = "samara_topic_love"
BTN_TOPIC_MONEY = "samara_topic_money"
BTN_TOPIC_FAMILY = "samara_topic_family"
BTN_TOPIC_DECISION = "samara_topic_decision"
BTN_RET_CONTINUE = "samara_ret_continue"
BTN_RET_NEW = "samara_ret_new"
BTN_RET_MUHURAT = "samara_ret_muhurat"
BTN_PAYWALL_PAY = "samara_paywall_pay"  # legacy — maps to PWYW amount ask
BTN_PAYWALL_LATER = "samara_paywall_later"
BTN_PWYW_CONFIRM_YES = "samara_pwyw_yes"
BTN_PWYW_CONFIRM_NO = "samara_pwyw_no"
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


CHECKIN_PHRASES_EN = (
    "Am I reading you right?",
    "Does that land?",
    "Am I on the right track?",
    "Does this feel familiar?",
)
CHECKIN_PHRASES_HI = (
    "Main sahi disha mein ja rahi hoon?",
    "Ye theek lag raha hai?",
    "Pehchaan aa rahi hai?",
    "Am I reading you right?",
)


def next_checkin_phrase(profile: dict, *, lang: str) -> str:
    """Rotate check-in wording; never repeat the previous phrase id."""
    pool = CHECKIN_PHRASES_EN if lang == "english" else CHECKIN_PHRASES_HI
    last = int(profile.get("last_checkin_phrase_id") or -1)
    nxt = (last + 1) % len(pool)
    if nxt == last and len(pool) > 1:
        nxt = (nxt + 1) % len(pool)
    profile["last_checkin_phrase_id"] = nxt
    return pool[nxt]


_TRAILING_CONFIRM_RE = re.compile(
    r"(?:\n|^)\s*(?:"
    r"does that (?:feel|sound|land|sit)(?:\s+\w+){0,4}\s*\?|"
    r"am i (?:reading|on)(?:\s+\w+){0,6}\s*\?|"
    r"does this feel(?:\s+\w+){0,4}\s*\?|"
    r"pehchaan aa rahi(?:\s+\w+){0,4}\s*\?|"
    r"ye theek lag(?:\s+\w+){0,4}\s*\?|"
    r"main sahi(?:\s+\w+){0,6}\s*\?"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_trailing_confirm_question(text: str | None) -> str:
    """Remove LLM-invented trailing check-ins; system appends one phrase."""
    raw = (text or "").rstrip()
    if not raw:
        return ""
    prev = None
    while prev != raw:
        prev = raw
        raw = _TRAILING_CONFIRM_RE.sub("", raw).rstrip()
    return raw


def beat1_confirm_buttons(body: str, *, lang: str, profile: dict | None = None) -> dict:
    checkin = ""
    if profile is not None:
        checkin = next_checkin_phrase(profile, lang=lang)
    text = strip_trailing_confirm_question(body)
    if checkin and checkin.lower() not in text.lower():
        text = f"{text}\n{checkin}"
    if lang == "english":
        yes_t, no_t = "Yes", "Not really"
    else:
        yes_t, no_t = "Haan", "Nahi bilkul"
    return _quickreply(
        text,
        "samara_beat1_confirm",
        [
            {"type": "text", "title": yes_t, "postbackText": BTN_BEAT1_YES},
            {"type": "text", "title": no_t, "postbackText": BTN_BEAT1_NO},
        ],
    )


def _place_button_title(display: str, *, max_len: int = 20) -> str:
    """WhatsApp quick-reply titles max 20 chars — avoid mid-word / trailing commas."""
    raw = " ".join(str(display or "").replace("\n", " ").split()).strip(" ,")
    if not raw:
        return "Place"
    if len(raw) <= max_len:
        return raw
    # Prefer "City, Admin" then truncate cleanly
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2:
        short = f"{parts[0]}, {parts[1]}"
        if len(short) <= max_len:
            return short
        if len(parts[0]) <= max_len:
            return parts[0][:max_len].rstrip(" ,")
    cut = raw[:max_len].rstrip(" ,")
    # Drop dangling partial word after last space if we chopped mid-token
    if " " in cut and not raw.startswith(cut):
        maybe = cut.rsplit(" ", 1)[0].rstrip(" ,")
        if len(maybe) >= 8:
            return maybe
    return cut or raw[:max_len]


def is_clear_place_winner(candidates: list[dict] | None) -> bool:
    """True when top match is clearly preferred over the rest (skip list)."""
    cands = [c for c in (candidates or []) if isinstance(c, dict) and c.get("display")]
    if len(cands) <= 1:
        return True
    s0 = float(cands[0].get("score") or 0)
    s1 = float(cands[1].get("score") or 0)
    gap = s0 - s1
    if gap >= 8.0:
        return True
    p0 = int(cands[0].get("population") or 0)
    p1 = int(cands[1].get("population") or 0)
    # Big city clearly dominates a village with a near-equal fuzzy score
    if gap >= 2.0 and p0 >= 100_000 and p0 >= max(5 * max(p1, 1), 200_000):
        return True
    return False


def _list_row_title(cand: dict, *, used: set[str]) -> str:
    """Unique ≤24-char list row title (Meta requires unique titles in a section)."""
    name = str(cand.get("name") or "").strip() or "Place"
    admin = str(cand.get("admin1") or "").strip()
    country = str(cand.get("country") or "").strip()
    candidates_titles = []
    if admin:
        candidates_titles.append(f"{name}, {admin}")
    candidates_titles.append(name)
    if country:
        candidates_titles.append(f"{name}, {country}")
    candidates_titles.append(str(cand.get("display") or name))
    for raw in candidates_titles:
        title = _place_button_title(raw, max_len=24)
        key = title.lower()
        if key and key not in used:
            used.add(key)
            return title
    # Last resort: append a digit
    for n in range(2, 10):
        title = _place_button_title(f"{name} ({n})", max_len=24)
        key = title.lower()
        if key not in used:
            used.add(key)
            return title
    used.add(name.lower())
    return _place_button_title(name, max_len=24)


def _list_row_description(cand: dict) -> str:
    parts = [
        str(cand.get("admin1") or "").strip(),
        str(cand.get("country") or "").strip(),
    ]
    desc = ", ".join(p for p in parts if p)
    if not desc:
        disp = str(cand.get("display") or "").strip()
        # Prefer the part after the city name
        if "," in disp:
            desc = disp.split(",", 1)[1].strip(" ,")
        else:
            desc = disp
    return _place_button_title(desc, max_len=72)


def place_confirm_numbered_text(candidates: list[dict]) -> str:
    """Plain-text fallback when list send fails — full names, reply 1/2/3."""
    cands = [c for c in (candidates or []) if isinstance(c, dict) and c.get("display")]
    lines = ["I found a few matches — reply with a number:\n"]
    for i, c in enumerate(cands[:3], start=1):
        lines.append(f"{i}. {c['display']}")
    lines.append("\nOr type your city again.")
    return "\n".join(lines)


def place_confirm_list(candidates: list[dict]) -> dict:
    """WhatsApp list message (dropdown) with full place names in descriptions."""
    cands = [c for c in (candidates or []) if isinstance(c, dict) and c.get("display")]
    show = cands[:3]
    used: set[str] = set()
    options: list[dict] = []
    for i, c in enumerate(show):
        options.append(
            {
                "type": "text",
                "title": _list_row_title(c, used=used),
                "description": _list_row_description(c),
                "postbackText": PLACE_CAND_POSTBACKS[i],
            }
        )
    none_title = "None of these"
    used.add(none_title.lower())
    options.append(
        {
            "type": "text",
            "title": none_title,
            "description": "Type your city again",
            "postbackText": BTN_PLACE_NO,
        }
    )
    body = "I found a few matches — which one is your place of birth?"
    return {
        "type": "list",
        "title": "Birth place",
        "body": body,
        "msgid": "samara_place_confirm",
        "button": "View places",
        "items": [{"title": "Places", "options": options}],
        "fallback_text": place_confirm_numbered_text(show),
    }


def place_confirm_winner_buttons(display: str) -> dict:
    """Clear-winner Yes / show-others (full name in message body)."""
    text = f"I think you mean {(display or '').strip()} — is that right?"
    return _quickreply(
        text,
        "samara_place_confirm",
        [
            {"type": "text", "title": "Yes", "postbackText": BTN_PLACE_YES},
            {
                "type": "text",
                "title": "No, show others",
                "postbackText": BTN_PLACE_OTHERS,
            },
        ],
        caption="Confirm",
    )


def place_confirm_single_buttons(display: str) -> dict:
    """Single geocode hit — Yes / retype."""
    text = f"{(display or '').strip()} — is that right?"
    return _quickreply(
        text,
        "samara_place_confirm",
        [
            {"type": "text", "title": "Yes", "postbackText": BTN_PLACE_YES},
            {"type": "text", "title": "No, try again", "postbackText": BTN_PLACE_NO},
        ],
    )


def place_confirm_ui(
    *,
    display: str,
    candidates: list[dict] | None = None,
    force_list: bool = False,
) -> dict:
    """Hybrid place picker: clear winner → Yes/No; else list (dropdown)."""
    cands = [c for c in (candidates or []) if isinstance(c, dict) and c.get("display")]
    if force_list and cands:
        return place_confirm_list(cands)
    if len(cands) >= 2:
        if not force_list and is_clear_place_winner(cands):
            return place_confirm_winner_buttons(cands[0].get("display") or display)
        return place_confirm_list(cands)
    return place_confirm_single_buttons(display or (cands[0]["display"] if cands else ""))


# Back-compat alias used by older call sites / tests
def place_confirm_buttons(
    *,
    display: str,
    candidates: list[dict] | None = None,
) -> dict:
    return place_confirm_ui(display=display, candidates=candidates)


def match_place_candidate_from_text(
    text: str, candidates: list[dict] | None
) -> int | None:
    """Map list title / truncated label / typed name back to a candidate index."""
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip(" ,").lower()
    if not raw:
        return None
    # Numbered fallback: "1" / "2" / "3"
    if raw in ("1", "2", "3"):
        idx = int(raw) - 1
        cands = [c for c in (candidates or []) if isinstance(c, dict)]
        if 0 <= idx < len(cands[:3]):
            return idx
        return None
    if len(raw) < 3:
        return None
    cands = [c for c in (candidates or []) if isinstance(c, dict) and c.get("display")]
    used: set[str] = set()
    # Prefer unique list-row / full-display matches over bare city name
    for i, c in enumerate(cands[:3]):
        disp = str(c.get("display") or "").strip()
        disp_l = disp.lower().strip(" ,")
        row_title = _list_row_title(c, used=used).lower()
        short = _place_button_title(disp).strip(" ,").lower()
        if raw in (disp_l, row_title, short):
            return i
        if disp_l.startswith(raw) or raw.startswith(disp_l):
            return i
        if row_title.startswith(raw) or raw.startswith(row_title):
            return i
    # Bare name only if unique among candidates
    name_hits = [
        i
        for i, c in enumerate(cands[:3])
        if str(c.get("name") or "").strip().lower() == raw
    ]
    if len(name_hits) == 1:
        return name_hits[0]
    return None


def parse_place_confirm(
    messages: dict, candidates: list[dict] | None = None
) -> tuple[str | None, int | None]:
    """Return (action, candidate_index).

    action: 'yes' | 'no' | 'others' | 'cand' | None
    """
    pid, title = _extract_postback(messages)
    title_l = (title or "").strip().lower()
    if pid == BTN_PLACE_YES or title_l in ("yes", "haan", "ha", "sahi hai"):
        return "yes", None
    if pid == BTN_PLACE_OTHERS or title_l in (
        "no, show others",
        "show others",
        "others",
    ):
        return "others", None
    if pid == BTN_PLACE_NO or title_l in (
        "no, try again",
        "no",
        "nahi",
        "none of these",
    ):
        return "no", None
    for i, btn in enumerate(PLACE_CAND_POSTBACKS):
        if pid == btn:
            return "cand", i
    # Gupshup sometimes delivers the button/list title as plain text (no postback id).
    body = ""
    if isinstance(messages, dict) and messages.get("type") == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip()
    probe = body or title
    idx = match_place_candidate_from_text(probe, candidates)
    if idx is not None:
        return "cand", idx
    if body:
        low = body.lower().strip()
        if low in ("yes", "haan", "ha", "sahi", "sahi hai", "y"):
            return "yes", None
        if low in ("no, show others", "show others", "others"):
            return "others", None
        if low in ("no", "nahi", "n", "nope", "no, try again", "none of these"):
            return "no", None
    return None, None


def beat2_next_button(body: str, *, lang: str) -> dict:
    title = "Tell me more" if lang == "english" else "Aage batao"
    return _quickreply(
        body,
        "samara_beat2_next",
        [{"type": "text", "title": title, "postbackText": BTN_BEAT2_NEXT}],
    )


def beat2a_confirm_buttons(body: str, *, lang: str, profile: dict | None = None) -> dict:
    checkin = ""
    if profile is not None:
        checkin = next_checkin_phrase(profile, lang=lang)
    text = strip_trailing_confirm_question(body)
    if checkin and checkin.lower() not in text.lower():
        text = f"{text}\n{checkin}"
    if lang == "english":
        yes_t, no_t = "Yes, that's right", "No, not really"
    else:
        yes_t, no_t = "Haan, sahi hai", "Nahi, aisa nahi"
    return _quickreply(
        text,
        "samara_beat2a_confirm",
        [
            {"type": "text", "title": yes_t[:20], "postbackText": BTN_BEAT2A_YES},
            {"type": "text", "title": no_t[:20], "postbackText": BTN_BEAT2A_NO},
        ],
    )


# Short forced-choice labels per engine theme (WhatsApp QR titles max 20 chars).
# These are TEXTURES, not events — same honesty contract as _THEME_TEXTURE_*.
_THEME_CHOICE_EN: dict[str, str] = {
    "responsibility": "Held it together",
    "zimmedari": "Held it together",
    "ambition": "Wanted more, fast",
    "letting go": "Let something go",
    "tyag": "Let something go",
    "growth": "Grew too fast",
    "vistar": "Grew too fast",
    "drive": "No finish line",
    "urja": "No finish line",
    "identity": "Didn't know me",
    "pehchaan": "Didn't know me",
    "emotions": "Felt it all",
    "bhavna": "Felt it all",
    "communication": "Overthought it",
    "soch-baat": "Overthought it",
    "harmony": "Kept the peace",
    "sukh": "Kept the peace",
    "change": "Ground shifted",
    "badlav": "Ground shifted",
}
_THEME_CHOICE_HI: dict[str, str] = {
    "responsibility": "Sab sambhala",
    "zimmedari": "Sab sambhala",
    "ambition": "Aur chahiye tha",
    "letting go": "Kuch chhoot gaya",
    "tyag": "Kuch chhoot gaya",
    "growth": "Tezi se bada hua",
    "vistar": "Tezi se bada hua",
    "drive": "Bina rukey",
    "urja": "Bina rukey",
    "identity": "Khud ko dhundha",
    "pehchaan": "Khud ko dhundha",
    "emotions": "Andar se zyada",
    "bhavna": "Andar se zyada",
    "communication": "Zyada socha",
    "soch-baat": "Zyada socha",
    "harmony": "Shanti banayi",
    "sukh": "Shanti banayi",
    "change": "Zameen hili",
    "badlav": "Zameen hili",
}


def theme_choice_label(theme: str | None, *, lang: str) -> str:
    key = (theme or "").strip().lower()
    if not key:
        return ""
    table = _THEME_CHOICE_EN if lang == "english" else _THEME_CHOICE_HI
    if key in table:
        return table[key]
    for k, v in table.items():
        if k in key or key in k:
            return v
    return ""


def beat2a_choice_options(
    quality_points: list[dict] | None, *, lang: str
) -> list[str]:
    """Two DISTINCT texture labels from engine themes. [] → fall back to Yes/No.

    Newest first — a 22-year-old recognises age 19-22 far better than 13-16.
    """
    labels: list[str] = []
    for point in reversed(list(quality_points or [])):
        if not isinstance(point, dict):
            continue
        theme = (
            point.get("theme_en") if lang == "english" else point.get("theme_hi")
        ) or point.get("theme_en")
        label = theme_choice_label(theme, lang=lang)
        if label and label not in labels:
            labels.append(label)
        if len(labels) == 2:
            break
    return labels if len(labels) == 2 else []


def beat2a_choice_buttons(body: str, *, lang: str, labels: list[str]) -> dict:
    """Forced choice — two textures, no 'am I right?'. Third option keeps a real No."""
    neither = "Neither, really" if lang == "english" else "Dono nahi"
    return _quickreply(
        strip_trailing_confirm_question(body),
        "samara_beat2a_choice",
        [
            {"type": "text", "title": labels[0][:20], "postbackText": BTN_BEAT2A_OPT_A},
            {"type": "text", "title": labels[1][:20], "postbackText": BTN_BEAT2A_OPT_B},
            {"type": "text", "title": neither[:20], "postbackText": BTN_BEAT2A_NEITHER},
        ],
        caption="Pick the closer one",
    )


def parse_beat2a_choice(
    messages: dict, labels: list[str] | None = None
) -> str | None:
    """Return 'a' | 'b' | 'neither' | None from the forced-choice QR."""
    pid, title = _extract_postback(messages)
    if pid == BTN_BEAT2A_OPT_A:
        return "a"
    if pid == BTN_BEAT2A_OPT_B:
        return "b"
    if pid == BTN_BEAT2A_NEITHER:
        return "neither"
    probe = (title or "").strip().lower()
    if not probe and isinstance(messages, dict) and messages.get("type") == "text":
        probe = ((messages.get("text") or {}).get("body") or "").strip().lower()
    if not probe:
        return None
    if probe in ("neither, really", "neither", "dono nahi", "none", "na"):
        return "neither"
    for i, lab in enumerate((labels or [])[:2]):
        if probe == str(lab).strip().lower()[:20]:
            return "a" if i == 0 else "b"
    if probe in ("1", "a"):
        return "a"
    if probe in ("2", "b"):
        return "b"
    return None


def test_me_ask_buttons(body: str, *, lang: str) -> dict:
    """Beat 1.5 — user names a year; typing is the point, Skip is the escape."""
    skip = "Skip this" if lang == "english" else "Rehne do"
    return _quickreply(
        body,
        "samara_test_me",
        [{"type": "text", "title": skip[:20], "postbackText": BTN_TEST_ME_SKIP}],
        caption="Type a year, or skip",
    )


def items_ask_buttons(body: str, *, lang: str) -> dict:
    """'Name your two or three' — answered inside the free demo (RULE 6)."""
    skip = "Skip" if lang == "english" else "Rehne do"
    return _quickreply(
        body,
        "samara_items_ask",
        [{"type": "text", "title": skip[:20], "postbackText": BTN_ITEMS_SKIP}],
        caption="Type them, or skip",
    )


_SKIP_WORDS = frozenset(
    {
        "skip",
        "skip this",
        "rehne do",
        "rehne don",
        "chhodo",
        "chodo",
        "pass",
        "next",
        "aage",
        "no",
        "nahi",
        "nope",
        "later",
        "baad mein",
        "kuch nahi",
        "nothing",
        "-",
    }
)


def is_skip_reply(messages: dict, *, postback: str) -> bool:
    pid, title = _extract_postback(messages)
    if pid == postback:
        return True
    probe = (title or "").strip().lower()
    if not probe and isinstance(messages, dict) and messages.get("type") == "text":
        probe = ((messages.get("text") or {}).get("body") or "").strip().lower()
    return probe.rstrip("!.") in _SKIP_WORDS


def parse_user_items(text: str, *, limit: int = 3) -> list[str]:
    """Split 'reels page, print idea and freelance' into the user's own words.

    Verbatim user strings only — never interpreted, never turned into claims.
    """
    raw = " ".join(str(text or "").replace("\n", ", ").split()).strip(" ,.")
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|;|/|\||\band\b|\baur\b|\+|\d\.)\s*", raw, flags=re.I)
    items: list[str] = []
    for part in parts:
        cleaned = part.strip(" ,.-").strip()
        if len(cleaned) < 2:
            continue
        if cleaned.lower() in items:
            continue
        items.append(cleaned[:60])
        if len(items) >= limit:
            break
    return items


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


# Chart theme keywords → lived texture (still not invented biography).
_THEME_TEXTURE_EN: dict[str, str] = {
    "responsibility": "carrying more than your share while keeping things steady",
    "ambition": "wanting a bigger lane than the one you were given",
    "letting go": "releasing something that had defined you for a while",
    "growth": "stretching into a version of yourself that felt slightly too big",
    "drive": "pushing hard with restless energy and little pause",
    "identity": "figuring out who you were when the old labels stopped fitting",
    "emotions": "feeling everything more sharply than you let on",
    "communication": "thinking two steps ahead in every conversation",
    "harmony": "trying to keep the peace even when it cost you",
    "change": "sensing the ground shifting under your feet",
    "zimmedari": "carrying more than your share while keeping things steady",
    "tyag": "releasing something that had defined you for a while",
    "vistar": "stretching into a version of yourself that felt slightly too big",
    "urja": "pushing hard with restless energy and little pause",
    "pehchaan": "figuring out who you were when the old labels stopped fitting",
    "bhavna": "feeling everything more sharply than you let on",
    "soch-baat": "thinking two steps ahead in every conversation",
    "sukh": "trying to keep the peace even when it cost you",
    "badlav": "sensing the ground shifting under your feet",
}
_THEME_TEXTURE_HI: dict[str, str] = {
    "responsibility": "apne hisse se zyada sambhalte hue sab theek rakhna",
    "zimmedari": "apne hisse se zyada sambhalte hue sab theek rakhna",
    "ambition": "diye hue lane se bada lane chahna",
    "letting go": "kisi cheez ko chhodna jo der se aapko define karti thi",
    "tyag": "kisi cheez ko chhodna jo der se aapko define karti thi",
    "growth": "khud ke thode bade version mein stretch karna",
    "vistar": "khud ke thode bade version mein stretch karna",
    "drive": "bina rukey zor lagaate rehna",
    "urja": "bina rukey zor lagaate rehna",
    "identity": "purane labels jab fit nahi hue, tab pehchaan dhundhna",
    "pehchaan": "purane labels jab fit nahi hue, tab pehchaan dhundhna",
    "emotions": "andar se zyada feel karna, bahar se kam dikhana",
    "bhavna": "andar se zyada feel karna, bahar se kam dikhana",
    "communication": "har baat mein do kadam aage sochna",
    "soch-baat": "har baat mein do kadam aage sochna",
    "harmony": "aman banaye rakhna chahe khud ko mehnga pade",
    "sukh": "aman banaye rakhna chahe khud ko mehnga pade",
    "change": "zameen ke hilne ka ehsaas",
    "badlav": "zameen ke hilne ka ehsaas",
}


def theme_texture_phrase(theme: str | None, *, lang: str) -> str:
    """Map engine theme keywords to short lived-texture phrases."""
    key = (theme or "").strip().lower()
    if not key:
        return ""
    table = _THEME_TEXTURE_EN if lang == "english" else _THEME_TEXTURE_HI
    if key in table:
        return table[key]
    # fuzzy: match english key inside hindi theme or vice versa
    for k, v in table.items():
        if k in key or key in k:
            return v
    return ""


def is_beat2c_skip_token(text: str | None) -> bool:
    """True when user skips sharing detail after bare yes."""
    raw = " ".join(str(text or "").replace("\n", " ").split()).strip().lower()
    if not raw:
        return True
    if len(raw) <= 2 and raw not in ("ha", "ji"):
        return True
    skip = {
        "ok",
        "okay",
        "k",
        "kk",
        "next",
        "aage",
        "aage badho",
        "skip",
        "pass",
        "continue",
        "move on",
        "nahi",
        "no",
        "nope",
        "baad mein",
        "later",
        "theek hai",
        "thik hai",
        "fine",
        "nothing",
        "kuch nahi",
    }
    return raw in skip


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
        theme_en = str(p.get("theme_en") or "")
        theme_hi = str(p.get("theme_hi") or "")
        out.append(
            {
                "age_start": a0i,
                "age_end": a1i,
                "theme_en": theme_en,
                "theme_hi": theme_hi,
                "texture_phrase_en": theme_texture_phrase(theme_en, lang="english"),
                "texture_phrase_hi": theme_texture_phrase(
                    theme_hi or theme_en, lang="hindi"
                ),
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


BTN_PWYW_AMOUNT_PREFIX = "samara_pwyw_amt_"


def pwyw_button_amounts(amount_inr: float | None = None) -> tuple[int, int]:
    """Two tappable PWYW amounts. Default (39, 99); tracks the configured min."""
    from kisna_chatbot.utils.pwyw_amount import min_payment_inr

    raw = float(amount_inr) if amount_inr and float(amount_inr) > 0 else min_payment_inr()
    low = max(1, int(round(raw)))
    high = 99 if low < 99 else int(round(low * 2.5))
    return low, high


def parse_pwyw_amount_button(messages: dict) -> float | None:
    """Amount from a tapped ₹ quick-reply. Typed amounts are parsed elsewhere."""
    pid, title = _extract_postback(messages)
    if pid.startswith(BTN_PWYW_AMOUNT_PREFIX):
        raw = pid[len(BTN_PWYW_AMOUNT_PREFIX) :]
        try:
            val = float(raw)
        except ValueError:
            return None
        return val if val > 0 else None
    # Gupshup sometimes delivers only the button title.
    m = re.fullmatch(r"\s*₹\s*(\d+(?:\.\d+)?)\s*", title or "")
    if m:
        try:
            val = float(m.group(1))
        except ValueError:
            return None
        return val if val > 0 else None
    return None


def paywall_buttons(*, lang: str, body: str, amount_inr: float | None = None) -> dict:
    """Door QR — tappable ₹ amounts + Later. Typing any other amount still works."""
    later_t = "Later" if lang == "english" else "Baad mein"
    low, high = pwyw_button_amounts(amount_inr)
    return _quickreply(
        body,
        "samara_paywall",
        [
            {
                "type": "text",
                "title": f"₹{low}",
                "postbackText": f"{BTN_PWYW_AMOUNT_PREFIX}{low}",
            },
            {
                "type": "text",
                "title": f"₹{high}",
                "postbackText": f"{BTN_PWYW_AMOUNT_PREFIX}{high}",
            },
            {"type": "text", "title": later_t, "postbackText": BTN_PAYWALL_LATER},
        ],
        caption="Choose one",
    )


def pwyw_confirm_buttons(*, lang: str, body: str) -> dict:
    if lang == "english":
        yes_t, no_t = "Yes, pay", "No, change amount"
    else:
        yes_t, no_t = "Haan, sahi hai", "Nahi, change"
    return _quickreply(
        body,
        "samara_pwyw_confirm",
        [
            {"type": "text", "title": yes_t[:20], "postbackText": BTN_PWYW_CONFIRM_YES},
            {"type": "text", "title": no_t[:20], "postbackText": BTN_PWYW_CONFIRM_NO},
        ],
        caption="Choose one",
    )


def parse_pwyw_confirm(messages: dict) -> str | None:
    """Return 'yes' | 'no' | None for large-amount PWYW confirm."""
    pid, title = _extract_postback(messages)
    if pid == BTN_PWYW_CONFIRM_YES:
        return "yes"
    if pid == BTN_PWYW_CONFIRM_NO:
        return "no"
    body = title
    if not body and isinstance(messages, dict) and messages.get("type") == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip().lower()
    body = (body or "").strip().lower()
    if body in ("yes", "haan", "ha", "sahi hai", "ok", "okay"):
        return "yes"
    if body in ("no", "nahi", "change", "nahi change"):
        return "no"
    return None


def want_more_buttons(*, lang: str, body: str) -> dict:
    """After free deep answer — invite without burning another LLM call."""
    if lang == "english":
        yes_t, no_t = "Want more", "Enough for now"
        default_body = "Want to go deeper on this, or pause here?"
    else:
        yes_t, no_t = "Aur jaanna hai", "Abhi bas"
        default_body = "Ispe aur depth chahiye, ya yahin rukna hai?"
    return _quickreply(
        (body or default_body).strip() or default_body,
        "samara_want_more",
        [
            {"type": "text", "title": yes_t[:20], "postbackText": BTN_WANT_MORE},
            {"type": "text", "title": no_t[:20], "postbackText": BTN_ENOUGH_FOR_NOW},
        ],
        caption="Choose one",
    )


def parse_want_more_choice(messages: dict) -> str | None:
    """Return 'more' | 'enough' | 'ack' | None from cliff QR or free-text."""
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
        "want more",
        "woh sunna",
        "filter batao",
        "aage batao",
        "go deeper",
        "deeper",
    )
    enough_phrases = (
        "abhi theek",
        "abhi bas",
        "i'm good",
        "im good",
        "theek hai abhi",
        "baad mein sochung",
        "enough for now",
        "enough",
        "pause",
    )
    ack_phrases = (
        "ok",
        "okay",
        "k",
        "kk",
        "thanks",
        "thank you",
        "thx",
        "ty",
        "cool",
        "nice",
        "great",
        "got it",
        "samajh gaya",
        "samajh gayi",
        "theek hai",
        "thik hai",
        "accha",
        "acha",
        "hmm",
        "haan",
        "ha",
        "👍",
        "🙏",
    )
    if any(p in body for p in more_phrases):
        return "more"
    if any(p in body for p in enough_phrases):
        return "enough"
    if body in ack_phrases or body.rstrip(".!") in ack_phrases:
        return "ack"
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
        lr = inter.get("list_reply") or {}
        raw_id = str(br.get("id") or lr.get("id") or "")
        title = str(br.get("title") or lr.get("title") or "").strip().lower()
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
    # Some Gupshup payloads use type=list_reply at top level
    if mtype == "list_reply":
        lr = messages.get("list_reply") or messages
        return (
            str(lr.get("id") or lr.get("postbackText") or "").strip(),
            str(lr.get("title") or "").strip().lower(),
        )
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
    """Return 'yes' | 'soft' | 'no' | None."""
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
    if pid == BTN_BEAT1_NO or title in (
        "not really",
        "nahi bilkul",
        "nahi",
        "no",
        "nope",
    ):
        return "no"
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
    if freetext == "no":
        return "no"
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

# Month-level precision — also forbidden in Beat 1 (multi-year range only).
_BEAT1_MONTH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b"
        r"(?:\s*[–-]\s*"
        r"(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec))?"
        r"\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{4}-\d{2}\b"),
)


def strip_exact_dates_from_beat1(text: str | None) -> tuple[str, bool]:
    """Remove day- and month-level date claims from Beat 1. Returns (clean, violated)."""
    if not text:
        return "", False
    cleaned = text
    violated = False
    for pattern in _EXACT_DAY_PATTERNS + _BEAT1_MONTH_PATTERNS:
        if pattern.search(cleaned):
            violated = True
            cleaned = pattern.sub("", cleaned)
    if not violated:
        return text, False
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip(" ,.-")
    return cleaned, True


def dates_in_upcoming_periods(chart: dict | None) -> set[str]:
    """ISO start/end dates from upcoming_periods — for guards/tests."""
    out: set[str] = set()
    for p in (chart or {}).get("upcoming_periods") or []:
        if not isinstance(p, dict):
            continue
        for key in ("start", "end"):
            val = str(p.get(key) or "")
            if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                out.add(val)
    return out


def extract_iso_dates_from_text(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))


def extract_spoken_day_dates(text: str | None) -> list[str]:
    """Rough spoken day-level dates (for future-timing tests)."""
    if not text:
        return []
    pat = re.compile(
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+"
        r"(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+\d{4})\b",
        re.IGNORECASE,
    )
    return pat.findall(text)


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
