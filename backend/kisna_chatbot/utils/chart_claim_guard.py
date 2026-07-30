"""Golden-rule guard: reading text must not invent chart facts.

THE RULE: every Lagna / rashi / nakshatra / planet / dasha claim in a reading
must already appear in the deterministic chart_json from compute_chart().
The LLM never calculates; this helper only audits interpretation text.
"""

from __future__ import annotations

import re
from typing import Any

# Canonical English / Hindi aliases the reading may use.
_SIGNS: tuple[tuple[str, ...], ...] = (
    ("aries", "mesha"),
    ("taurus", "vrishabha", "vrishabh"),
    ("gemini", "mithuna", "mithun"),
    ("cancer", "karka", "kark"),
    ("leo", "simha", "singh"),
    ("virgo", "kanya"),
    ("libra", "tula", "tul"),
    ("scorpio", "vrishchika", "vrischika"),
    ("sagittarius", "dhanu", "dhanush"),
    ("capricorn", "makara", "makar"),
    ("aquarius", "kumbha", "kumbh"),
    ("pisces", "meena", "meen"),
)

_PLANETS: tuple[tuple[str, ...], ...] = (
    ("sun", "surya"),
    ("moon", "chandra"),
    ("mars", "mangal", "mangala"),
    ("mercury", "budha", "budh"),
    ("jupiter", "guru", "brihaspati"),
    ("venus", "shukra"),
    ("saturn", "shani"),
    ("rahu",),
    ("ketu",),
)

_NAKSHATRAS: tuple[tuple[str, ...], ...] = (
    ("ashwini", "aswini"),
    ("bharani",),
    ("krittika", "kritika"),
    ("rohini",),
    ("mrigashira", "mrigashirsha", "mrigasira"),
    ("ardra",),
    ("punarvasu",),
    ("pushya", "pushyami"),
    ("ashlesha", "aslesha"),
    ("magha", "magh"),
    ("purva phalguni", "poorva phalguni", "purvaphalguni"),
    ("uttara phalguni", "uttaraphalguni"),
    ("hasta",),
    ("chitra", "chithira"),
    ("swati", "swathi"),
    ("vishakha", "visakha"),
    ("anuradha",),
    ("jyeshtha", "jyestha"),
    ("mula", "moola"),
    ("purva ashadha", "poorva ashadha", "purvashadha"),
    ("uttara ashadha", "uttarashadha"),
    ("shravana", "sravana"),
    ("dhanishta", "dhanishtha"),
    ("shatabhisha", "satabhisha", "shatabhisa"),
    ("purva bhadrapada", "poorva bhadrapada", "purvabhadrapada"),
    ("uttara bhadrapada", "uttarabhadrapada"),
    ("revati",),
)

# Word-boundary-ish match; multi-word nakshatras handled via longer aliases first.
_WORD = r"(?<![a-zA-Z]){0}(?![a-zA-Z])"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _canonical_from_aliases(raw: str, groups: tuple[tuple[str, ...], ...]) -> str | None:
    n = _norm(raw)
    if not n:
        return None
    for group in groups:
        if n in group or n == group[0]:
            return group[0]
    return None


def _find_mentions(text: str, groups: tuple[tuple[str, ...], ...]) -> set[str]:
    """Return canonical names mentioned in text (longest alias first per group)."""
    lowered = text or ""
    found: set[str] = set()
    # Sort aliases longest-first so "purva phalguni" beats "phalguni"-style partials.
    candidates: list[tuple[str, str]] = []
    for group in groups:
        canon = group[0]
        for alias in sorted(group, key=len, reverse=True):
            candidates.append((alias, canon))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    matched_spans: list[tuple[int, int]] = []
    for alias, canon in candidates:
        pattern = re.compile(_WORD.format(re.escape(alias)), re.IGNORECASE)
        for m in pattern.finditer(lowered):
            span = (m.start(), m.end())
            if any(span[0] < e and span[1] > s for s, e in matched_spans):
                continue
            matched_spans.append(span)
            found.add(canon)
    return found


def allowed_chart_facts(chart_json: dict[str, Any]) -> dict[str, set[str]]:
    """Build the set of signs / nakshatras / planets / dasha lords present in chart_json."""
    signs: set[str] = set()
    nakshatras: set[str] = set()
    planets: set[str] = set()
    dasha_lords: set[str] = set()

    def add_sign(obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        for key in ("sign_en", "sign_hi"):
            c = _canonical_from_aliases(str(obj.get(key) or ""), _SIGNS)
            if c:
                signs.add(c)

    lagna = chart_json.get("lagna")
    if lagna:
        add_sign(lagna)
    add_sign(chart_json.get("rashi") or {})
    add_sign(chart_json.get("surya_rashi") or {})

    nak = chart_json.get("nakshatra") or {}
    if isinstance(nak, dict):
        c = _canonical_from_aliases(str(nak.get("name") or ""), _NAKSHATRAS)
        if c:
            nakshatras.add(c)

    planets_map = chart_json.get("planets") or {}
    if isinstance(planets_map, dict):
        for name, pos in planets_map.items():
            pc = _canonical_from_aliases(str(name), _PLANETS)
            if pc:
                planets.add(pc)
            if isinstance(pos, dict):
                add_sign(pos)
                hc = _canonical_from_aliases(str(pos.get("name_hi") or ""), _PLANETS)
                if hc:
                    planets.add(hc)

    for period in chart_json.get("dasha_timeline") or []:
        if not isinstance(period, dict):
            continue
        for key in ("planet_en", "planet_hi"):
            pc = _canonical_from_aliases(str(period.get(key) or ""), _PLANETS)
            if pc:
                dasha_lords.add(pc)
                planets.add(pc)

    return {
        "signs": signs,
        "nakshatras": nakshatras,
        "planets": planets,
        "dasha_lords": dasha_lords,
    }


def extract_chart_claims(reading_text: str) -> dict[str, set[str]]:
    """Extract sign / nakshatra / planet mentions from reading prose."""
    return {
        "signs": _find_mentions(reading_text, _SIGNS),
        "nakshatras": _find_mentions(reading_text, _NAKSHATRAS),
        "planets": _find_mentions(reading_text, _PLANETS),
        # Dasha lords are planet names in prose; same extraction set.
        "dasha_lords": _find_mentions(reading_text, _PLANETS),
    }


class ChartClaimViolation(ValueError):
    """Raised when reading text invents a chart fact absent from chart_json."""

    def __init__(self, invented: dict[str, set[str]]):
        self.invented = invented
        parts = []
        for kind, values in invented.items():
            if values:
                parts.append(f"{kind}={sorted(values)}")
        super().__init__(
            "Reading invents chart facts not in chart_json: " + "; ".join(parts)
        )


def assert_reading_respects_chart(
    chart_json: dict[str, Any], reading_text: str
) -> None:
    """Assert every astrology claim in reading_text is present in chart_json.

    Raises ChartClaimViolation listing invented facts.
    """
    allowed = allowed_chart_facts(chart_json)
    claimed = extract_chart_claims(reading_text)

    invented: dict[str, set[str]] = {}
    for kind in ("signs", "nakshatras", "planets"):
        extra = claimed[kind] - allowed[kind]
        # Planets that only appear as dasha lords are still "in chart" via dasha.
        if kind == "planets":
            extra -= allowed["dasha_lords"]
        if extra:
            invented[kind] = extra

    # Dasha-lord claims that aren't in timeline (and not otherwise on chart planets)
    # are also violations when the prose clearly names a dasha planet — we treat
    # planet mentions already covered above; keep dasha check as planets ⊆ allowed.
    if invented:
        raise ChartClaimViolation(invented)
