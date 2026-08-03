"""Pure antardasha helpers (no Swiss Ephemeris import).

Used by engine.py and unit tests. All dates/labels originate here or in
compute_chart — the LLM never invents them.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

_MONTH_EN = (
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


def window_label_from_ymd(year: int, month: int) -> tuple[str, str]:
    """Soft early/mid/late + year labels. Engine-side only."""
    if month <= 4:
        return (f"early {year}", f"{year} ke shuruaat")
    if month <= 8:
        return (f"mid {year}", f"{year} ke beech")
    return (f"late {year}", f"{year} ke ant")


def window_label_month_from_ymd(
    year: int, month: int, day: Optional[int] = None
) -> tuple[str, str]:
    """Month-level (or adjacent month-pair) labels for Beat 2b/2c.

    Never day-level. If day >= 20, use a month-pair spanning into the next month.
    """
    m = max(1, min(12, int(month)))
    y = int(year)
    name = _MONTH_EN[m]
    if day is not None and int(day) >= 20:
        if m == 12:
            next_name, next_y = _MONTH_EN[1], y + 1
            en = f"{name}–{next_name} {next_y}" if next_y != y else f"{name}–{next_name} {y}"
            # Cross-year pair: "December 2019–January 2020"
            en = f"{name} {y}–{next_name} {next_y}"
            hi = f"{name} {y}–{next_name} {next_y} ke aas-paas"
        else:
            next_name = _MONTH_EN[m + 1]
            en = f"{name}–{next_name} {y}"
            hi = f"{name}–{next_name} {y} ke aas-paas"
        return en, hi
    en = f"{name} {y}"
    hi = f"{name} {y} ke aas-paas"
    return en, hi


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


def curate_upcoming_periods(
    antardasha_timeline: list[dict],
    *,
    today: date | None = None,
    birth_year: int | None = None,
    current_age: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Next future antardasha transitions with exact ISO dates (engine only)."""
    today = today or date.today()
    today_s = today.isoformat()
    future: list[dict] = []
    for p in antardasha_timeline or []:
        start = str(p.get("start") or "")
        if not start or start <= today_s:
            continue
        antar = p.get("antar_planet_en") or ""
        theme_en, theme_hi = ANTAR_THEMES.get(antar, ("change", "badlav"))
        age_at = p.get("age_start")
        if age_at is None and birth_year is not None and len(start) >= 4:
            try:
                age_at = int(start[:4]) - int(birth_year)
            except ValueError:
                age_at = current_age
        future.append(
            {
                "start": start,
                "end": p.get("end"),
                "maha_planet_en": p.get("maha_planet_en"),
                "maha_planet_hi": p.get("maha_planet_hi"),
                "antar_planet_en": p.get("antar_planet_en"),
                "antar_planet_hi": p.get("antar_planet_hi"),
                "age_at_start": age_at,
                "theme_en": theme_en,
                "theme_hi": theme_hi,
                "window_label_month_en": p.get("window_label_month_en"),
                "window_label_month_hi": p.get("window_label_month_hi"),
            }
        )
        if len(future) >= limit:
            break
    return future


def lookup_antardasha_covering_year(
    antardasha_timeline: list[dict], year: int
) -> dict | None:
    """Return the antardasha row covering a calendar year (prefer mid-year)."""
    mid = f"{int(year):04d}-06-15"
    covering = []
    for p in antardasha_timeline or []:
        start = str(p.get("start") or "")
        end = str(p.get("end") or "")
        if not start:
            continue
        if start[:4] == f"{int(year):04d}" or (
            end and start <= mid <= end
        ) or (start[:4] <= f"{int(year):04d}" <= (end[:4] if end else start[:4])):
            covering.append(p)
    if not covering:
        return None
    # Prefer period that contains mid-year; else first start in that year
    for p in covering:
        start = str(p.get("start") or "")
        end = str(p.get("end") or "9999-12-31")
        if start <= mid <= end:
            return p
    return covering[0]
