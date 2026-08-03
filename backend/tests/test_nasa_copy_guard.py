"""NASA data-lineage phrasing: allow lineage, reject endorsement."""
from __future__ import annotations

import os

os.environ.setdefault("ENV_MODE", "dev")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt")
os.environ.setdefault("SYSTEM_API_KEY", "test-api")
os.environ.setdefault("KISNA_PRODUCT_API", "https://example.com/products")
os.environ.setdefault("GUPSHUP_APP_ID", "test-app-id")
os.environ.setdefault("GUPSHUP_TOKEN", "test-token")
os.environ.setdefault("GUPSHUP_APP_NAME", "test-app")
os.environ.setdefault("GUPSHUP_API_KEY", "test-api-key")

from kisna_chatbot.processors.samara_reading_agent import (
    GREETING_TEXT_EN,
    GREETING_TEXT_HI,
)
from kisna_chatbot.utils.nasa_copy_guard import (
    APPROVED_NASA_LINEAGE,
    has_nasa_endorsement,
    sanitize_nasa_endorsement,
)


def test_approved_lineage_constant():
    assert APPROVED_NASA_LINEAGE == (
        "powered by the same planetary data NASA uses to track the solar system"
    )


def test_greeting_contains_approved_lineage_not_endorsement():
    for sample in (GREETING_TEXT_EN, GREETING_TEXT_HI):
        assert APPROVED_NASA_LINEAGE in sample
        assert not has_nasa_endorsement(sample)
        assert "backed by NASA" not in sample.lower()
        assert "nasa-powered" not in sample.lower()
        assert "partnership with nasa" not in sample.lower()


def test_greeting_is_short():
    for sample in (GREETING_TEXT_EN, GREETING_TEXT_HI):
        lines = [ln for ln in sample.strip().split("\n") if ln.strip()]
        assert 1 <= len(lines) <= 3, sample
        assert APPROVED_NASA_LINEAGE in sample


def test_sanitize_replaces_backed_by_nasa():
    raw = "Samara is backed by NASA for accurate readings."
    clean, violated = sanitize_nasa_endorsement(raw)
    assert violated is True
    assert "backed by NASA" not in clean
    assert APPROVED_NASA_LINEAGE in clean
    assert not has_nasa_endorsement(clean)


def test_sanitize_replaces_nasa_powered_and_certified():
    for phrase in (
        "Our NASA-powered astrology",
        "NASA certified readings",
        "in partnership with NASA today",
        "NASA-approved kundli",
    ):
        clean, violated = sanitize_nasa_endorsement(phrase)
        assert violated is True
        assert not has_nasa_endorsement(clean)
        assert APPROVED_NASA_LINEAGE in clean


def test_sanitize_leaves_approved_lineage_alone():
    text = f"Welcome — {APPROVED_NASA_LINEAGE}."
    clean, violated = sanitize_nasa_endorsement(text)
    assert violated is False
    assert clean == text
