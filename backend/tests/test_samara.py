"""End-to-end tests for Samara (Clara) client — webhook, chart, follow-ups, dashboard APIs.

Paywall is OFF in the live agent; follow-up tests assert ungated answers.
"""
import json
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://clara-astro.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "test_database")

ADMIN_USER = "Yogansh@claraai.tech"
ADMIN_PASS = "riteshseema"
PHONE_ID = "919549549339"


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def token():
    r = requests.post(
        f"{API}/system/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("success") is True
    assert j.get("token")
    return j["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _text_webhook(phone: str, body: str = "Hi") -> dict:
    wamid = f"wamid.TEST_{uuid.uuid4().hex}"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": PHONE_ID, "display_phone_number": PHONE_ID},
                            "contacts": [{"wa_id": phone, "profile": {"name": "Test User"}}],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": wamid,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def _flow_webhook(phone: str, flow: dict) -> dict:
    wamid = f"wamid.TEST_{uuid.uuid4().hex}"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": PHONE_ID, "display_phone_number": PHONE_ID},
                            "contacts": [{"wa_id": phone, "profile": {"name": "Test User"}}],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": wamid,
                                    "timestamp": str(int(time.time())),
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "nfm_reply",
                                        "nfm_reply": {
                                            "name": "flow",
                                            "body": "Sent",
                                            "response_json": json.dumps(flow),
                                        },
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def _wait_for(cond, timeout=30, interval=1.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = cond()
        if last:
            return last
        time.sleep(interval)
    return last


def _post_webhook(payload):
    r = requests.post(f"{API}/gupshup/message/samara", json=payload, timeout=15)
    return r


# ─── Test 1: Text greeting creates samara profile with birth_details flow ─────
class TestGreeting:
    def test_greeting_creates_samara_profile(self, mongo):
        phone = "919876500010"
        mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})
        r = _post_webhook(_text_webhook(phone, "Hi"))
        assert r.status_code == 200
        assert r.json().get("success") is True

        def check():
            u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
            if not u:
                return None
            ch = u.get("chat_history") or []
            joined = json.dumps(ch, ensure_ascii=False)
            if "Namaste" in joined and "Sent flow - [birth_details]" in joined:
                return u
            return None

        u = _wait_for(check, timeout=25)
        assert u is not None, "samara user not created / greeting missing"
        assert u.get("client_id") == "samara"


# ─── Test 2: Full chart from nfm_reply ────────────────────────────────────────
class TestFullChart:
    def test_full_chart_with_time(self, mongo):
        phone = "919876500011"
        mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})
        # Seed conversation first
        _post_webhook(_text_webhook(phone, "Hi"))
        time.sleep(6)

        flow = {
            "flow_token": f"samara_birth${int(time.time())}",
            "flow_kind": "birth_details",
            "birth_date": "1990-05-15",
            "birth_time": "07:25",
            "unknown_time": False,
            "birth_place": "Jaipur",
        }
        r = _post_webhook(_flow_webhook(phone, flow))
        assert r.status_code == 200

        def check():
            u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
            if not u:
                return None
            chart = u.get("chart_json")
            if not chart:
                return None
            if not u.get("free_reading_used"):
                return None
            return u

        u = _wait_for(check, timeout=45, interval=2)
        assert u is not None, "chart not computed / free reading not delivered"
        chart = u["chart_json"]
        meta = chart.get("meta") or {}
        assert meta.get("chart_type") == "full", f"chart_type={meta.get('chart_type')}"
        assert chart.get("lagna"), "lagna missing"
        assert chart.get("rashi") or chart.get("moon", {}).get("rashi"), "rashi missing"
        assert chart.get("nakshatra") or chart.get("moon", {}).get("nakshatra"), "nakshatra missing"
        dasha = chart.get("dasha_timeline") or []
        assert len(dasha) == 9, f"dasha_timeline len={len(dasha)}"
        assert u.get("birth_details", {}).get("date_of_birth") == "1990-05-15"
        # LLM reading present
        ch = u.get("chat_history") or []
        assert any(m.get("role") == "assistant" and len(str(m.get("content") or "")) > 200 for m in ch), "no long reading in chat_history"


# ─── Test 3: Unknown time → surya_kundli ─────────────────────────────────────
class TestNoBirthTime:
    def test_unknown_time_produces_surya_kundli(self, mongo):
        phone = "919876500012"
        mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})
        _post_webhook(_text_webhook(phone, "Hi"))
        time.sleep(5)

        flow = {
            "flow_token": f"samara_birth${int(time.time())}",
            "flow_kind": "birth_details",
            "birth_date": "1988-11-02",
            "birth_time": "",
            "unknown_time": True,
            "birth_place": "Mumbai",
        }
        _post_webhook(_flow_webhook(phone, flow))

        def check():
            u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
            if u and u.get("chart_json"):
                return u
            return None

        u = _wait_for(check, timeout=45, interval=2)
        assert u is not None
        chart = u["chart_json"]
        assert chart["meta"]["chart_type"] == "surya_kundli"
        assert chart.get("lagna") is None, f"lagna should be None, got {chart.get('lagna')}"


# ─── Test 4: Follow-ups ungated (paywall OFF until Phase 2) ──────────────────
class TestPaywallAndFollowup:
    def test_followup_not_paywalled_when_credits_zero(self, mongo):
        """Paywall is intentionally OFF. Zero credits must still get a real answer."""
        phone = "919876500013"
        mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})
        _post_webhook(_text_webhook(phone, "Hi"))
        time.sleep(5)
        flow = {
            "flow_token": f"samara_birth${int(time.time())}",
            "flow_kind": "birth_details",
            "birth_date": "1992-03-10",
            "birth_time": "10:15",
            "unknown_time": False,
            "birth_place": "Delhi",
        }
        _post_webhook(_flow_webhook(phone, flow))

        u = _wait_for(
            lambda: mongo.users.find_one({"phone_number": phone, "client_id": "samara", "free_reading_used": True}),
            timeout=45, interval=2,
        )
        assert u is not None, "free reading did not complete"

        mongo.users.update_one(
            {"_id": u["_id"]},
            {"$set": {"credits": 0, "followup_questions_asked": 0}},
        )
        _post_webhook(_text_webhook(phone, "Career kaisa rahega?"))

        def followup_check():
            u2 = mongo.users.find_one({"_id": u["_id"]})
            if int(u2.get("followup_questions_asked") or 0) < 1:
                return None
            ch = u2.get("chat_history") or []
            last_bots = [
                str(m.get("content") or "")
                for m in ch[-4:]
                if m.get("role") == "assistant"
            ]
            joined = " ".join(last_bots).lower()
            # Must NOT be the dead paywall / "coming soon" copy
            if "coming soon" in joined:
                return None
            if "₹49" in joined and "credits chahiye" in joined:
                return None
            if last_bots:
                return u2
            return None

        u_fu = _wait_for(followup_check, timeout=45, interval=2)
        assert u_fu is not None, "follow-up answer not observed (paywall should be OFF)"
        # Credits must not be decremented while paywall is off
        assert int(u_fu.get("credits") or 0) == 0


# ─── Test 5: Geocode failure ─────────────────────────────────────────────────
class TestGeocodeFailure:
    def test_bad_place_returns_geocode_fail(self, mongo):
        phone = "919876500014"
        mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})
        _post_webhook(_text_webhook(phone, "Hi"))
        time.sleep(5)
        flow = {
            "flow_token": f"samara_birth${int(time.time())}",
            "flow_kind": "birth_details",
            "birth_date": "1991-01-01",
            "birth_time": "05:30",
            "unknown_time": False,
            "birth_place": "Xyzzyville Nowhere",
        }
        _post_webhook(_flow_webhook(phone, flow))

        def check():
            u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
            if not u:
                return None
            ch = u.get("chat_history") or []
            joined = " ".join(str(m.get("content") or "") for m in ch[-4:] if m.get("role") == "assistant")
            if "nahi mili" in joined or "nearby" in joined.lower() or "bade sheher" in joined:
                return u
            return None

        u = _wait_for(check, timeout=20, interval=1.5)
        assert u is not None, "geocode failure message not observed"
        assert not u.get("chart_json"), "chart should not be stored on geocode failure"


# ─── Test 6: Dashboard APIs ──────────────────────────────────────────────────
class TestDashboardAPIs:
    def test_login(self, token):
        assert isinstance(token, str) and len(token) > 20

    def test_dashboard_stats(self, auth_headers):
        r = requests.get(f"{API}/system/dashboard/stats", params={"client_id": "samara"}, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # tolerate either flat or nested "data"
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        keys = set(payload.keys())
        assert "total_readings" in keys, f"total_readings missing in {keys}"
        assert "total_followup_questions" in keys, f"total_followup_questions missing in {keys}"

    def test_list_users(self, auth_headers):
        r = requests.get(f"{API}/system/user", params={"client_id": "samara", "page": 1, "limit": 20}, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        # find array of users
        users = None
        for v in [j.get("results"), j.get("users"), j.get("data"), j]:
            if isinstance(v, list):
                users = v
                break
            if isinstance(v, dict) and isinstance(v.get("users"), list):
                users = v["users"]
                break
        assert users is not None, f"cannot find users list in {list(j.keys())}"
        assert len(users) >= 1

    def test_user_detail(self, auth_headers):
        # Use the pre-seeded user 919876500001
        r = requests.get(f"{API}/system/user/919876500001", params={"client_id": "samara"}, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        payload = j.get("data") if isinstance(j.get("data"), dict) else j
        # look at user object
        user = payload.get("user") if isinstance(payload.get("user"), dict) else payload
        assert "chart_json" in user or "chart_json" in payload, "chart_json missing"
        assert "birth_details" in user or "birth_details" in payload, "birth_details missing"
        assert "credits" in user or "credits" in payload, "credits missing"
        assert "free_reading_used" in user or "free_reading_used" in payload, "free_reading_used missing"
