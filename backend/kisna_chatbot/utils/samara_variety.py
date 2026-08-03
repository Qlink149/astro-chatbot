"""Message archetype rotation and anti-repetition for Samara readings."""

from __future__ import annotations

from typing import Literal

Archetype = Literal["reaction", "punch", "read", "question"]

ARCHETYPES: tuple[Archetype, ...] = ("reaction", "punch", "read", "question")

_ARCHETYPE_INSTRUCTIONS: dict[Archetype, str] = {
    "reaction": (
        "ARCHETYPE for this message: reaction — write exactly ONE short human "
        "line (e.g. a quiet beat like Achha… / Hmm.). No chart dump."
    ),
    "punch": (
        "ARCHETYPE for this message: punch — 1–2 lines, one sharp observation. "
        "No filler, no structure announcement."
    ),
    "read": (
        "ARCHETYPE for this message: read — 3–5 lines of substantive reading. "
        "Vary rhythm from your recent messages."
    ),
    "question": (
        "ARCHETYPE for this message: question — a SINGLE question only, "
        "nothing else. No preamble."
    ),
}


def choose_archetype(profile: dict, *, prefer: Archetype | None = None) -> Archetype:
    """Pick an archetype; never repeat last_archetype consecutively."""
    last = (profile.get("last_archetype") or "").strip()
    if prefer and prefer in ARCHETYPES and prefer != last:
        return prefer
    # Prefer read for substantive beats unless last was read
    order: list[Archetype] = ["read", "punch", "question", "reaction"]
    for a in order:
        if a != last:
            return a
    return "punch" if last != "punch" else "read"


def record_outbound_variety(profile: dict, text: str, archetype: Archetype) -> None:
    """Track last archetype, recent bot messages, and opening phrases."""
    profile["last_archetype"] = archetype
    focus = dict(profile.get("conversation_focus") or {})
    focus["last_archetype"] = archetype
    profile["conversation_focus"] = focus

    recent = list(profile.get("recent_bot_messages") or [])
    cleaned = (text or "").strip()
    if cleaned:
        recent.append(cleaned[:400])
    profile["recent_bot_messages"] = recent[-3:]

    opener = cleaned.split("\n")[0].strip()[:80] if cleaned else ""
    openers = list(profile.get("recent_openers") or [])
    if opener:
        openers.append(opener.lower())
    profile["recent_openers"] = openers[-5:]


def variety_prompt_block(profile: dict, archetype: Archetype) -> str:
    """Inject anti-repetition + archetype instruction into reading prompts."""
    recent = list(profile.get("recent_bot_messages") or [])
    openers = list(profile.get("recent_openers") or [])
    lines = [
        "VARIETY / ANTI-REPETITION (mandatory)",
        _ARCHETYPE_INSTRUCTIONS[archetype],
        "Do NOT reuse openers, sentence structures, or rhythms from your last messages.",
        "BANNED openers: user's name first; 'Aapke chart mein…'; 'In your chart…'; "
        "method talk ('That context helps me see…', 'Based on your chart…'); "
        "structure announcements ('Now let's look…', 'Moving on…'); bullets/headers/lists.",
    ]
    if recent:
        lines.append("Your last outbound messages (do not echo):")
        for i, msg in enumerate(recent, 1):
            lines.append(f"  [{i}] {msg[:240]}")
    if openers:
        lines.append(
            "Recently used opening phrases (forbid reuse): "
            + " | ".join(openers[-5:])
        )
    return "\n".join(lines)
