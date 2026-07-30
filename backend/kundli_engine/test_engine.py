"""
Proof tests for the kundli engine.
Run: python3 test_engine.py
These verify (a) correctness against a documented chart, and
(b) that the no-birth-time fallback behaves honestly.
"""
import json
from engine import compute_chart, BirthDetails


def show(title, chart):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    print(json.dumps(chart, indent=2, ensure_ascii=False))


def test_with_time():
    # Mahatma Gandhi — 2 Oct 1869, ~07:11, Porbandar.
    # Documented: Kanya (Virgo) Lagna, Karka (Cancer) Rashi/Moon.
    b = BirthDetails(
        year=1869, month=10, day=2, hour=7, minute=11,
        latitude=21.6417, longitude=69.6293, timezone_offset=5.5,
        place_name="Porbandar",
    )
    chart = compute_chart(b)
    show("TEST 1 — full chart (birth time known)", chart)
    assert chart["meta"]["has_birth_time"] is True
    assert chart["meta"]["birth_year"] == 1869
    assert isinstance(chart["meta"]["current_age"], int)
    assert chart["lagna"]["sign_en"] == "Virgo", chart["lagna"]
    assert chart["rashi"]["sign_en"] == "Cancer", chart["rashi"]
    assert len(chart["dasha_timeline"]) == 9
    for period in chart["dasha_timeline"]:
        assert "age_start" in period and "age_end" in period
        assert "starts_before_birth" in period and "is_relevant" in period
        assert isinstance(period["starts_before_birth"], bool)
        assert isinstance(period["is_relevant"], bool)
    assert "houses" in chart
    assert chart["houses"]["system"] == "whole_sign"
    assert "1" in chart["houses"]["bhavas"]
    assert "planet_houses" in chart["houses"]
    print("\n[PASS] Lagna=Virgo, Rashi=Cancer, 9 dasha periods — matches documented chart.")


def test_without_time():
    b = BirthDetails(
        year=1990, month=5, day=15,
        latitude=24.5854, longitude=73.7125,  # Udaipur
        timezone_offset=5.5, place_name="Udaipur",
    )
    chart = compute_chart(b)
    show("TEST 2 — fallback (no birth time)", chart)
    assert chart["meta"]["has_birth_time"] is False
    assert chart["meta"]["chart_type"] == "surya_kundli"
    assert chart["lagna"] is None
    assert "houses" not in chart, "houses must be absent when birth time unknown"
    assert chart["meta"]["note_if_no_time"] is not None
    assert chart["surya_rashi"]["sign_en"] is not None
    print("\n[PASS] No time -> Lagna omitted, houses absent, surya_kundli, honest note present.")


if __name__ == "__main__":
    test_with_time()
    test_without_time()
    print("\nALL TESTS PASSED ✅")
