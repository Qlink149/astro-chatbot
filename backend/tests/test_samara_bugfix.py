"""Bug-fix verification for Samara WhatsApp bot (Phase 1).

Verifies:
  1. External webhook reachability (preview URL)
  2. Real Gupshup Flow send (via backend logs + chat_history)
  3. Typed-text birth-details fallback (with time -> full chart)
  4. Typed-text fallback without time -> surya_kundli
  5. nfm_reply flow regression -> full chart + free reading
  6. Paywall after free reading
  7. Gupshup subscription registration
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://clara-astro.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "test_database")
PHONE_ID = os.environ.get("SAMARA_PHONE_NUMBER_ID", "919549549339")
BIRTH_FLOW_ID = os.environ.get("SAMARA_BIRTH_FLOW_ID", "1018626800813268")
EXPECTED_WEBHOOK_URL = "https://clara-astro.preview.emergentagent.com/api/gupshup/message/samara"
BACKEND_LOG = "/var/log/supervisor/backend.out.log"


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _text_webhook(phone: str, body: str = "Hi") -> dict:
    wamid = f"wamid.TESTBUG_{uuid.uuid4().hex}"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": PHONE_ID,
                                "display_phone_number": PHONE_ID,
                            },
                            "contacts": [
                                {"wa_id": phone, "profile": {"name": "Bugfix User"}}
                            ],
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
    wamid = f"wamid.TESTBUG_{uuid.uuid4().hex}"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": PHONE_ID,
                                "display_phone_number": PHONE_ID,
                            },
                            "contacts": [
                                {"wa_id": phone, "profile": {"name": "Bugfix User"}}
                            ],
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


def _post_webhook(payload: dict, url: str | None = None, timeout: int = 30):
    target = url or f"{API}/gupshup/message/samara"
    last_err = None
    for attempt in range(2):
        try:
            return requests.post(target, json=payload, timeout=timeout)
        except requests.RequestException as exc:  # network flake
            last_err = exc
            time.sleep(2)
    raise last_err  # type: ignore[misc]


def _wait_for(cond, timeout=45, interval=2):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = cond()
        if last:
            return last
        time.sleep(interval)
    return last


# ─── Test 1: External webhook reachability ────────────────────────────────────
def test_external_webhook_reachable():
    phone = "919876500030"
    r = _post_webhook(_text_webhook(phone, "Hi"), url=EXPECTED_WEBHOOK_URL, timeout=30)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    body = r.json()
    assert body.get("success") is True, f"unexpected body: {body}"


# ─── Test 2: Real Gupshup Flow send visible in logs + chat_history ────────────
def test_real_flow_send_accepted(mongo):
    phone = "919876500031"
    mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})

    # snapshot log size to only scan new lines
    try:
        start_size = os.path.getsize(BACKEND_LOG)
    except OSError:
        start_size = 0

    r = _post_webhook(_text_webhook(phone, "Hi"), url=EXPECTED_WEBHOOK_URL, timeout=30)
    assert r.status_code == 200

    def check_user():
        u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
        if not u:
            return None
        ch = u.get("chat_history") or []
        joined = json.dumps(ch, ensure_ascii=False)
        if "Namaste" in joined and "Sent flow - [birth_details]" in joined:
            return u
        return None

    u = _wait_for(check_user, timeout=25)
    assert u is not None, "Greeting + flow marker not stored in chat_history"

    # Verify backend log has flow API response with matching flow_id + status 200
    time.sleep(1)
    try:
        with open(BACKEND_LOG, "rb") as fh:
            fh.seek(start_size)
            new_log = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        new_log = ""

    # Fallback: tail whole file if we didn't capture enough
    if "Birth details flow API response" not in new_log:
        try:
            with open(BACKEND_LOG, "rb") as fh:
                fh.seek(max(0, os.path.getsize(BACKEND_LOG) - 200_000))
                new_log = fh.read().decode("utf-8", errors="ignore")
        except OSError:
            pass

    assert "Birth details flow API response" in new_log, (
        "Expected 'Birth details flow API response' log line missing"
    )
    # Find the most recent flow response line for our flow_id
    hits = re.findall(
        r"Birth details flow API response[^\n]*",
        new_log,
    )
    assert hits, "no flow API response lines captured"
    last = hits[-1]
    assert '"status_code":200' in last or "status_code=200" in last, (
        f"flow API did not return 200: {last}"
    )
    # flow_id is logged in the preceding 'Sending birth details flow' record
    assert BIRTH_FLOW_ID in new_log, (
        f"expected flow_id {BIRTH_FLOW_ID} somewhere in recent backend logs"
    )


# ─── Test 3: Typed-text fallback with time -> full chart ──────────────────────
def test_typed_text_fallback_full_chart(mongo):
    phone = "919876500035"
    mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})

    # Greeting first (creates user, sends flow) then typed reply
    r1 = _post_webhook(_text_webhook(phone, "Hi"))
    assert r1.status_code == 200
    time.sleep(4)

    r2 = _post_webhook(_text_webhook(phone, "12-08-1993, 14:30, Jaipur"))
    assert r2.status_code == 200

    def check():
        u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
        if not u or not u.get("chart_json") or not u.get("free_reading_used"):
            return None
        return u

    u = _wait_for(check, timeout=50, interval=2)
    assert u is not None, "typed-text fallback did not produce chart + free reading"
    chart = u["chart_json"]
    meta = chart.get("meta") or {}
    assert meta.get("chart_type") == "full", f"chart_type={meta.get('chart_type')}"
    dasha = chart.get("dasha_timeline") or []
    assert len(dasha) == 9, f"dasha_timeline len={len(dasha)}"

    bd = u.get("birth_details") or {}
    assert bd.get("date_of_birth") == "1993-08-12", bd
    assert bd.get("time_of_birth") == "14:30", bd
    # Place could be 'Jaipur' or geocoded canonical spelling – ensure Jaipur substring
    assert "jaipur" in str(bd.get("place_name") or "").lower(), bd

    ch = u.get("chat_history") or []
    long_assistant = [
        m for m in ch if m.get("role") == "assistant" and len(str(m.get("content") or "")) > 200
    ]
    assert long_assistant, "LLM reading not found in chat_history"


# ─── Test 4: Typed-text fallback WITHOUT time -> surya_kundli ─────────────────
def test_typed_text_fallback_surya_kundli(mongo):
    phone = "919876500032"
    mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})

    _post_webhook(_text_webhook(phone, "Hi"))
    time.sleep(4)
    r = _post_webhook(_text_webhook(phone, "01/01/1995 Mumbai"))
    assert r.status_code == 200

    def check():
        u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
        if not u or not u.get("chart_json"):
            return None
        return u

    u = _wait_for(check, timeout=45, interval=2)
    assert u is not None, "surya kundli chart not produced from typed text"
    chart = u["chart_json"]
    assert chart["meta"]["chart_type"] == "surya_kundli", chart["meta"]
    assert chart.get("lagna") is None, f"lagna should be None, got {chart.get('lagna')}"


# ─── Test 5: nfm_reply regression ─────────────────────────────────────────────
def test_nfm_reply_regression(mongo):
    phone = "919876500033"
    mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})

    _post_webhook(_text_webhook(phone, "Hi"))
    time.sleep(4)

    flow = {
        "flow_token": f"samara_birth${BIRTH_FLOW_ID}",
        "flow_kind": "birth_details",
        "birth_date": "1988-11-20",
        "birth_time": "21:45",
        "unknown_time": False,
        "birth_place": "Pune",
    }
    r = _post_webhook(_flow_webhook(phone, flow))
    assert r.status_code == 200

    def check():
        u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
        if not u or not u.get("chart_json") or not u.get("free_reading_used"):
            return None
        return u

    u = _wait_for(check, timeout=50, interval=2)
    assert u is not None, "nfm_reply flow did not deliver chart + reading"
    assert u["chart_json"]["meta"]["chart_type"] == "full"


# ─── Test 6: Follow-up ungated (paywall OFF until Phase 2) ────────────────────
def test_followup_not_paywalled_after_free_reading(mongo):
    phone = "919876500033"
    u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
    if not u or not u.get("free_reading_used"):
        pytest.skip("nfm_reply regression must have produced free reading first")

    before = int(u.get("followup_questions_asked") or 0)
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"credits": 0}})
    r = _post_webhook(_text_webhook(phone, "Career kaisa rahega?"))
    assert r.status_code == 200

    def check():
        u2 = mongo.users.find_one({"_id": u["_id"]})
        if int(u2.get("followup_questions_asked") or 0) <= before:
            return None
        ch = u2.get("chat_history") or []
        recent = " ".join(
            str(m.get("content") or "")
            for m in ch[-6:]
            if m.get("role") == "assistant"
        ).lower()
        if "coming soon" in recent:
            return None
        if recent.strip():
            return u2
        return None

    u_fu = _wait_for(check, timeout=45, interval=1.5)
    assert u_fu is not None, "follow-up answer not delivered (paywall should be OFF)"


# ─── Test 7: Gupshup subscription check ───────────────────────────────────────
def test_gupshup_subscription_registered():
    result = subprocess.run(
        ["python", "scripts/setup_gupshup_webhook.py", "--list"],
        cwd="/app/backend",
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, f"script failed: {result.stderr[:400]}"
    data = json.loads(result.stdout)
    subs = data.get("subscriptions") or []
    assert len(subs) == 1, f"expected exactly one subscription, got {len(subs)}"
    sub = subs[0]
    assert sub.get("url") == EXPECTED_WEBHOOK_URL, sub
    assert sub.get("active") is True, sub
    assert "MESSAGE" in (sub.get("modes") or []), sub
