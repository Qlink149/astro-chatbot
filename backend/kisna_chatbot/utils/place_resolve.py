"""Offline-first birth-place resolution for Samara.

Resolution order:
1. Slim GeoNames cities15000 index (bundled pickle)
2. Fuzzy match (rapidfuzz) with country bias from WhatsApp dial code
3. Nominatim fallback for villages / misses

Never silently invents a place — callers must confirm candidates.
"""

from __future__ import annotations

import logging
import pickle
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parents[2] / "data" / "geonames" / "cities15000_slim.pkl"

# Dial-code prefix → ISO2 (longest match first). Bias only — never hard-lock.
_DIAL_TO_CC: list[tuple[str, str]] = [
    ("971", "AE"),
    ("966", "SA"),
    ("974", "QA"),
    ("965", "KW"),
    ("968", "OM"),
    ("973", "BH"),
    ("880", "BD"),
    ("977", "NP"),
    ("94", "LK"),
    ("92", "PK"),
    ("91", "IN"),
    ("86", "CN"),
    ("81", "JP"),
    ("65", "SG"),
    ("61", "AU"),
    ("60", "MY"),
    ("55", "BR"),
    ("49", "DE"),
    ("44", "GB"),
    ("33", "FR"),
    ("27", "ZA"),
    ("1", "US"),  # also CA — US bias is fine as default for +1
]

_COUNTRY_ALIASES = {
    "india": "IN",
    "bharat": "IN",
    "pakistan": "PK",
    "bangladesh": "BD",
    "nepal": "NP",
    "sri lanka": "LK",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "uae": "AE",
    "dubai": "AE",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().replace(",", " ").split())


def infer_country_iso(phone_number: str | None) -> str | None:
    """DEFAULT country from WhatsApp wa_id (e.g. 91XXXXXXXXXX → IN). Bias only."""
    digits = re.sub(r"\D", "", phone_number or "")
    if digits.startswith("00"):
        digits = digits[2:]
    for prefix, cc in _DIAL_TO_CC:
        if digits.startswith(prefix) and len(digits) > len(prefix) + 4:
            return cc
    return None


@lru_cache(maxsize=1)
def _load_index() -> list[dict[str, Any]]:
    if not _DATA.is_file():
        logger.warning("GeoNames index missing: %s — run scripts/build_geonames_index.py", _DATA)
        return []
    try:
        rows = pickle.loads(_DATA.read_bytes())
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        logger.warning("Failed to load GeoNames index: %s", exc)
        return []


def _query_country_hint(query: str) -> str | None:
    q = _normalize(query)
    for name, cc in _COUNTRY_ALIASES.items():
        if name in q:
            return cc
    return None


def _score_row(query: str, row: dict[str, Any], bias_cc: str | None) -> float:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        # Fallback: simple containment
        q = _normalize(query)
        names = [_normalize(row.get("name") or ""), _normalize(row.get("ascii") or "")]
        names += [_normalize(a) for a in (row.get("alts") or [])[:8]]
        best = 0.0
        for n in names:
            if not n:
                continue
            if q == n:
                best = max(best, 100.0)
            elif q in n or n in q:
                best = max(best, 80.0)
        if bias_cc and row.get("cc") == bias_cc:
            best += 5.0
        return best

    q = _normalize(query)
    # Strip trailing country/state tokens for matching city core
    tokens = q.split()
    city_guess = q
    if len(tokens) >= 2:
        city_guess = " ".join(tokens[:2]) if len(tokens[0]) <= 3 else tokens[0]
        # Prefer full query too
    candidates = [row.get("name") or "", row.get("ascii") or ""]
    candidates += list(row.get("alts") or [])[:8]
    # Also match "udaipur rajasthan"
    admin = (row.get("admin1") or "").lower()
    country = (row.get("country") or "").lower()
    display = (row.get("display") or "").lower()
    scores = [fuzz.WRatio(q, _normalize(c)) for c in candidates if c]
    scores.append(fuzz.WRatio(q, display))
    if admin:
        scores.append(fuzz.WRatio(q, f"{_normalize(row.get('name') or '')} {admin}"))
    best = max(scores) if scores else 0.0
    # Boost exact ascii/name equality
    if q in {_normalize(row.get("name") or ""), _normalize(row.get("ascii") or "")}:
        best = max(best, 98.0)
    if bias_cc and row.get("cc") == bias_cc:
        best += 8.0
    # Mild population nudge (log-ish)
    pop = int(row.get("pop") or 0)
    if pop > 1_000_000:
        best += 3.0
    elif pop > 100_000:
        best += 1.5
    # If user typed a country and row mismatches, penalize
    hinted = _query_country_hint(query)
    if hinted and row.get("cc") != hinted:
        best -= 15.0
    return best


def search_places(
    query: str,
    *,
    phone_number: str | None = None,
    limit: int = 3,
    min_score: float = 70.0,
) -> list[dict[str, Any]]:
    """Return up to `limit` place candidates ranked by fuzzy score + bias."""
    q = _normalize(query)
    if not q or len(q) < 2:
        return []
    bias = _query_country_hint(query) or infer_country_iso(phone_number)
    rows = _load_index()
    if not rows:
        return []

    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        fuzz = None
        process = None

    scored: list[tuple[float, dict[str, Any]]] = []

    if process is not None:
        # Index: primary name/ascii → row indices (dedupe later by display)
        choices: dict[str, int] = {}
        for i, row in enumerate(rows):
            for key in (row.get("ascii"), row.get("name")):
                k = _normalize(key or "")
                if k and k not in choices:
                    choices[k] = i
            for alt in (row.get("alts") or [])[:4]:
                k = _normalize(alt)
                if k and k not in choices:
                    choices[k] = i
        # Also try "name admin1"
        for i, row in enumerate(rows):
            admin = _normalize(row.get("admin1") or "")
            name = _normalize(row.get("ascii") or row.get("name") or "")
            if name and admin:
                combo = f"{name} {admin}"
                if combo not in choices:
                    choices[combo] = i

        raw_hits = process.extract(
            q, list(choices.keys()), scorer=fuzz.WRatio, limit=40
        )
        seen_idx: set[int] = set()
        for match_key, score, _ in raw_hits:
            idx = choices.get(match_key)
            if idx is None or idx in seen_idx:
                continue
            seen_idx.add(idx)
            row = rows[idx]
            sc = float(score)
            if bias and row.get("cc") == bias:
                sc += 8.0
            hinted = _query_country_hint(query)
            if hinted and row.get("cc") != hinted:
                sc -= 15.0
            pop = int(row.get("pop") or 0)
            if pop > 1_000_000:
                sc += 3.0
            elif pop > 100_000:
                sc += 1.5
            if sc >= min_score:
                scored.append((sc, row))
    else:
        for row in rows:
            sc = _score_row(q, row, bias)
            if sc >= min_score:
                scored.append((sc, row))

    scored.sort(key=lambda x: (-x[0], -int(x[1].get("pop") or 0)))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sc, row in scored:
        key = (row.get("display") or row.get("name") or "").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "display": row.get("display") or row.get("name"),
                "name": row.get("name"),
                "admin1": row.get("admin1") or "",
                "country": row.get("country") or "",
                "cc": row.get("cc") or "",
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "score": round(sc, 1),
                "population": int(row.get("pop") or 0),
            }
        )
        if len(out) >= limit:
            break
    return out


def nominatim_fallback(query: str, *, bias_cc: str | None = None) -> list[dict[str, Any]]:
    """Last-resort network geocode for villages / misses. Returns 0–1 candidates."""
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="samara-by-clara", timeout=6)
        q = query.strip()
        loc = None
        if bias_cc == "IN":
            loc = geolocator.geocode(f"{q}, India")
        if loc is None:
            loc = geolocator.geocode(q)
        if not loc:
            return []
        raw = loc.raw or {}
        addr = raw.get("address") or {}
        display = loc.address or q
        # Prefer compact display
        city = addr.get("city") or addr.get("town") or addr.get("village") or q
        state = addr.get("state") or ""
        country = addr.get("country") or ""
        parts = [p for p in (city, state, country) if p]
        return [
            {
                "display": ", ".join(parts) if parts else display,
                "name": city,
                "admin1": state,
                "country": country,
                "cc": (addr.get("country_code") or "").upper(),
                "lat": float(loc.latitude),
                "lon": float(loc.longitude),
                "score": 60.0,
                "population": 0,
            }
        ]
    except Exception as exc:
        logger.warning("Nominatim fallback failed", extra={"query": query, "error": str(exc)})
        return []


def resolve_place_candidates(
    query: str,
    *,
    phone_number: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Full resolve: offline fuzzy first, Nominatim if empty."""
    hits = search_places(query, phone_number=phone_number, limit=limit)
    if hits:
        return hits
    bias = _query_country_hint(query) or infer_country_iso(phone_number)
    return nominatim_fallback(query, bias_cc=bias)[:limit]
