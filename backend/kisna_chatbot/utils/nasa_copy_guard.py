"""Outbound lint for NASA data-lineage phrasing.

Allowed: factual DATA lineage ("the same planetary data NASA uses…").
Forbidden: any implication that NASA endorses, partners with, certifies,
or backs Samara.

NOTE (Meta ads): In-chat data-lineage phrasing is fine. For META AD creative
(separate from WhatsApp), the NASA reference must be even more conservative —
ad review is stricter. Do NOT reuse the in-chat lineage line verbatim in ad
creative without legal/brand review.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Exact approved phrasing for the data reference (Task 1).
APPROVED_NASA_LINEAGE = (
    "powered by the same planetary data NASA uses to track the solar system"
)

# Endorsement / partnership / certification claims — never ship these.
_ENDORSEMENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bbacked\s+by\s+NASA\b",
        r"\bNASA[-\s]?powered\b",
        r"\bin\s+partnership\s+with\s+NASA\b",
        r"\bNASA[-\s]?certified\b",
        r"\bNASA\s+endorses?\b",
        r"\bNASA[-\s]?approved\b",
        r"\bNASA\s+partner(?:ship)?\b",
        r"\bNASA\s+backed\b",
        r"\bNASA\s+ke\s+saath\s+partnership\b",
        r"\bNASA\s+dwaara\s+certified\b",
        r"\bNASA\s+se\s+backed\b",
        r"\bNASA[-\s]?backed\b",
    )
)


def has_nasa_endorsement(text: str | None) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _ENDORSEMENT_PATTERNS)


def sanitize_nasa_endorsement(text: str | None) -> tuple[str, bool]:
    """Strip endorsement phrasing; fall back to the approved lineage line.

    Returns (clean_text, violated).
    """
    if not text:
        return "", False
    if not has_nasa_endorsement(text):
        return text, False

    cleaned = text
    for pattern in _ENDORSEMENT_PATTERNS:
        cleaned = pattern.sub(APPROVED_NASA_LINEAGE, cleaned)

    # Collapse accidental double inserts of the approved line.
    doubled = re.compile(
        re.escape(APPROVED_NASA_LINEAGE) + r"(?:\s*,?\s*" + re.escape(APPROVED_NASA_LINEAGE) + r")+",
        re.IGNORECASE,
    )
    cleaned = doubled.sub(APPROVED_NASA_LINEAGE, cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if APPROVED_NASA_LINEAGE.lower() not in cleaned.lower() and has_nasa_endorsement(cleaned):
        cleaned = f"{cleaned.rstrip('.')}. {APPROVED_NASA_LINEAGE}."

    # Final pass: if any endorsement residue remains, force-append approved line
    # after stripping residual NASA endorsement tokens we still recognise.
    if has_nasa_endorsement(cleaned):
        for pattern in _ENDORSEMENT_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
        if APPROVED_NASA_LINEAGE.lower() not in cleaned.lower():
            cleaned = f"{cleaned}. {APPROVED_NASA_LINEAGE}." if cleaned else APPROVED_NASA_LINEAGE

    logger.warning(
        "nasa_copy_guard: stripped endorsement phrasing from outbound copy"
    )
    return cleaned, True
