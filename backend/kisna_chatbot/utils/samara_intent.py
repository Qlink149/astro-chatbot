"""Samara inbound intent classification (Haiku + heuristics).

When unsure between followup and new_deep_question, prefer followup (free).
Distress is handled earlier in the agent and must never be overridden here.
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Literal

SamaraIntent = Literal[
    "distress",
    "confirmation",
    "denial",
    "followup",
    "new_deep_question",
    "clarification",
    "correction",
    "meta",
    "payment_intent",
    "smalltalk",
    "offtopic",
    "test_me",
]

FREE_INTENTS = frozenset(
    {
        "followup",
        "clarification",
        "meta",
        "confirmation",
        "denial",
        "correction",
        "smalltalk",
        "offtopic",
        "test_me",
    }
)

VALID_INTENTS = frozenset(
    {
        "distress",
        "confirmation",
        "denial",
        "followup",
        "new_deep_question",
        "clarification",
        "correction",
        "meta",
        "payment_intent",
        "smalltalk",
        "offtopic",
        "test_me",
    }
)

_INTENT_SYSTEM = """You classify WhatsApp messages to Samara (Vedic astrology companion).
Return ONLY a JSON object: {"intent": "<one>"}.
intents: confirmation, denial, followup, new_deep_question, clarification,
correction, meta, payment_intent, smalltalk, offtopic, test_me.
Rules:
- Short referents after a claim (aur?, why, kab, that, it, kitna) → followup
- New life-area deep question → new_deep_question
- When unsure between followup and new_deep_question → followup
- how does this work / who are you / pricing / is this real → meta
- birth time wrong / chart wrong → correction
- pay / unlock / credits → payment_intent
- greetings → smalltalk
- challenge / test me / ask another year → test_me
Never return distress (handled elsewhere).
"""


def heuristic_intent(text: str, *, focus: dict | None = None) -> SamaraIntent | None:
    """Fast deterministic classify for clear cases. None → use LLM."""
    t = (text or "").strip().lower()
    if not t:
        return None

    if re.search(
        r"\b(kill myself|suicide|self[- ]?harm|end my life|marna chahta|"
        r"jeena nahi)\b",
        t,
    ):
        return "distress"

    if re.search(
        r"(birth time (is )?wrong|galat time|time galat|wrong (birth )?time|"
        r"chart (is )?wrong|dob wrong|date of birth wrong|recompute|dob galat)",
        t,
    ):
        return "correction"

    if re.search(
        r"(how does (this|it) work|kaise kaam|who are you|tum kaun|"
        r"is this real|sach hai|pricing|kitna (paisa|lagta)|how much (do i|to) pay|"
        r"kya ye real)",
        t,
    ):
        return "meta"

    if re.search(
        r"\b(pay|unlock|payment|credits? kharid|paise de)\b",
        t,
    ) or t in ("pay", "unlock"):
        return "payment_intent"

    if re.search(
        r"(test me|test karo|koi aur saal|another year|challenge|"
        r"pooch(iye|o) .*saal)",
        t,
    ):
        return "test_me"

    if re.fullmatch(
        r"(hi|hello|hey|namaste|namaskar|hola|yo|sup|good morning|"
        r"good evening|wassup)+[!?. ]*",
        t,
    ):
        return "smalltalk"

    if t in (
        "yes",
        "haan",
        "ha",
        "haan ji",
        "ji",
        "sahi",
        "sahi hai",
        "exactly",
        "true",
        "bilkul",
    ):
        return "confirmation"

    if t in (
        "no",
        "nahi",
        "nahin",
        "not really",
        "nope",
        "galat",
        "wrong",
    ):
        return "denial"

    # Short follow-up cues — especially when focus has a claim
    if re.fullmatch(
        r"(aur\??|why\??|kab\??|kitna\??|that\??|it\??|uske baad\??|"
        r"phir\??|and then\??|how\??|kyun\??|kyu\??|kya matlab\??)",
        t,
    ):
        return "followup"
    if len(t) <= 24 and re.search(
        r"^(aur|why|kab|kitna|kyun|kyu|that|and then|uske baad)\b",
        t,
    ):
        return "followup"

    if re.search(r"(samajh nahi|didn't understand|confused|kya bola|matlab\?)", t):
        return "clarification"

    if re.search(
        r"(weather|cricket|football|recipe|stock market tip)\b",
        t,
    ):
        return "offtopic"

    # Explicit new deep question signals
    if len(t) > 40 and re.search(
        r"\b(career|job|shaadi|marriage|love|money|paisa|family|"
        r"decision|should i|kya karun|kab milegi|promotion)\b",
        t,
    ):
        # Still err toward followup if focus claim exists and text is short-ish
        if focus and focus.get("last_claim") and len(t) < 60:
            return "followup"
        return "new_deep_question"

    return None


async def classify_intent(
    text: str,
    *,
    focus: dict | None = None,
    recent_turns: str = "",
    classify_fn: Callable[[str, str], Awaitable[str]] | None = None,
) -> SamaraIntent:
    """Classify intent; default followup when unsure."""
    heur = heuristic_intent(text, focus=focus)
    if heur is not None:
        return heur

    if classify_fn is None:
        return "followup"

    user_blob = json.dumps(
        {
            "inbound": text,
            "focus": focus or {},
            "recent_turns": (recent_turns or "")[:800],
        },
        ensure_ascii=False,
    )
    try:
        raw = await classify_fn(_INTENT_SYSTEM, user_blob)
        data = json.loads(raw.strip().strip("`"))
        if isinstance(data, dict):
            intent = str(data.get("intent") or "").strip().lower()
            if intent in VALID_INTENTS and intent != "distress":
                return intent  # type: ignore[return-value]
    except Exception:
        pass
    return "followup"


def is_free_intent(intent: SamaraIntent) -> bool:
    return intent in FREE_INTENTS
