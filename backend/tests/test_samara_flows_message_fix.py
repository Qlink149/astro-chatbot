"""Iteration 3 verification: FLOWS_MESSAGE subscription + real phone_number_id routing.

Verifies:
  1. Gupshup subscription includes FLOWS_MESSAGE mode, version 3, active
  2. Real phone_number_id (451074671429987) routes inbound text -> samara client greeting + flow
  3. Full nfm_reply flow completion with real phone_number_id -> chart + free reading + LLM
  4. Outbound Gupshup flow send returns 200 in backend logs
  5. Backend health + admin login
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
REAL_PHONE_ID = "451074671429987"  # real Meta phone_number_id (from .env SAMARA_PHONE_NUMBER_ID)
BIRTH_FLOW_ID = os.environ.get("SAMARA_BIRTH_FLOW_ID", "1018626800813268")
EXPECTED_WEBHOOK_URL = "https://clara-astro.preview.emergentagent.com/api/gupshup/message/samara"
BACKEND_LOG = "/var/log/supervisor/backend.out.log"

ADMIN_USER = "Yogansh@claraai.tech"
ADMIN_PASS = "riteshseema"


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _text_webhook(phone: str, body: str = "Hi") -> dict:
    wamid = f"wamid.ITER3_{uuid.uuid4().hex}"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": REAL_PHONE_ID,
                                "display_phone_number": REAL_PHONE_ID,
                            },
                            "contacts": [
                                {"wa_id": phone, "profile": {"name": "Iter3 User"}}
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
    wamid = f"wamid.ITER3_{uuid.uuid4().hex}"
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": REAL_PHONE_ID,
                                "display_phone_number": REAL_PHONE_ID,
                            },
                            "contacts": [
                                {"wa_id": phone, "profile": {"name": "Iter3 User"}}
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


def _post_webhook(payload: dict, timeout: int = 30):
    last_err = None
    for _ in range(2):
        try:
            return requests.post(
                f"{API}/gupshup/message/samara", json=payload, timeout=timeout
            )
        except requests.RequestException as exc:
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


def _req_with_retry(method: str, url: str, **kwargs):
    kwargs.setdefault("timeout", 30)
    last = None
    for _ in range(3):
        try:
            return requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            last = exc
            time.sleep(3)
    raise last  # type: ignore[misc]


# ─── Test 1: Backend ping ─────────────────────────────────────────────────────
def test_backend_ping():
    r = _req_with_retry("GET", f"{API}/ping", timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("status") == "ok"


# ─── Test 2: Admin login ──────────────────────────────────────────────────────
def test_admin_login():
    r = _req_with_retry(
        "POST",
        f"{API}/system/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    token = body.get("token") or body.get("access_token")
    assert token, f"no token in response: {body}"
    assert isinstance(token, str) and len(token) > 20


# ─── Test 3: Gupshup subscription includes FLOWS_MESSAGE + MESSAGE ────────────
def test_gupshup_subscription_flows_message_mode():
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
    assert sub.get("version") == 3, f"version={sub.get('version')}"
    modes = set(sub.get("modes") or [])
    assert "MESSAGE" in modes, f"MESSAGE missing from modes: {modes}"
    assert "FLOWS_MESSAGE" in modes, f"FLOWS_MESSAGE missing from modes: {modes}"
    # Sanity: expected extra modes from the fix
    for m in ["SENT", "DELIVERED", "READ", "DELETED", "FAILED", "OTHERS", "ENQUEUED"]:
        assert m in modes, f"expected mode {m} missing: {modes}"


# ─── Test 4: Real phone_number_id routes to samara client ─────────────────────
def test_real_phone_number_id_routes_samara(mongo):
    phone = "919876500041"
    mongo.users.delete_one({"phone_number": phone, "client_id": "samara"})
    # also delete any stale kisna record for this phone to be sure
    mongo.users.delete_one({"phone_number": phone, "client_id": "kisna"})

    # snapshot log
    try:
        start_size = os.path.getsize(BACKEND_LOG)
    except OSError:
        start_size = 0

    r = _post_webhook(_text_webhook(phone, "Hi"))
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("success") is True, body

    def check_user():
        u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
        if not u:
            return None
        ch = u.get("chat_history") or []
        joined = json.dumps(ch, ensure_ascii=False)
        if "Namaste" in joined and "Sent flow - [birth_details]" in joined:
            return u
        return None

    u = _wait_for(check_user, timeout=30, interval=2)
    assert u is not None, "greeting + birth_details flow marker not recorded for samara client"

    # ensure NOT stored as kisna
    kisna_u = mongo.users.find_one({"phone_number": phone, "client_id": "kisna"})
    assert kisna_u is None, "user was routed to kisna client — phone_number_id map is wrong"

    # confirm log shows an outbound flow API 200 in this window
    time.sleep(1)
    try:
        with open(BACKEND_LOG, "rb") as fh:
            fh.seek(start_size)
            new_log = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        new_log = ""
    if "Birth details flow API response" not in new_log:
        try:
            with open(BACKEND_LOG, "rb") as fh:
                fh.seek(max(0, os.path.getsize(BACKEND_LOG) - 300_000))
                new_log = fh.read().decode("utf-8", errors="ignore")
        except OSError:
            pass
    assert "Birth details flow API response" in new_log, (
        "flow API response log line missing after real phone_number_id inbound"
    )
    hits = re.findall(r"Birth details flow API response[^\n]*", new_log)
    assert hits, "no flow API response lines captured"
    last = hits[-1]
    assert ('"status_code": 200' in last) or ('"status_code":200' in last) or ("status_code=200" in last), (
        f"flow API did not return 200: {last}"
    )
    # phone appears near flow send record
    assert phone in new_log, f"phone {phone} not seen in backend logs recently"


# ─── Test 5: Full nfm_reply flow with real phone_number_id ────────────────────
def test_nfm_reply_full_regression_real_phone_id(mongo):
    phone = "919876500041"  # same phone continues; user should already exist from test 4
    # ensure user exists (in case test 4 was skipped by ordering)
    u0 = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
    if not u0:
        _post_webhook(_text_webhook(phone, "Hi"))
        time.sleep(4)

    # Clear chart/free_reading state so we truly test regeneration via nfm_reply
    mongo.users.update_one(
        {"phone_number": phone, "client_id": "samara"},
        {"$unset": {"chart_json": "", "birth_details": ""},
         "$set": {"free_reading_used": False}},
    )

    flow = {
        "flow_token": f"samara_birth${BIRTH_FLOW_ID}",
        "flow_kind": "birth_details",
        "birth_date": "1991-03-10",
        "birth_time": "06:40",
        "unknown_time": False,
        "birth_place": "Lucknow",
    }
    r = _post_webhook(_flow_webhook(phone, flow))
    assert r.status_code == 200, r.text[:300]

    def check():
        u = mongo.users.find_one({"phone_number": phone, "client_id": "samara"})
        if not u:
            return None
        if not u.get("chart_json") or not u.get("free_reading_used"):
            return None
        return u

    u = _wait_for(check, timeout=45, interval=2)
    assert u is not None, "nfm_reply with real phone_number_id did not deliver chart + reading"

    chart = u["chart_json"]
    meta = chart.get("meta") or {}
    assert meta.get("chart_type") == "full", f"chart_type={meta.get('chart_type')}"
    assert chart.get("lagna"), f"lagna missing/empty: {chart.get('lagna')}"
    dasha = chart.get("dasha_timeline") or []
    assert len(dasha) == 9, f"dasha_timeline len={len(dasha)}"

    bd = u.get("birth_details") or {}
    assert bd.get("date_of_birth") == "1991-03-10", bd
    assert bd.get("time_of_birth") == "06:40", bd
    assert "lucknow" in str(bd.get("place_name") or "").lower(), bd

    ch = u.get("chat_history") or []
    long_assistant = [
        m for m in ch if m.get("role") == "assistant" and len(str(m.get("content") or "")) > 200
    ]
    assert long_assistant, "LLM reading not found in chat_history after nfm_reply"
