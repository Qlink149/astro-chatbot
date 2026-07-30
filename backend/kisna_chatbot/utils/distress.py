"""Crisis / distress detection for Samara.

Runs BEFORE astrology. Never predicts outcomes, never paywalls, never debits.

Primary path: Haiku LLM classifier on every inbound text message.
Fail-safe only: if the classifier errors or returns unparseable output, a
minimal self-harm keyword screen still routes to crisis (never to astrology).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

DISTRESS_CLASSIFIER_PROMPT = """
You classify whether a WhatsApp message to an astrology guide (Samara) shows
acute distress that must NOT receive an astrology reading or prediction.

Return ONLY JSON (no markdown): {"distress": true|false, "self_harm": true|false}

Set distress=true when the message indicates ANY of:
- hopelessness, severe depression, or "nothing good will happen / I'm exhausted"
- self-harm or suicide ideation
- medical emergency or serious illness fear (e.g. will mother survive / recover)
- abuse or domestic violence
- acute crisis framed as desperation: marriage collapsing ("will my marriage
  survive?", "should I leave my spouse?"), business/financial ruin desperation

Set self_harm=true ONLY if there is ideation or intent about harming themselves
or wanting to die / end their life.

Set distress=false for ordinary astrology questions (career dasha, marriage
timing curiosity, money outlook) WITHOUT desperation or crisis framing.

Never invent chart facts. Never answer the user — only classify.
"""

# Fail-safe only when LLM unavailable — never the primary path
_SELF_HARM_FAILSAFE = (
    r"\bsuicide\b",
    r"\bkill myself\b",
    r"\bend my life\b",
    r"\bwant to die\b",
    r"\bi want to die\b",
    r"\bself[- ]?harm\b",
    r"\batmahatya\b",
    r"\bmarna chaht[ai]\b",
    r"\bjaan de dun\b",
)

ClassifyFn = Callable[[str, str], Awaitable[str]]


@dataclass(frozen=True)
class DistressResult:
    distress: bool
    self_harm: bool
    source: str  # "llm" | "failsafe" | "none"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def self_harm_failsafe(text: str) -> bool:
    """Last-resort screen if LLM fails — self-harm phrases only."""
    t = _norm(text)
    if not t:
        return False
    return any(re.search(p, t, re.IGNORECASE) for p in _SELF_HARM_FAILSAFE)


def parse_classifier_json(raw: str) -> Optional[DistressResult]:
    text = (raw or "").strip()
    if "```" in text:
        text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        data: Any = json.loads(text)
        if not isinstance(data, dict):
            return None
        distress = bool(data.get("distress"))
        self_harm = bool(data.get("self_harm")) and distress
        return DistressResult(distress, self_harm, "llm")
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def crisis_response_text(*, lang: str, self_harm: bool) -> str:
    """Canned warmth — no astrology, no prediction, no paywall."""
    if lang == "english":
        base = (
            "I'm really glad you told me this. What you're carrying sounds heavy, "
            "and you don't have to hold it alone.\n\n"
            "I'm not going to read your chart on this — you deserve a real human "
            "in your corner right now, not an astrology answer."
        )
        if self_harm:
            base += (
                "\n\nIf you might hurt yourself, please reach someone who can help "
                "today: Tele-MANAS 14416 or KIRAN 1800-599-0019. "
                "You can also talk to someone you trust."
            )
        else:
            base += (
                "\n\nIf you can, speak with someone you trust, or a counsellor. "
                "You matter more than any chart."
            )
        base += (
            "\n\nWhen you feel ready — only if you want — we can come back to "
            "your reading later. No pressure."
        )
        return base

    base = (
        "Aapne yeh share kiya, yeh bahut badi baat hai. Jo aap mehsoos kar rahe ho, "
        "woh bhaari lag sakta hai — aap akele nahi ho.\n\n"
        "Is par main abhi kundli nahi padhungi. Aapko ab kisi asli insan ki "
        "madad chahiye, prediction ki nahi."
    )
    if self_harm:
        base += (
            "\n\nAgar aap khud ko nuksaan pahunchane ke baare mein soch rahe ho, "
            "to aaj hi madad lo: Tele-MANAS 14416 ya KIRAN 1800-599-0019. "
            "Kisi trusted dost ya parivar se bhi baat kar sakte ho."
        )
    else:
        base += (
            "\n\nAgar ho sake, kisi trusted dost, parivar, ya counsellor se baat "
            "kariye. Aap kisi bhi chart se zyada important ho."
        )
    base += (
        "\n\nJab aap ready feel karo — sirf agar aap chaaho — tab hum reading "
        "pe wapas aa sakte hain. Koi zabardasti nahi."
    )
    return base


async def assess_distress(
    text: str,
    *,
    classify_fn: ClassifyFn | None = None,
) -> DistressResult:
    """Always prefer Haiku classifier; failsafe only if LLM missing/fails."""
    body = (text or "").strip()
    if not body:
        return DistressResult(False, False, "none")

    if classify_fn is not None:
        try:
            raw = await classify_fn(DISTRESS_CLASSIFIER_PROMPT, body)
            parsed = parse_classifier_json(raw)
            if parsed is not None:
                return parsed
        except Exception:
            pass

    if self_harm_failsafe(body):
        return DistressResult(True, True, "failsafe")
    return DistressResult(False, False, "none")


def extract_inbound_text(messages: dict | None) -> str:
    if not isinstance(messages, dict):
        return ""
    if messages.get("type") == "text":
        return ((messages.get("text") or {}).get("body") or "").strip()
    return ""
