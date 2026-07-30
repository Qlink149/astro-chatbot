"""
Clara AI Jyotishi — Kundli Calculation Engine
==============================================

CRITICAL ARCHITECTURAL RULE
---------------------------
This module is the ONLY thing that calculates a chart.
The LLM NEVER calculates. It only receives the JSON this module produces
and writes the warm interpretation on top of it.

Everything here is deterministic: same birth details -> same chart, always.
Built on pyswisseph (Swiss Ephemeris, NASA JPL DE431 data) via PyJHora.
Ayanamsa is pinned to LAHIRI (Government of India standard).

BIRTH-TIME FALLBACK
-------------------
If birth time is missing, Lagna (ascendant) is unreliable. This engine
does NOT silently guess. It sets `has_birth_time=False`, omits the Lagna,
and marks the chart as `surya_kundli` (sun-level) so the bot can honestly
tell the user the limitation instead of faking certainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import swisseph as swe
from jhora import const, utils
from jhora.panchanga import drik
from jhora.horoscope.chart import charts
from jhora.horoscope.dhasa.graha import vimsottari

from kundli_engine.antardasha_labels import (
    curate_turning_points as _curate_turning_points,
    window_label_from_ymd as _window_label_from_ymd,
)

# pysweph (cp312-compatible fork) can return more than the classic
# (xx, retflag) 2-tuple from calc_ut/calc. PyJHora 4.8.7 still does:
#   longi, _ = swe.calc_ut(...)
# Normalize back to the legacy shape before any chart math runs.
def _legacy_swe_calc_result(result):
    if not isinstance(result, tuple):
        return result
    if len(result) == 2:
        return result
    if isinstance(result[0], (list, tuple)):
        return result[0], result[1]
    if len(result) >= 7:
        return list(result[:6]), int(result[6])
    return list(result[:-1]), result[-1]


def _patch_swe_calc_api() -> None:
    for name in ("calc_ut", "calc"):
        orig = getattr(swe, name, None)
        if orig is None or getattr(orig, "_clara_legacy_patched", False):
            continue

        def _wrapped(*args, _orig=orig, **kwargs):
            return _legacy_swe_calc_result(_orig(*args, **kwargs))

        _wrapped._clara_legacy_patched = True  # type: ignore[attr-defined]
        setattr(swe, name, _wrapped)


_patch_swe_calc_api()

# PyJHora wheels no longer ship Swiss Ephemeris .se1 files. const.py points
# swe at an empty jhora/data/ephe/ at import time — override that path here
# AND patch const so later utils.set_ephemeris_data_path() cannot wipe it.
_EPHE_DIR = Path(__file__).resolve().parent / "ephe"
if not _EPHE_DIR.is_dir():
    raise RuntimeError(f"Bundled Swiss Ephemeris directory missing: {_EPHE_DIR}")
_EPHE_PATH = str(_EPHE_DIR)
const._EPHIMERIDE_DATA_PATH = _EPHE_PATH
const._ephe_path = _EPHE_PATH
swe.set_ephe_path(_EPHE_PATH)
if hasattr(utils, "set_ephemeris_data_path"):
    utils.set_ephemeris_data_path(_EPHE_PATH)

# --- Pin the ayanamsa once, at import time. Never change this at runtime. ---
const._DEFAULT_AYANAMSA_MODE = "LAHIRI"
drik.set_ayanamsa_mode("LAHIRI")

# Sign names (0-indexed as PyJHora returns them: 0 = Aries/Mesha)
SIGNS_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
SIGNS_HI = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
]

# Planet indices as PyJHora returns them in rasi_chart rows.
# 'L' = Lagna (ascendant). 0..8 = the nine grahas below.
PLANETS = {
    0: ("Sun", "Surya"),
    1: ("Moon", "Chandra"),
    2: ("Mars", "Mangal"),
    3: ("Mercury", "Budha"),
    4: ("Jupiter", "Guru"),
    5: ("Venus", "Shukra"),
    6: ("Saturn", "Shani"),
    7: ("Rahu", "Rahu"),
    8: ("Ketu", "Ketu"),
}

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]


@dataclass
class BirthDetails:
    """Input. Time is optional on purpose (birth-time problem)."""
    year: int
    month: int
    day: int
    latitude: float
    longitude: float
    timezone_offset: float = 5.5          # IST default
    hour: Optional[int] = None
    minute: Optional[int] = None
    place_name: str = ""

    @property
    def has_time(self) -> bool:
        return self.hour is not None and self.minute is not None


def _sign_of(deg_tuple) -> int:
    """PyJHora returns (sign_index, degrees_in_sign). Return sign index."""
    return int(deg_tuple[0])


def _deg_in_sign(deg_tuple) -> float:
    return float(deg_tuple[1])


def _nakshatra_from_nak_raw(nak_raw) -> dict:
    """drik.nakshatra returns [nak_index(1..27), pada, ...]."""
    idx = int(nak_raw[0]) - 1  # -> 0..26
    pada = int(nak_raw[1])
    idx = max(0, min(26, idx))
    return {"name": NAKSHATRAS[idx], "index": idx + 1, "pada": pada}


def _jd_to_year(jd: float) -> str:
    y, m, d, _ = utils.jd_to_gregorian(jd)
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _build_antardasha_timeline(
    jd: float,
    place,
    birth_year: int,
    current_age: int,
) -> list[dict]:
    """Flat chronological antardasha (bhukti) rows from PyJHora.

    Returns [] on any failure — never raises into the reading path.
    """
    from jhora import const as jhora_const

    try:
        _vim_bal, rows = vimsottari.get_vimsottari_dhasa_bhukthi(
            jd,
            place,
            dhasa_level_index=jhora_const.MAHA_DHASA_DEPTH.ANTARA,
        )
    except Exception:
        return []

    if not rows:
        return []

    timeline: list[dict] = []
    for i, row in enumerate(rows):
        try:
            lords, start_greg, _dur = row[0], row[1], row[2]
            if not lords or len(lords) < 2:
                continue
            maha_idx, antar_idx = int(lords[0]), int(lords[1])
            maha_en, maha_hi = PLANETS.get(maha_idx, (f"P{maha_idx}", ""))
            antar_en, antar_hi = PLANETS.get(antar_idx, (f"P{antar_idx}", ""))

            sy, sm, sd = int(start_greg[0]), int(start_greg[1]), int(start_greg[2])
            start_str = f"{sy:04d}-{sm:02d}-{sd:02d}"

            if i + 1 < len(rows):
                next_greg = rows[i + 1][1]
                ey, em, ed = int(next_greg[0]), int(next_greg[1]), int(next_greg[2])
                end_str = f"{ey:04d}-{em:02d}-{ed:02d}"
                end_year = ey
            else:
                # Last bhukti: approximate end from duration years if present
                dur = float(_dur or 0)
                end_jd = utils.julian_day_number(
                    drik.Date(sy, sm, sd), (0, 0, 0)
                ) + dur * 365.2425
                end_str = _jd_to_year(end_jd)
                end_year = int(end_str[:4])

            age_start = sy - birth_year
            age_end = end_year - birth_year
            starts_before_birth = sy < birth_year
            # Lived adult past only: ended by now, and reached adulthood.
            is_relevant = (
                age_end is not None
                and age_end <= current_age
                and age_end >= 15
            )
            label_en, label_hi = _window_label_from_ymd(sy, sm)
            timeline.append({
                "maha_planet_en": maha_en,
                "maha_planet_hi": maha_hi,
                "antar_planet_en": antar_en,
                "antar_planet_hi": antar_hi,
                "start": start_str,
                "end": end_str,
                "age_start": age_start,
                "age_end": age_end,
                "starts_before_birth": starts_before_birth,
                "is_relevant": is_relevant,
                "window_label_en": label_en,
                "window_label_hi": label_hi,
            })
        except Exception:
            continue
    return timeline


def compute_chart(birth: BirthDetails) -> dict:
    """
    Deterministic chart computation.
    Returns a clean JSON-serializable dict for the interpretation layer.
    """
    # Re-assert ephemeris path — PyJHora helpers may reset it to empty package data.
    swe.set_ephe_path(_EPHE_PATH)

    # If time missing, use noon as a placeholder ONLY for sun-level positions,
    # and flag that Lagna is not trustworthy.
    hour = birth.hour if birth.has_time else 12
    minute = birth.minute if birth.has_time else 0

    dob = drik.Date(birth.year, birth.month, birth.day)
    tob = (hour, minute, 0)
    place = drik.Place(
        birth.place_name or "birthplace",
        birth.latitude, birth.longitude, birth.timezone_offset,
    )
    jd = utils.julian_day_number(dob, tob)

    rasi = charts.rasi_chart(jd, place)  # list of ['L'/0..8, (sign, deg)]

    planets_out = {}
    lagna_out = None
    for row in rasi:
        pid, pos = row[0], row[1]
        sign_idx = _sign_of(pos)
        entry = {
            "sign_en": SIGNS_EN[sign_idx],
            "sign_hi": SIGNS_HI[sign_idx],
            "sign_index": sign_idx,
            "degrees": round(_deg_in_sign(pos), 2),
        }
        if pid == "L":
            lagna_out = entry
        else:
            en, hi = PLANETS[int(pid)]
            planets_out[en] = {**entry, "name_hi": hi}

    # Moon sign = Rashi (the "moon sign" people identify with)
    moon = planets_out.get("Moon", {})
    rashi = {
        "sign_en": moon.get("sign_en"),
        "sign_hi": moon.get("sign_hi"),
        "sign_index": moon.get("sign_index"),
    }

    # Nakshatra (from Moon) — always available (doesn't need exact Lagna)
    nak_raw = drik.nakshatra(jd, place)
    nakshatra = _nakshatra_from_nak_raw(nak_raw)

    # Sun sign (Surya Rashi) — the fallback identity when no birth time
    sun = planets_out.get("Sun", {})
    surya_rashi = {
        "sign_en": sun.get("sign_en"),
        "sign_hi": sun.get("sign_hi"),
        "sign_index": sun.get("sign_index"),
    }

    # Vimshottari Mahadasha timeline -> mapped to real calendar years.
    # This is the TRUST ANCHOR for the Ateet (past) section.
    from datetime import date as _date
    _today = _date.today()
    current_age = _today.year - birth.year - (
        (_today.month, _today.day) < (birth.month, birth.day)
    )

    dasha_timeline = []
    try:
        md = vimsottari.vimsottari_mahadasa(jd, place)
        seq = list(md.items())
        for i, (planet_idx, start_jd) in enumerate(seq):
            end_jd = seq[i + 1][1] if i + 1 < len(seq) else None
            en, hi = PLANETS.get(int(planet_idx), (f"P{planet_idx}", ""))
            start_str = _jd_to_year(start_jd)
            end_str = _jd_to_year(end_jd) if end_jd else None
            start_year = int(start_str[:4])
            end_year = int(end_str[:4]) if end_str else None
            # Age of the person during this period (clamped at birth).
            age_start = start_year - birth.year
            age_end = (end_year - birth.year) if end_year else None
            # Flag periods that began before the person was born. Vimshottari's
            # first mahadasha almost always starts before birth — the LLM must
            # NOT narrate life before birth. This flag makes that explicit.
            starts_before_birth = start_year < birth.year
            # Relevance tagging so the prompt can focus on recent adult life
            # instead of narrating childhood or 20-year spans.
            lived_from = max(age_start, 0)
            if age_end is not None and current_age > age_end:
                phase = "past"
            elif age_start <= current_age and (age_end is None or current_age <= age_end):
                phase = "current"
            else:
                phase = "future"
            # "Relevant" = the adult, near-present chapters people actually
            # recognise. Childhood (< ~15) is NOT a trust anchor.
            is_relevant = (
                phase in ("past", "current")
                and (age_end is None or age_end >= 15)
                and (current_age - lived_from) <= 20
            )
            dasha_timeline.append({
                "planet_en": en,
                "planet_hi": hi,
                "start": start_str,
                "end": end_str,
                "age_start": age_start,          # may be negative if before birth
                "age_end": age_end,
                "starts_before_birth": starts_before_birth,
                "lived_from_age": lived_from,
                "phase": phase,                  # past / current / future
                "is_relevant": is_relevant,      # prompt should focus on these
            })
    except Exception as e:  # never crash the reading over dasha
        dasha_timeline = []
        _dasha_error = str(e)

    # Antardasha / turning points — ONLY when birth time is known.
    # Noon-placeholder JD is too unreliable for dated anchors.
    if birth.has_time:
        antardasha_timeline = _build_antardasha_timeline(
            jd, place, birth.year, current_age
        )
        turning_points = _curate_turning_points(antardasha_timeline)
        dated_anchors_available = True
    else:
        antardasha_timeline = []
        turning_points = []
        dated_anchors_available = False

    chart = {
        "meta": {
            "has_birth_time": birth.has_time,
            "chart_type": "full" if birth.has_time else "surya_kundli",
            "ayanamsa": "Lahiri",
            "note_if_no_time": (
                None if birth.has_time else
                "Exact birth time missing. Lagna (ascendant) omitted. "
                "Reading falls back to Sun/Moon-sign level. Tell the user honestly."
            ),
            "place_name": birth.place_name,
            # Birth anchor — the LLM MUST use this as the floor. Never narrate
            # any life event, feeling, or period before birth_date.
            "birth_date": f"{birth.year:04d}-{birth.month:02d}-{birth.day:02d}",
            "birth_year": birth.year,
            "current_age": current_age,
            "birth_time": (
                f"{birth.hour:02d}:{birth.minute:02d}" if birth.has_time else None
            ),
            "dated_anchors_available": dated_anchors_available,
        },
        "lagna": lagna_out if birth.has_time else None,
        "rashi": rashi,               # Moon sign
        "surya_rashi": surya_rashi,   # Sun sign (fallback identity)
        "nakshatra": nakshatra,
        "planets": planets_out,
        "dasha_timeline": dasha_timeline,
        "antardasha_timeline": antardasha_timeline,
        "turning_points": turning_points,
    }
    # Houses / bhava — ONLY when birth time is known (whole-sign from Lagna).
    # When time is unknown, omit the key entirely — never estimate.
    if birth.has_time and lagna_out is not None:
        chart["houses"] = _whole_sign_houses(lagna_out, planets_out)
    return chart


def _whole_sign_houses(lagna: dict, planets: dict) -> dict:
    """Whole-sign bhava table from Lagna (Vedic). Engine-side only.

    Returns:
      {
        "system": "whole_sign",
        "lagna_sign_en": ...,
        "bhavas": { "1": {"sign_en", "sign_hi", "sign_index", "planets": [...]}, ... },
        "planet_houses": { "Sun": 1, "Moon": 10, ... }
      }
    """
    lagna_idx = int(lagna["sign_index"])
    bhavas: dict = {}
    for h in range(1, 13):
        sign_idx = (lagna_idx + h - 1) % 12
        bhavas[str(h)] = {
            "sign_en": SIGNS_EN[sign_idx],
            "sign_hi": SIGNS_HI[sign_idx],
            "sign_index": sign_idx,
            "planets": [],
        }
    planet_houses: dict = {}
    for name, pos in (planets or {}).items():
        if not isinstance(pos, dict) or pos.get("sign_index") is None:
            continue
        house_num = ((int(pos["sign_index"]) - lagna_idx) % 12) + 1
        planet_houses[name] = house_num
        bhavas[str(house_num)]["planets"].append(name)
    return {
        "system": "whole_sign",
        "lagna_sign_en": lagna.get("sign_en"),
        "lagna_sign_hi": lagna.get("sign_hi"),
        "bhavas": bhavas,
        "planet_houses": planet_houses,
    }
