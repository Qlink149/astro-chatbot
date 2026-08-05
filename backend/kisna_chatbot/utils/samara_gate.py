"""Gate / trust / solicited-reply helpers for Samara (no chart math)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

GateKind = Literal["door", "none"]
DoorKind = Literal["near", "far", "none"]

# A dated window is only worth selling if the user can plan around it.
NEAR_WINDOW_MONTHS = 12


@dataclass(frozen=True)
class GateAction:
    kind: GateKind
    body: str | None = None


_QUESTION_CUE = re.compile(
    r"(\?|kya |hai kya|batao|bataye|batayein|tell me|are you |do you |"
    r"working or|studying|what about|which )",
    re.IGNORECASE,
)


def outbound_asks_user_question(text: str) -> bool:
    """True if outbound copy invites a free-text answer from the user."""
    t = (text or "").strip()
    if not t:
        return False
    if "?" in t:
        return True
    # Trailing invite without ? (Hinglish)
    lower = t.lower()
    return bool(
        re.search(
            r"(batayein|batao|bataiye|tell me|what matters|sabse zaroori)\s*\??\s*$",
            lower,
        )
    )


def mark_bot_asked_question(profile: dict, text: str, *, context: str | None = None) -> None:
    if outbound_asks_user_question(text):
        profile["bot_asked_question"] = True
        profile["bot_question_context"] = (context or text)[-400:]
    else:
        # Complete statements clear any stale invite
        pass


def clear_bot_asked_question(profile: dict) -> None:
    profile["bot_asked_question"] = False
    profile["bot_question_context"] = None


def bump_trust(profile: dict, delta: int) -> int:
    score = int(profile.get("trust_score") or 0) + int(delta)
    profile["trust_score"] = score
    profile["trust_scored"] = True
    return score


def gate_suppressed(profile: dict) -> bool:
    return bool(profile.get("gate_suppressed_session"))


def needs_trust_recovery(profile: dict) -> bool:
    if gate_suppressed(profile):
        return False
    if int(profile.get("trust_recovery_attempts") or 0) >= 2:
        return False
    # Only after intro signals existed; default 0 before Beat1 must not trap everyone.
    if not profile.get("trust_scored"):
        return False
    return int(profile.get("trust_score") or 0) <= 0


_MONTHS_EN = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _format_iso_date(iso: str) -> str:
    """'2028-10-10' → '10 October 2028'. Engine dates only — never synthesised."""
    m = _ISO_DATE.match(str(iso or "").strip())
    if not m:
        return ""
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 1 <= month <= 12:
        return ""
    return f"{day} {_MONTHS_EN[month]} {year}"


def _months_away(iso: str, *, today: date | None = None) -> int | None:
    m = _ISO_DATE.match(str(iso or "").strip())
    if not m:
        return None
    today = today or date.today()
    year, month = int(m.group(1)), int(m.group(2))
    return (year - today.year) * 12 + (month - today.month)


def current_mahadasha_name(chart: dict | None, *, lang: str) -> str:
    """Current mahadasha planet from engine rows only."""
    chart = chart or {}
    for row in chart.get("dasha_timeline") or []:
        if not isinstance(row, dict) or row.get("phase") != "current":
            continue
        name = (
            row.get("planet_en")
            if lang == "english"
            else (row.get("planet_hi") or row.get("planet_en"))
        )
        if name:
            return str(name)
    # Legacy shape kept for older profiles
    dasha = (chart.get("dasha") or {}).get("current_mahadasha") or {}
    return str(dasha.get("planet_en") or dasha.get("planet") or "")


@dataclass(frozen=True)
class DoorWindow:
    """What the door is allowed to point at. FUTURE rows only."""

    kind: DoorKind
    label: str = ""          # "10 October 2028" — exact engine date
    year: str = ""           # "2028" — coarse form for the far branch
    months_away: int | None = None
    maha: str = ""


def next_upcoming_window(
    profile: dict, *, lang: str, today: date | None = None
) -> DoorWindow:
    """First engine `upcoming_periods` row, with distance so copy can branch.

    NEVER reads `turning_points` — those are past by construction
    (`is_relevant` requires `age_end <= current_age`) and must not be sold
    as windows to lean into.
    """
    chart = profile.get("chart_json") or {}
    maha = current_mahadasha_name(chart, lang=lang)
    for row in chart.get("upcoming_periods") or []:
        if not isinstance(row, dict):
            continue
        start = str(row.get("start") or "")
        label = _format_iso_date(start)
        if not label:
            continue
        away = _months_away(start, today=today)
        if away is None:
            continue
        kind: DoorKind = "near" if away <= NEAR_WINDOW_MONTHS else "far"
        return DoorWindow(
            kind=kind,
            label=label,
            year=start[:4],
            months_away=away,
            maha=maha,
        )
    return DoorWindow(kind="none", maha=maha)


def chart_door_windows(profile: dict, *, lang: str) -> str:
    """Back-compat label helper — future windows only, never past ones."""
    win = next_upcoming_window(profile, lang=lang)
    if win.label:
        return win.label
    if win.maha:
        return (
            f"your current {win.maha} chapter"
            if lang == "english"
            else f"aapki current {win.maha} dasha"
        )
    return "your chart" if lang == "english" else "aapke chart"


def _chapter_phrase(maha: str, *, lang: str) -> str:
    if maha:
        return f"this {maha} chapter" if lang == "english" else f"is {maha} chapter"
    return "this chapter" if lang == "english" else "is chapter"


def _items_phrase(items: list[str], *, lang: str) -> str:
    """The user's own words, verbatim. Personalisation must not drop at the ask."""
    clean = [str(i).strip() for i in (items or []) if str(i).strip()][:3]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    joiner = " and " if lang == "english" else " aur "
    return ", ".join(clean[:-1]) + joiner + clean[-1]


def door_gate_body(
    profile: dict, *, amount_inr: float, today: date | None = None
) -> str:
    """Door framing — templated from engine `upcoming_periods`, never LLM-authored.

    Three branches:
      near (<=12mo) — name the exact engine date and sell the timing map.
      far  (>12mo)  — say so honestly, then sell direction instead of timing.
      none          — no dated rows (usually no birth time): sell direction only.
    No recharge-pack maths in the pitch.
    """
    from kisna_chatbot.utils.pwyw_amount import format_inr
    from kisna_chatbot.utils.samara_beats import TOPIC_LABELS, TOPIC_LABELS_EN

    lang = "english" if (profile.get("user_language") or "") == "english" else "hindi"
    amt = format_inr(amount_inr)
    topic_key = str(profile.get("chosen_topic") or "").strip().lower()
    if lang == "english":
        topic_label = (
            TOPIC_LABELS_EN.get(topic_key) or TOPIC_LABELS.get(topic_key) or "this"
        )
    else:
        topic_label = TOPIC_LABELS.get(topic_key) or topic_key or "is topic"

    win = next_upcoming_window(profile, lang=lang, today=today)
    chapter = _chapter_phrase(win.maha, lang=lang)
    # Two deterministic variants per branch — same facts, different phrasing.
    idx = sum(ord(c) for c in f"{topic_key}|{win.label}|{win.kind}") % 2

    # When the free answer already used their named items, it ALSO already gave
    # the "which one" verdict. Reselling that reads as a shopkeeper charging for
    # what he just handed over — so pitch the cost side, which stays unopened.
    items = _items_phrase(list(profile.get("user_items") or []), lang=lang)
    if items:
        if lang == "english":
            cliffs_items = (
                f"You named {items}. I've said which one {chapter} feeds — "
                f"what's still closed is the cost side: what carrying the "
                f"others does to the one you keep, and what this chapter asks "
                f"of you before you commit to it.",
                f"I've given you the pick out of {items}. What I haven't opened "
                f"is the price of it — what {chapter} takes from you for that "
                f"choice, and what to stop paying for while you make it.",
            )
            cliff = cliffs_items[idx]
            pwyw = (
                f"Pay what feels right — ₹{amt} minimum. "
                f"Tap below, or type any amount you like."
            )
            return f"{cliff}\n\n{pwyw}"
        cliffs_items_hi = (
            f"Aapne {items} bataye the. Inmein se {chapter} kis ko feed karta "
            f"hai, woh maine keh diya — jo abhi band hai woh cost hai: baaki "
            f"cheezein uthaye rehne se jo aap rakhna chahte ho uspe kya asar "
            f"padta hai, aur commit karne se pehle chapter aapse kya maangta hai.",
            f"{items} mein se pick maine de diya. Jo nahi khola woh uski keemat "
            f"hai — us choice ke badle {chapter} aapse kya leta hai, aur tab tak "
            f"kis pe kharch band karna hai.",
        )
        cliff = cliffs_items_hi[idx]
        pwyw = (
            f"Jo theek lage — minimum ₹{amt}. "
            f"Neeche tap karo, ya koi bhi amount type kar do."
        )
        return f"{cliff}\n\n{pwyw}"

    if lang == "english":
        if win.kind == "near":
            cliffs = (
                f"On {topic_label}, your next real window is {win.label}. "
                f"What I'd map next: which month to move in, and the one to sit "
                f"still through.",
                f"Your next dated shift on {topic_label} is {win.label}. "
                f"The part I haven't opened is what to push before it, and what "
                f"to stop paying for.",
            )
        elif win.kind == "far":
            cliffs = (
                f"Straight with you: your next dated shift is {win.year}. Too far "
                f"to plan around. So the {topic_label} read worth paying for isn't "
                f"'when' — it's which of the things you're carrying {chapter} will "
                f"actually pay for, and which one to drop this year.",
                f"I won't pretend there's a date coming. The next one in your chart "
                f"is {win.year}, which is no use to you now. What is useful: which "
                f"single thing {chapter} rewards on {topic_label}, and what to stop "
                f"spending yourself on.",
            )
        else:
            cliffs = (
                f"Your chart doesn't hand me dated windows here. What it does give "
                f"is direction — which way {chapter} pays on {topic_label}, and "
                f"what to stop spending yourself on.",
                f"No dated shift to point at, and I won't invent one. The read "
                f"worth paying for is which side of {topic_label} {chapter} "
                f"rewards, and what to put down.",
            )
        cliff = cliffs[idx]
        pwyw = (
            f"Pay what feels right — ₹{amt} minimum. "
            f"Tap below, or type any amount you like."
        )
        return f"{cliff}\n\n{pwyw}"

    if win.kind == "near":
        cliffs_hi = (
            f"{topic_label} pe aapka agla asli window {win.label} hai. "
            f"Aage main yahi map karungi: kis mahine move karna hai, aur kis mein "
            f"ruk jaana behtar hai.",
            f"{topic_label} pe agla dated shift {win.label} hai. Jo abhi khola "
            f"nahi — usse pehle kya push karna hai, aur kis pe kharch band karna hai.",
        )
    elif win.kind == "far":
        cliffs_hi = (
            f"Seedhi baat: aapka agla dated shift {win.year} mein hai. Itni door ki "
            f"planning nahi hoti. Toh {topic_label} ka jo read paise ke laayak hai "
            f"woh 'kab' nahi hai — woh ye hai ki jo cheezein aap abhi uthaye ghoom "
            f"rahe ho, unmein se {chapter} kis ko pay karega, aur kis ko is saal "
            f"chhod dena behtar hai.",
            f"Main jhoothi date nahi dungi. Chart mein agla shift {win.year} hai — "
            f"abhi ke liye bekaar. Kaam ki baat ye hai: {topic_label} pe {chapter} "
            f"kis ek cheez ko reward karta hai, aur kis pe khud ko kharch karna "
            f"band karna hai.",
        )
    else:
        cliffs_hi = (
            f"Yahan chart mujhe dated window nahi de raha. Jo de raha hai woh "
            f"direction hai — {topic_label} pe {chapter} kis taraf pay karta hai, "
            f"aur kis pe rukna hai.",
            f"Koi dated shift nahi hai, aur main banaungi bhi nahi. Paise ke laayak "
            f"read ye hai: {topic_label} ke kis side ko {chapter} reward karta hai, "
            f"aur kya neeche rakh dena hai.",
        )
    cliff = cliffs_hi[idx]
    pwyw = (
        f"Jo theek lage — minimum ₹{amt}. "
        f"Neeche tap karo, ya koi bhi amount type kar do."
    )
    return f"{cliff}\n\n{pwyw}"


def decide_gate_action(
    profile: dict,
    *,
    amount_inr: float,
    force: bool = False,
) -> GateAction:
    """At most one gate action. Never gate solicited / recovery / suppressed."""
    if profile.get("bot_asked_question"):
        return GateAction("none")
    if profile.get("in_trust_recovery"):
        return GateAction("none")
    if gate_suppressed(profile):
        return GateAction("none")
    if needs_trust_recovery(profile) and not force:
        return GateAction("none")
    free_used = bool(profile.get("free_deep_answer_used"))
    from kisna_chatbot.payments.credit_ledger import get_credit_balance

    if not free_used:
        return GateAction("none")
    if get_credit_balance(profile) > 0:
        return GateAction("none")
    return GateAction("door", body=door_gate_body(profile, amount_inr=amount_inr))


def count_gate_messages(bot_response: list[Any]) -> int:
    """How many paywall-style QRs are in one outbound list."""
    n = 0
    for item in bot_response or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "quickreply":
            continue
        msgid = str(item.get("msgid") or "")
        if msgid in ("samara_paywall", "samara_want_more"):
            # want_more is cliff invite, not gate — only count paywall
            if msgid == "samara_paywall":
                n += 1
            continue
        opts = item.get("options") or []
        titles = " ".join(str(o.get("title") or "") for o in opts).lower()
        if "pay now" in titles or "₹" in titles or "dekhte hain" in titles:
            n += 1
    return n
