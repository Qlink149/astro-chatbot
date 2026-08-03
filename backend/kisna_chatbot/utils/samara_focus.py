"""Conversation focus object — referent resolution for follow-ups."""

from __future__ import annotations

import json
import re
from typing import Any


def empty_focus() -> dict[str, Any]:
    return {
        "topic": None,
        "last_claim": None,
        "dates_on_table": [],
        "open_loop": None,
        "user_facts": [],
        "awaiting": None,
        "last_archetype": None,
    }


def get_focus(profile: dict) -> dict[str, Any]:
    focus = dict(empty_focus())
    existing = profile.get("conversation_focus")
    if isinstance(existing, dict):
        focus.update({k: existing.get(k, focus[k]) for k in focus})
    if focus.get("topic") is None and profile.get("chosen_topic"):
        focus["topic"] = profile.get("chosen_topic")
    if focus.get("open_loop") is None and profile.get("open_loop_summary"):
        focus["open_loop"] = str(profile.get("open_loop_summary") or "")[:200]
    if focus.get("last_archetype") is None and profile.get("last_archetype"):
        focus["last_archetype"] = profile.get("last_archetype")
    return focus


def _iso_dates_from_engine_payload(*chunks: str | None) -> list[str]:
    found: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        for m in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", chunk):
            if m not in found:
                found.append(m)
    return found


def update_focus_after_bot(
    profile: dict,
    *,
    text: str,
    claim: str | None = None,
    dates: list[str] | None = None,
    awaiting: str | None = None,
    topic: str | None = None,
    open_loop: str | None = None,
) -> dict[str, Any]:
    focus = get_focus(profile)
    if topic:
        focus["topic"] = topic
    if claim:
        focus["last_claim"] = claim[:300]
    elif text:
        # First substantive line as soft claim
        line = next(
            (ln.strip() for ln in (text or "").splitlines() if ln.strip()),
            "",
        )
        if line:
            focus["last_claim"] = line[:300]
    if dates:
        merged = list(focus.get("dates_on_table") or [])
        for d in dates:
            if d and d not in merged:
                merged.append(d)
        focus["dates_on_table"] = merged[-6:]
    else:
        # Prefer engine ISO already on profile chart when bot named month labels;
        # do not invent ISO from free text.
        pass
    if awaiting is not None:
        focus["awaiting"] = awaiting
    if open_loop is not None:
        focus["open_loop"] = open_loop[:300]
    if profile.get("last_archetype"):
        focus["last_archetype"] = profile.get("last_archetype")
    profile["conversation_focus"] = focus
    return focus


def update_focus_from_user(
    profile: dict,
    *,
    text: str | None = None,
    fact: str | None = None,
    awaiting: str | None = None,
) -> dict[str, Any]:
    focus = get_focus(profile)
    facts = list(focus.get("user_facts") or [])
    volunteer = (fact or text or "").strip()
    if volunteer and len(volunteer) > 2:
        # Keep user's own words; skip pure yes/no
        low = volunteer.lower()
        if low not in ("yes", "haan", "ha", "no", "nahi", "ok", "okay"):
            if volunteer not in facts:
                facts.append(volunteer[:160])
            focus["user_facts"] = facts[-8:]
    if awaiting is not None:
        focus["awaiting"] = awaiting
    profile["conversation_focus"] = focus
    return focus


def focus_prompt_block(profile: dict) -> str:
    focus = get_focus(profile)
    return (
        "CONVERSATION FOCUS (structured state — use for referents)\n"
        f"{json.dumps(focus, ensure_ascii=False)}\n"
        "Pronouns and short follow-ups (that / it / why / kab / aur? / kitna) "
        "resolve against last_claim, dates_on_table, and open_loop. "
        "If the referent is genuinely ambiguous, ask ONE short clarifying "
        "question — do not guess and do not give a generic answer."
    )
