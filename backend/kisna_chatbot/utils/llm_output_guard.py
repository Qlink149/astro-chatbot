"""Strip LLM planning / chain-of-thought that leaked into user-facing copy."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

# Common meta / planning openers models emit before the real reply.
_META_LINE_START = re.compile(
    r"^(?:"
    r"got it\.?|"
    r"okay\.?|"
    r"sure\.?|"
    r"the user (?:confirmed|said|tapped|selected|chose)|"
    r"i(?:'ll| will) (?:invite|keep|ask|respond|write|acknowledge)|"
    r"i need to|"
    r"let me |"
    r"here(?:'s| is) (?:my |the )?(?:plan|approach|thinking)|"
    r"thinking:|"
    r"internal(?:ly)?:|"
    r"note to self|"
    r"instructions?:|"
    r"task:"
    r").*",
    re.IGNORECASE,
)

_SEPARATOR = re.compile(r"^\s*-{3,}\s*$")


def strip_llm_meta(text: str | None) -> str:
    """Drop planning/thinking blocks; keep the user-facing reply.

    Handles:
    - Content before a --- separator (common CoT leak pattern)
    - Leading meta lines ("The user confirmed…", "I'll invite…")
    """
    if not text:
        return ""
    raw = text.replace("\r\n", "\n").strip()
    if not raw:
        return ""

    # Prefer content after the last --- separator if both sides have substance.
    parts = re.split(r"\n\s*-{3,}\s*\n", raw)
    if len(parts) >= 2:
        after = parts[-1].strip()
        before = "\n\n".join(p.strip() for p in parts[:-1] if p.strip())
        # If after looks like real reply, use it; else fall through to line filter.
        if after and len(after) >= 12:
            raw = after

    lines = raw.split("\n")
    kept: list[str] = []
    skipping_meta = True
    for line in lines:
        stripped = line.strip()
        if skipping_meta:
            if not stripped:
                continue
            if _SEPARATOR.match(stripped):
                continue
            if _META_LINE_START.match(stripped):
                continue
            skipping_meta = False
        kept.append(line)

    out = "\n".join(kept).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out or raw


def enforce_language_script(
    text: str | None,
    lang: str,
    *,
    fallback: str = "",
) -> str:
    """English mode must never ship Devanagari; Hindi may mix Roman."""
    raw = (text or "").strip()
    if not raw or lang == "hindi":
        return raw
    if not _DEVANAGARI.search(raw):
        return raw
    if fallback:
        logger.warning(
            "Devanagari in English LLM output — using fallback",
            extra={"preview": raw[:120]},
        )
        return fallback.strip()
    kept = [line for line in raw.split("\n") if not _DEVANAGARI.search(line)]
    cleaned = "\n".join(kept).strip()
    if cleaned:
        logger.warning(
            "Devanagari stripped from English LLM output",
            extra={"preview": raw[:120]},
        )
        return cleaned
    return fallback.strip() if fallback else raw
