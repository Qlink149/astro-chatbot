"""Slim chart_json slices for prompts — never invent fields."""

from __future__ import annotations

from datetime import date
from typing import Any


def current_antardasha_row(
    chart: dict | None,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Row from antardasha_timeline where start <= today <= end."""
    if not chart:
        return None
    today = today or date.today()
    today_s = today.isoformat()
    for row in chart.get("antardasha_timeline") or []:
        if not isinstance(row, dict):
            continue
        start = str(row.get("start") or "")
        end = str(row.get("end") or "")
        if start and end and start <= today_s <= end:
            return {
                "maha_planet_en": row.get("maha_planet_en"),
                "maha_planet_hi": row.get("maha_planet_hi"),
                "antar_planet_en": row.get("antar_planet_en"),
                "antar_planet_hi": row.get("antar_planet_hi"),
                "start": start,
                "end": end,
                "window_label_month_en": row.get("window_label_month_en"),
                "window_label_month_hi": row.get("window_label_month_hi"),
            }
    return None


def slim_chart_for_beat(chart: dict | None, beat_or_purpose: str) -> dict[str, Any]:
    """Prune bulky fields; keep what the current beat needs.

    Always engine-sourced — no LLM computation.
    """
    if not chart:
        return {}
    purpose = (beat_or_purpose or "").lower()
    meta = dict(chart.get("meta") or {})
    out: dict[str, Any] = {
        "meta": meta,
        "rashi": chart.get("rashi"),
        "surya_rashi": chart.get("surya_rashi"),
        "nakshatra": chart.get("nakshatra"),
        "lagna": chart.get("lagna"),
    }

    if purpose in ("beat1",):
        # Soft past uses mahadasha via soft_past_range helper — keep light dasha
        out["dasha_timeline"] = _slim_dasha(chart.get("dasha_timeline"), limit=4)
        return out

    if purpose in ("beat2", "beat2a"):
        out["turning_points"] = chart.get("turning_points") or []
        out["dasha_timeline"] = _slim_dasha(chart.get("dasha_timeline"), limit=6)
        return out

    if purpose in ("beat2b", "beat2c"):
        out["turning_points"] = chart.get("turning_points") or []
        return out

    if purpose in ("beat4", "paid_deep", "followup", "solicited", "muhurat"):
        out["turning_points"] = chart.get("turning_points") or []
        out["upcoming_periods"] = chart.get("upcoming_periods") or []
        current = current_antardasha_row(chart)
        if current:
            out["current_period"] = current
        out["dasha_timeline"] = _slim_dasha(chart.get("dasha_timeline"), limit=6)
        if chart.get("houses"):
            # Drop exact degrees; keep house table if present
            houses = chart["houses"]
            if isinstance(houses, dict):
                out["houses"] = {
                    "system": houses.get("system"),
                    "lagna_sign_en": houses.get("lagna_sign_en"),
                    "planet_houses": houses.get("planet_houses"),
                }
        # Planets without degree noise
        planets = chart.get("planets") or {}
        if isinstance(planets, dict):
            slim_p = {}
            for name, info in planets.items():
                if isinstance(info, dict):
                    slim_p[name] = {
                        k: info.get(k)
                        for k in ("sign_en", "sign_hi", "retrograde")
                        if k in info
                    }
                else:
                    slim_p[name] = info
            out["planets"] = slim_p
        return out

    # Default: meta + identity + turning + upcoming
    out["turning_points"] = chart.get("turning_points") or []
    out["upcoming_periods"] = chart.get("upcoming_periods") or []
    return out


def _slim_dasha(timeline: Any, *, limit: int) -> list:
    rows = list(timeline or [])
    slim = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        slim.append(
            {
                k: row.get(k)
                for k in (
                    "planet_en",
                    "planet_hi",
                    "start",
                    "end",
                    "age_start",
                    "age_end",
                    "phase",
                    "is_relevant",
                )
                if k in row
            }
        )
    # Prefer relevant / current
    relevant = [r for r in slim if r.get("is_relevant") or r.get("phase") == "current"]
    if len(relevant) >= min(2, limit):
        return relevant[-limit:]
    return slim[-limit:]
