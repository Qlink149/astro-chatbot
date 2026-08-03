"""Pay-what-you-want amount parse + credit grant formula for Samara."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def min_payment_inr() -> float:
    raw = (os.getenv("SAMARA_MIN_PAYMENT_INR") or "39").strip()
    try:
        return float(raw)
    except ValueError:
        return 39.0


def max_payment_inr() -> float:
    raw = (os.getenv("SAMARA_MAX_PAYMENT_INR") or "5000").strip()
    try:
        return float(raw)
    except ValueError:
        return 5000.0


def rupees_per_credit() -> float:
    raw = (os.getenv("SAMARA_RUPEES_PER_CREDIT") or "4.0").strip()
    try:
        return float(raw) or 4.0
    except ValueError:
        return 4.0


def min_credits_grant() -> int:
    raw = (os.getenv("SAMARA_MIN_CREDITS_GRANT") or "10").strip()
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return 10


def credits_for_amount(amount_inr: float) -> int:
    """₹39 → 10, ₹99 → 25 (max of floor credits and round(amount / rate))."""
    rate = rupees_per_credit()
    raw = round(float(amount_inr) / rate) if rate > 0 else 0
    return max(min_credits_grant(), int(raw))


def parse_amount_inr(text: str) -> float | None:
    """Parse free-text amounts like ₹39, rs 50, ३९, 99.5. Returns None if unparseable."""
    if not text or not str(text).strip():
        return None
    t = str(text).strip().translate(_DEVANAGARI_DIGITS)
    t = t.replace(",", "").replace("\u20b9", " ").replace("₹", " ")
    t = re.sub(r"(?i)\b(rs\.?|inr|rupees?|rupaye|rupaya)\b", " ", t)
    t = t.strip()
    # Prefer first number (integer or decimal)
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if val <= 0:
        return None
    # Ignore absurd junk (e.g. phone numbers typed by mistake)
    if val > 1_000_000:
        return None
    return val


AmountVerdict = Literal["ok", "under_min", "needs_confirm", "unparseable"]


@dataclass(frozen=True)
class AmountCheck:
    verdict: AmountVerdict
    amount_inr: float | None = None
    credits: int | None = None


def check_amount(text: str) -> AmountCheck:
    amount = parse_amount_inr(text)
    if amount is None:
        return AmountCheck("unparseable")
    min_inr = min_payment_inr()
    max_inr = max_payment_inr()
    if amount + 1e-9 < min_inr:
        return AmountCheck("under_min", amount_inr=amount)
    if amount > max_inr + 1e-9:
        return AmountCheck(
            "needs_confirm",
            amount_inr=amount,
            credits=credits_for_amount(amount),
        )
    return AmountCheck(
        "ok",
        amount_inr=amount,
        credits=credits_for_amount(amount),
    )


def format_inr(amount: float) -> str:
    if float(amount).is_integer():
        return str(int(amount))
    return f"{amount:g}"
