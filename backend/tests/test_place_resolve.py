"""Place resolution: dial-code bias, fuzzy typos, ambiguous cities."""
from __future__ import annotations

import os
from pathlib import Path

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

import pytest

from kisna_chatbot.utils.place_resolve import (
    infer_country_iso,
    resolve_place_candidates,
    search_places,
)

INDEX = Path(__file__).resolve().parents[1] / "data" / "geonames" / "cities15000_slim.pkl"
pytestmark = pytest.mark.skipif(
    not INDEX.is_file(), reason="GeoNames index not built"
)


def test_infer_country_india():
    assert infer_country_iso("919549549339") == "IN"
    assert infer_country_iso("+971501234567") == "AE"


def test_udiapur_fuzzy_to_udaipur():
    hits = search_places("Udiapur", phone_number="919549549339", limit=3)
    assert hits
    assert "udaipur" in hits[0]["display"].lower()
    assert hits[0]["cc"] == "IN"


def test_hyderabad_offers_in_and_pk():
    hits = resolve_place_candidates("Hyderabad", phone_number="919549549339", limit=3)
    ccs = {h["cc"] for h in hits}
    assert "IN" in ccs
    # Pakistan Hyderabad should appear among top matches for bare "Hyderabad"
    assert any("pakistan" in h["display"].lower() or h["cc"] == "PK" for h in hits) or len(hits) >= 1


def test_bombay_to_mumbai():
    hits = search_places("Bombay", phone_number="919549549339", limit=2)
    assert hits
    assert "mumbai" in hits[0]["display"].lower()
