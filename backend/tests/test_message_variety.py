"""Message variety: archetype rotation and banned openers."""

from __future__ import annotations

import os

os.environ.setdefault("ENV_MODE", "dev")

from kisna_chatbot.prompts.samara_reading import _SHARED_RULES
from kisna_chatbot.utils.samara_variety import (
    choose_archetype,
    record_outbound_variety,
    variety_prompt_block,
)


def test_archetype_never_repeats_consecutively():
    profile: dict = {}
    seen = []
    for _ in range(8):
        a = choose_archetype(profile)
        assert a != profile.get("last_archetype") or not profile.get("last_archetype")
        record_outbound_variety(profile, f"Hello from {a}", a)
        seen.append(a)
    for i in range(1, len(seen)):
        assert seen[i] != seen[i - 1]


def test_variety_block_bans_openers():
    profile = {"recent_bot_messages": ["Achha…"], "recent_openers": ["achha…"]}
    block = variety_prompt_block(profile, "punch")
    assert "Aapke chart mein" in block
    assert "In your chart" in block
    assert "Achha" in block or "achha" in block


def test_shared_rules_ban_name_and_chart_openers():
    r = _SHARED_RULES.lower()
    assert "do not open with the user's name" in r
    assert "aapke chart mein" in r
    assert "in your chart" in r
