"""Gate / trust / solicited-reply helpers for Samara (no chart math)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

GateKind = Literal["door", "none"]


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


def chart_door_windows(profile: dict, *, lang: str) -> str:
    """Template fill from engine turning_points — no LLM, no invented dates."""
    chart = profile.get("chart_json") or {}
    tps = list(chart.get("turning_points") or [])
    labels: list[str] = []
    for tp in tps[:3]:
        if not isinstance(tp, dict):
            continue
        if lang == "english":
            lab = tp.get("window_label_en") or tp.get("window_label_hi")
        else:
            lab = tp.get("window_label_hi") or tp.get("window_label_en")
        if lab:
            labels.append(str(lab))
    if len(labels) >= 2:
        return f"{labels[0]} and {labels[1]}" if lang == "english" else f"{labels[0]} aur {labels[1]}"
    if labels:
        return labels[0]
    # Fallback: current mahadasha name only (engine field)
    dasha = (chart.get("dasha") or {}).get("current_mahadasha") or {}
    name = dasha.get("planet_en") or dasha.get("planet") or ""
    if name:
        return (
            f"your current {name} period"
            if lang == "english"
            else f"aapki current {name} dasha"
        )
    return "the next clear windows in your chart" if lang == "english" else "chart ke agle clear windows"


def door_gate_body(profile: dict, *, amount_inr: float) -> str:
    """Door framing — topic-aware open loop + PWYW; never meter language."""
    from kisna_chatbot.utils.pwyw_amount import (
        credits_for_amount,
        format_inr,
        rupees_per_credit,
    )
    from kisna_chatbot.utils.samara_beats import TOPIC_LABELS, TOPIC_LABELS_EN

    lang = "english" if (profile.get("user_language") or "") == "english" else "hindi"
    windows = chart_door_windows(profile, lang=lang)
    amt = format_inr(amount_inr)
    rate = format_inr(rupees_per_credit())
    floor_credits = credits_for_amount(amount_inr)
    topic_key = str(profile.get("chosen_topic") or "").strip().lower()
    if lang == "english":
        topic_label = TOPIC_LABELS_EN.get(topic_key) or TOPIC_LABELS.get(topic_key) or "this"
    else:
        topic_label = TOPIC_LABELS.get(topic_key) or topic_key or "is topic"

    # Rotate cliff openers (deterministic from topic + windows — no random hash).
    idx = sum(ord(c) for c in f"{topic_key}|{windows}") % 4

    if lang == "english":
        cliffs = (
            f"On {topic_label}, your chart still has clearer windows around {windows} — "
            f"which month to lean into, and what to hold back on.",
            f"There's more on {topic_label} I haven't opened yet. "
            f"Your next sharp windows sit around {windows}.",
            f"If we go deeper on {topic_label}, I'd map the timing around {windows} — "
            f"what to push, what to protect.",
            f"The free read on {topic_label} was the door. "
            f"The fuller timing picture around {windows} is what we unlock next.",
        )
        cliff = cliffs[idx]
        pwyw = (
            f"Pay what you want — minimum ₹{amt} "
            f"(about ₹{rate} per deep answer; at least {floor_credits} answers). "
            f"Type an amount like {amt} when you're ready, or Later — both are fine."
        )
        return f"{cliff}\n\n{pwyw}"

    cliffs_hi = (
        f"{topic_label} pe chart mein clear windows {windows} ke around hain — "
        f"kaun sa mahina lean karna hai, kis se bachna hai.",
        f"{topic_label} pe aur depth baaki hai. Agla sharp window {windows} ke around hai.",
        f"Agar {topic_label} pe deeper jayein, main {windows} ke timing pe map karungi — "
        f"kya push karna hai, kya protect.",
        f"Free read sirf shuruaat thi. {windows} ke around poori timing tasveer next step hai.",
    )
    cliff = cliffs_hi[idx]
    pwyw = (
        f"Jo dena chaho — minimum ₹{amt} "
        f"(lagbhag ₹{rate} per deep jawab; kam se kam {floor_credits} sawaal). "
        f"Amount type karo jaise {amt}, ya Baad mein — dono theek hain."
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
