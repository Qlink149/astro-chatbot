"""Pure antardasha helpers (no Swiss Ephemeris import).

Used by engine.py and unit tests. All dates/labels originate here or in
compute_chart — the LLM never invents them.
"""

from __future__ import annotations


def window_label_from_ymd(year: int, month: int) -> tuple[str, str]:
    """Soft early/mid/late + year labels. Engine-side only."""
    if month <= 4:
        return (f"early {year}", f"{year} ke shuruaat")
    if month <= 8:
        return (f"mid {year}", f"{year} ke beech")
    return (f"late {year}", f"{year} ke ant")


# Theme keywords only — never life events.
ANTAR_THEMES: dict[str, tuple[str, str]] = {
    "Saturn": ("responsibility", "zimmedari"),
    "Rahu": ("ambition", "ambition"),
    "Ketu": ("letting go", "tyag"),
    "Jupiter": ("growth", "vistar"),
    "Mars": ("drive", "urja"),
    "Sun": ("identity", "pehchaan"),
    "Moon": ("emotions", "bhavna"),
    "Mercury": ("communication", "soch-baat"),
    "Venus": ("harmony", "sukh"),
}

TURNING_POINT_PREFER = ("Saturn", "Rahu", "Ketu", "Jupiter", "Mars")


def curate_turning_points(
    antardasha_timeline: list[dict], limit: int = 5
) -> list[dict]:
    """Pick up to `limit` narratively significant relevant transitions.

    Prefer Saturn/Rahu/Ketu/Jupiter/Mars antars. Chronological, newest last.
    Themes are keywords only — never life events.
    """
    relevant = [p for p in antardasha_timeline if p.get("is_relevant")]
    preferred = [
        p for p in relevant if p.get("antar_planet_en") in TURNING_POINT_PREFER
    ]
    chosen = preferred[-limit:] if len(preferred) >= limit else preferred[:]
    if len(chosen) < limit:
        for p in relevant:
            if p in chosen:
                continue
            chosen.append(p)
            if len(chosen) >= limit:
                break
    chosen.sort(key=lambda p: p.get("start") or "")
    chosen = chosen[-limit:]
    out = []
    for p in chosen:
        antar = p.get("antar_planet_en") or ""
        theme_en, theme_hi = ANTAR_THEMES.get(antar, ("change", "badlav"))
        out.append({**p, "theme_en": theme_en, "theme_hi": theme_hi})
    return out
