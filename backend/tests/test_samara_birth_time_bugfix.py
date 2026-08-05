"""Tests for the birth-time manual-input bug fix in Samara Flow.

Coverage:
  * _parse_birth_time — new manual TextInput + AM/PM payload
  * 12-hour → 24-hour conversion edge cases (12 AM=0, 12 PM=12, 3 PM=15 etc.)
  * Invalid inputs → None
  * unknown_time OptIn escape
  * Legacy Dropdown (birth_hour/birth_minute) and single-string birth_time backwards compatibility
  * End-to-end SamaraReadingAgent flow with new payload (mocked complete_chat, real compute_chart)
  * birth_details.json Flow JSON schema
  * POST /api/system/user/{phone}/reset endpoint (auth, 404, wipe)
"""

# Env bootstrap must come before importing the samara agent (see test_samara_v3_flow.py).
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

from kisna_chatbot.main import app  # noqa: F401  (pre-bootstraps module graph)

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import requests

import kisna_chatbot.processors.samara_reading_agent as mod


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://clara-astro.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"


def _run(coro):
    return asyncio.run(coro)


# ── _parse_birth_time: 12h → 24h conversion ──────────────────────────────────

class TestParseBirthTimeManual:
    """New manual TextInput + AM/PM payload."""

    def test_7_32_am_maps_to_7_32(self):
        # The reported bug — non-quarter-hour minute must survive.
        assert mod._parse_birth_time({
            "birth_hour_input": "7",
            "birth_minute_input": "32",
            "birth_ampm": "AM",
        }) == (7, 32)

    def test_3_47_pm_maps_to_15_47(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "3",
            "birth_minute_input": "47",
            "birth_ampm": "PM",
        }) == (15, 47)

    def test_12_00_am_maps_to_0_0_midnight(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "12",
            "birth_minute_input": "0",
            "birth_ampm": "AM",
        }) == (0, 0)

    def test_12_15_pm_maps_to_12_15_noon(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "12",
            "birth_minute_input": "15",
            "birth_ampm": "PM",
        }) == (12, 15)

    def test_11_59_pm_maps_to_23_59(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "11",
            "birth_minute_input": "59",
            "birth_ampm": "PM",
        }) == (23, 59)

    def test_1_00_am_maps_to_1_0(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "1",
            "birth_minute_input": "0",
            "birth_ampm": "AM",
        }) == (1, 0)

    def test_ampm_lowercase_is_normalised(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "8",
            "birth_minute_input": "5",
            "birth_ampm": "am",
        }) == (8, 5)


class TestParseBirthTimeInvalid:
    """Invalid manual-input payloads must return None (no fake time)."""

    def test_missing_ampm(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "7",
            "birth_minute_input": "32",
            "birth_ampm": "",
        }) is None

    def test_hour_greater_than_12(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "13",
            "birth_minute_input": "0",
            "birth_ampm": "PM",
        }) is None

    def test_hour_zero(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "0",
            "birth_minute_input": "5",
            "birth_ampm": "AM",
        }) is None

    def test_minute_over_59(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "7",
            "birth_minute_input": "60",
            "birth_ampm": "AM",
        }) is None

    def test_non_numeric_hour(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "seven",
            "birth_minute_input": "32",
            "birth_ampm": "AM",
        }) is None

    def test_non_numeric_minute(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "7",
            "birth_minute_input": "thirty",
            "birth_ampm": "AM",
        }) is None

    def test_blank_strings(self):
        assert mod._parse_birth_time({
            "birth_hour_input": "",
            "birth_minute_input": "",
            "birth_ampm": "",
        }) is None

    def test_empty_dict(self):
        assert mod._parse_birth_time({}) is None


class TestUnknownTimeEscape:
    """OptIn 'unknown_time' restores the honest no-time / surya_kundli path.

    When the user checks 'I don't know', parser returns None even if hour
    fields were also filled (OptIn wins). Empty OptIn list does not block
    a filled clock time.
    """

    def test_unknown_true_short_circuits(self):
        assert mod._parse_birth_time({
            "unknown_time": True,
            "birth_hour_input": "7",
            "birth_minute_input": "32",
            "birth_ampm": "AM",
        }) is None

    def test_unknown_string_true_short_circuits(self):
        assert mod._parse_birth_time({
            "unknown_time": "true",
            "birth_hour_input": "7",
            "birth_minute_input": "32",
            "birth_ampm": "AM",
        }) is None

    def test_unknown_list_form_short_circuits(self):
        assert mod._parse_birth_time({
            "unknown_time": ["unknown_time"],
            "birth_hour_input": "7",
            "birth_minute_input": "32",
            "birth_ampm": "AM",
        }) is None

    def test_unknown_empty_list_does_not_block(self):
        assert mod._parse_birth_time({
            "unknown_time": [],
            "birth_hour_input": "7",
            "birth_minute_input": "32",
            "birth_ampm": "AM",
        }) == (7, 32)

    def test_unknown_alone_returns_none(self):
        assert mod._parse_birth_time({"unknown_time": True}) is None


class TestLegacyPayloads:
    """Older Flow schemas still parse."""

    def test_legacy_24h_dropdowns(self):
        assert mod._parse_birth_time({
            "birth_hour": "15",
            "birth_minute": "30",
        }) == (15, 30)

    def test_legacy_single_birth_time_hhmm(self):
        assert mod._parse_birth_time({"birth_time": "07:25"}) == (7, 25)

    def test_legacy_birth_time_unknown_word(self):
        assert mod._parse_birth_time({"birth_time": "unknown"}) is None


# ── End-to-end SamaraReadingAgent.process() ─────────────────────────────────

def _flow_reply(payload: dict) -> dict:
    return {
        "type": "interactive",
        "interactive": {
            "nfm_reply": {"response_json": json.dumps(payload)},
        },
    }


class TestEndToEndFlow:
    """Full agent flow: new payload → chart → language buttons."""

    def test_new_payload_7_32_am_computes_chart_and_asks_language(self):
        async def go():
            agent = mod.SamaraReadingAgent()
            profile = {"username": "Rahul", "chat_history": []}
            data = {
                "client_id": "samara",
                "phone_number": "919999900010",
                "user_profile": profile,
                "messages": _flow_reply({
                    "flow_kind": "birth_details",
                    "birth_date": "1990-05-15",
                    "birth_hour_input": "7",
                    "birth_minute_input": "32",
                    "birth_ampm": "AM",
                    "unknown_time": [],
                    "birth_place": "jaipur",
                }),
            }
            with (
                patch(
                    "kisna_chatbot.processors.samara_reading_agent.resolve_place_candidates",
                    return_value=[{
                        "display": "Jaipur, Rajasthan, India",
                        "name": "Jaipur",
                        "admin1": "Rajasthan",
                        "country": "India",
                        "cc": "IN",
                        "lat": 26.9124,
                        "lon": 75.7873,
                        "score": 100,
                        "population": 3000000,
                    }],
                ),
                patch.object(mod, "timezone_offset_for", return_value=5.5),
            ):
                out = await agent.process(data)

            # Unambiguous place → no confirmation round-trip; chart straight away.
            chart = profile["chart_json"]
            assert chart is not None
            assert chart["meta"]["has_birth_time"] is True
            assert chart["meta"]["birth_time"] == "07:32"
            resp = out["bot_response"]
            assert len(resp) == 1
            assert resp[0]["type"] == "quickreply"
            ids = [o["postbackText"] for o in resp[0]["options"]]
            assert "samara_lang_en" in ids
            assert "samara_lang_hi" in ids
            # The resolved place is echoed so a wrong city is still visible.
            assert "Jaipur" in resp[0]["text"]
            assert "start over" in resp[0]["text"].lower()

        _run(go())

    def test_ambiguous_place_still_asks_before_computing(self):
        """Auto-confirm is only for a clear winner — ties must still be asked."""
        async def go():
            agent = mod.SamaraReadingAgent()
            profile = {"username": "Rahul", "chat_history": []}
            data = {
                "client_id": "samara",
                "phone_number": "919999900012",
                "user_profile": profile,
                "messages": _flow_reply({
                    "flow_kind": "birth_details",
                    "birth_date": "1990-05-15",
                    "birth_hour_input": "7",
                    "birth_minute_input": "32",
                    "birth_ampm": "AM",
                    "unknown_time": [],
                    "birth_place": "springfield",
                }),
            }
            tie = [
                {
                    "display": "Springfield, Illinois, United States",
                    "name": "Springfield",
                    "admin1": "Illinois",
                    "country": "United States",
                    "lat": 39.8,
                    "lon": -89.6,
                    "score": 90,
                    "population": 110000,
                },
                {
                    "display": "Springfield, Missouri, United States",
                    "name": "Springfield",
                    "admin1": "Missouri",
                    "country": "United States",
                    "lat": 37.2,
                    "lon": -93.3,
                    "score": 89,
                    "population": 160000,
                },
            ]
            with patch(
                "kisna_chatbot.processors.samara_reading_agent.resolve_place_candidates",
                return_value=tie,
            ):
                out = await agent.process(data)
            assert profile.get("chart_json") is None
            assert profile.get("conversation_beat") == "awaiting_place_confirm"
            assert any(
                r.get("type") in ("quickreply", "list") for r in out["bot_response"]
            )

        _run(go())

    def test_missing_time_computes_surya_kundli(self):
        """Blank time (or OptIn) → honest surya_kundli, language ask, no Lagna."""
        async def go():
            agent = mod.SamaraReadingAgent()
            profile = {"username": "Aisha", "chat_history": []}
            data = {
                "client_id": "samara",
                "phone_number": "919999900011",
                "user_profile": profile,
                "messages": _flow_reply({
                    "flow_kind": "birth_details",
                    "birth_date": "1990-05-15",
                    "birth_hour_input": "",
                    "birth_minute_input": "",
                    "birth_ampm": "",
                    "unknown_time": True,
                    "birth_place": "jaipur",
                }),
            }
            with (
                patch(
                    "kisna_chatbot.processors.samara_reading_agent.resolve_place_candidates",
                    return_value=[{
                        "display": "Jaipur, Rajasthan, India",
                        "name": "Jaipur",
                        "admin1": "Rajasthan",
                        "country": "India",
                        "cc": "IN",
                        "lat": 26.9124,
                        "lon": 75.7873,
                        "score": 100,
                        "population": 3000000,
                    }],
                ),
                patch.object(mod, "timezone_offset_for", return_value=5.5),
            ):
                out = await agent.process(data)
            chart = profile.get("chart_json")
            assert chart is not None
            assert chart["meta"]["chart_type"] == "surya_kundli"
            assert chart["meta"]["has_birth_time"] is False
            assert chart.get("lagna") is None
            resp = out["bot_response"]
            assert resp[0]["type"] == "quickreply"
            ids = [o["postbackText"] for o in resp[0]["options"]]
            assert "samara_lang_en" in ids

        _run(go())


# ── birth_details.json schema ───────────────────────────────────────────────

class TestFlowJson:
    def test_flow_json_schema(self):
        candidates = (
            "/app/backend/json/birth_details.json",
            os.path.join(os.path.dirname(__file__), "..", "json", "birth_details.json"),
        )
        path = next((p for p in candidates if os.path.isfile(p)), None)
        assert path, "birth_details.json not found"
        with open(path, encoding="utf-8") as f:
            flow = json.load(f)
        assert flow["version"] == "7.0"
        screen = flow["screens"][0]
        form = screen["layout"]["children"][0]
        assert form["type"] == "Form"
        children = form["children"]

        by_name = {c.get("name"): c for c in children if "name" in c}

        # birth_date DatePicker, required
        assert by_name["birth_date"]["type"] == "DatePicker"
        assert by_name["birth_date"]["required"] is True

        # birth_hour_input TextInput number (optional — unknown time allowed)
        h = by_name["birth_hour_input"]
        assert h["type"] == "TextInput"
        assert h["input-type"] == "number"
        assert h["required"] is False

        # birth_minute_input TextInput number
        m = by_name["birth_minute_input"]
        assert m["type"] == "TextInput"
        assert m["input-type"] == "number"
        assert m["required"] is False

        # birth_ampm RadioButtonsGroup with AM & PM
        ampm = by_name["birth_ampm"]
        assert ampm["type"] == "RadioButtonsGroup"
        ampm_ids = {o["id"] for o in ampm["data-source"]}
        assert ampm_ids == {"AM", "PM"}
        assert ampm["required"] is False

        # unknown_time OptIn restored ("I don't know")
        ut = by_name["unknown_time"]
        assert ut["type"] == "OptIn"
        assert ut["required"] is False

        # birth_place free-text TextInput (worldwide — no city dropdown)
        bp = by_name["birth_place"]
        assert bp["type"] == "TextInput"
        assert bp["required"] is True
        assert bp.get("input-type") in ("text", None) or bp.get("input-type") == "text"
        assert "data-source" not in bp

        # Single place field only (no duplicate city/location)
        assert "city" not in by_name
        assert "location" not in by_name

        # Honesty copy about missing time
        sub = next(c for c in children if c.get("type") == "TextSubheading")
        assert "unknown" in sub["text"].lower() or "don't know" in sub["text"].lower()
        assert "Lagna" in sub["text"] or "ascendant" in sub["text"].lower()
        assert "free text" in sub["text"].lower() or "state" in sub["text"].lower()


# ── /api/system/user/{phone}/reset endpoint ─────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    resp = requests.post(
        f"{API}/system/auth/login",
        json={"username": "Yogansh@claraai.tech", "password": "riteshseema"},
        timeout=15,
    )
    if resp.status_code != 200:
        pytest.skip(f"admin login failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]


class TestResetEndpoint:
    def test_reset_requires_auth(self):
        resp = requests.post(
            f"{API}/system/user/919999900099/reset",
            params={"client_id": "samara"},
            timeout=10,
        )
        assert resp.status_code == 401

    def test_reset_unknown_phone_404(self, admin_token):
        resp = requests.post(
            f"{API}/system/user/919000000000/reset",
            params={"client_id": "samara"},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert resp.status_code == 404

    def test_reset_wipes_profile_fields(self, admin_token):
        # Seed a user directly in Mongo, then call reset, then verify wipe.
        from pymongo import MongoClient

        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("MONGO_DB_NAME", "test_database")
        client = MongoClient(mongo_url)
        db = client[db_name]

        phone = f"91999TEST{uuid.uuid4().hex[:6]}"
        try:
            db.users.insert_one({
                "phone_number": phone,
                "client_id": "samara",
                "chat_history": [{"role": "user", "content": "hi"}],
                "chart_json": {"meta": {"birth_year": 1990}},
                "birth_details": {"date_of_birth": "1990-05-15"},
                "free_reading_used": True,
                "credits": 5,
                "followup_questions_asked": 3,
                "user_language": "english",
            })

            resp = requests.post(
                f"{API}/system/user/{phone}/reset",
                params={"client_id": "samara"},
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=15,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "ok"
            assert body["phone_number"] == phone

            after = db.users.find_one({"phone_number": phone, "client_id": "samara"})
            assert after is not None
            assert after["chat_history"] == []
            assert after["chart_json"] is None
            assert after["birth_details"] is None
            assert after["free_reading_used"] is False
            assert after["credits"] == 0
            assert after["followup_questions_asked"] == 0
            assert after["user_language"] is None
        finally:
            db.users.delete_many({"phone_number": phone, "client_id": "samara"})
            client.close()
