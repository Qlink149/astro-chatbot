"""Place → coordinates for birth charts.

Preferred path: kisna_chatbot.utils.place_resolve (GeoNames offline + fuzzy).
This module keeps timezone_offset_for and a thin geocode_place wrapper for
legacy callers that only need (lat, lon).
"""

from datetime import datetime
from functools import lru_cache

from kisna_chatbot.utils.logger_config import logger


@lru_cache(maxsize=1)
def _get_tz_finder():
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


def geocode_place(place: str, *, phone_number: str | None = None) -> tuple[float, float] | None:
    """Resolve a place name to (lat, lon). Uses offline GeoNames then Nominatim."""
    from kisna_chatbot.utils.place_resolve import resolve_place_candidates

    hits = resolve_place_candidates(place, phone_number=phone_number, limit=1)
    if hits:
        return (float(hits[0]["lat"]), float(hits[0]["lon"]))
    return None


def timezone_offset_for(lat: float, lon: float, year: int, month: int, day: int) -> float:
    """UTC offset (hours) at birth place/date. Defaults to IST 5.5 on failure."""
    try:
        import pytz

        tz_name = _get_tz_finder().timezone_at(lat=lat, lng=lon)
        if tz_name:
            dt = pytz.timezone(tz_name).localize(datetime(year, month, day, 12, 0))
            return dt.utcoffset().total_seconds() / 3600.0
    except Exception as e:
        logger.warning("Timezone lookup failed", extra={"lat": lat, "lon": lon, "error": str(e)})
    return 5.5
