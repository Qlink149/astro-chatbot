"""Tests for POST /api/system/user/{phone}/delete-chat — chat-only wipe endpoint.

Contract:
  - 401 when no bearer token supplied
  - 404 when user not found
  - success wipes chat_history + chat_messages + message_traces
  - CRITICAL: preserves chart_json, birth_details, user_language,
    free_reading_used, reading_delivered_at, followup_questions_asked, credits
  - Regression: /reset still does a full wipe and still enforces auth
"""
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

from kisna_chatbot.main import app  # noqa: F401  (bootstrap)

import os as _os
import time
import pytest
import requests

BASE_URL = _os.environ.get("REACT_APP_BACKEND_URL", "https://clara-astro.preview.emergentagent.com").rstrip("/")
USERNAME = "Yogansh@claraai.tech"
PASSWORD = "riteshseema"

TEST_PHONE = f"9199TESTDC{int(time.time()) % 100000}"
CLIENT_ID = "samara"


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/system/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def db_users():
    """Direct pymongo handle so we can seed / re-fetch without going via API."""
    from kisna_chatbot.database.collections import users, chat_messages, message_traces
    return users, chat_messages, message_traces


SEED_PROFILE = {
    "phone_number": TEST_PHONE,
    "client_id": CLIENT_ID,
    "username": "TEST_DeleteChatUser",
    "user_language": "hindi",
    "free_reading_used": True,
    "reading_delivered_at": "2026-01-05T10:00:00Z",
    "followup_questions_asked": 3,
    "credits": 42,
    "chart_json": {"meta": {"birth_year": 1990, "chart_type": "full"}, "lagna": {"sign_en": "Leo", "sign_hi": "Simha"}},
    "birth_details": {"date_of_birth": "1990-05-15", "time_of_birth": "07:25", "place_name": "Jaipur"},
    "chat_history": [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "namaste"},
        {"role": "user", "text": "what about my career"},
    ],
}


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup(db_users):
    users, chat_messages, message_traces = db_users
    query = {"phone_number": TEST_PHONE, "client_id": CLIENT_ID}
    users.delete_many(query)
    chat_messages.delete_many(query)
    message_traces.delete_many(query)

    users.insert_one(dict(SEED_PROFILE))
    chat_messages.insert_many([
        {"phone_number": TEST_PHONE, "client_id": CLIENT_ID, "role": "user", "text": "hi"},
        {"phone_number": TEST_PHONE, "client_id": CLIENT_ID, "role": "assistant", "text": "namaste"},
    ])
    message_traces.insert_one({
        "phone_number": TEST_PHONE, "client_id": CLIENT_ID, "request_id": "req_test_dc", "trace": []
    })

    yield

    users.delete_many(query)
    chat_messages.delete_many(query)
    message_traces.delete_many(query)


# ----------------- delete-chat endpoint -----------------

class TestDeleteChatAuth:
    def test_delete_chat_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/system/user/{TEST_PHONE}/delete-chat?client_id={CLIENT_ID}",
            timeout=15,
        )
        assert r.status_code in (401, 403), f"Expected 401/403 without token, got {r.status_code}: {r.text}"

    def test_delete_chat_unknown_phone_returns_404(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/system/user/9199NOTEXIST0001/delete-chat?client_id={CLIENT_ID}",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 404, r.text


class TestDeleteChatBehaviour:
    def test_delete_chat_success_response_shape(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/system/user/{TEST_PHONE}/delete-chat?client_id={CLIENT_ID}",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["phone_number"] == TEST_PHONE
        assert data["client_id"] == CLIENT_ID
        assert data["chat_messages_deleted"] == 2
        assert data["message_traces_deleted"] == 1

    def test_delete_chat_wipes_transcript_but_preserves_profile(self, auth_headers, db_users):
        """CRITICAL — the whole point of delete-chat vs reset."""
        users, chat_messages, message_traces = db_users
        query = {"phone_number": TEST_PHONE, "client_id": CLIENT_ID}
        user = users.find_one(query)
        assert user is not None
        # Wiped:
        assert user.get("chat_history") == []
        assert chat_messages.count_documents(query) == 0
        assert message_traces.count_documents(query) == 0
        # Preserved:
        assert user.get("chart_json") == SEED_PROFILE["chart_json"]
        assert user.get("birth_details") == SEED_PROFILE["birth_details"]
        assert user.get("user_language") == "hindi"
        assert user.get("free_reading_used") is True
        assert user.get("reading_delivered_at") == SEED_PROFILE["reading_delivered_at"]
        assert user.get("followup_questions_asked") == 3
        assert user.get("credits") == 42

    def test_delete_chat_idempotent(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/system/user/{TEST_PHONE}/delete-chat?client_id={CLIENT_ID}",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["chat_messages_deleted"] == 0
        assert data["message_traces_deleted"] == 0


# ----------------- /reset regression -----------------

class TestResetRegression:
    def test_reset_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/system/user/{TEST_PHONE}/reset?client_id={CLIENT_ID}",
            timeout=15,
        )
        assert r.status_code in (401, 403)

    def test_reset_unknown_phone_returns_404(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/system/user/9199NOTEXIST9999/reset?client_id={CLIENT_ID}",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 404

    def test_reset_does_full_wipe(self, auth_headers, db_users):
        """Regression — /reset still nukes chart, language, credits etc."""
        users, _, _ = db_users
        query = {"phone_number": TEST_PHONE, "client_id": CLIENT_ID}
        # Re-seed the profile richly (previous tests already wiped its transcript).
        users.update_one(query, {"$set": {
            "chart_json": SEED_PROFILE["chart_json"],
            "birth_details": SEED_PROFILE["birth_details"],
            "user_language": "hindi",
            "free_reading_used": True,
            "credits": 42,
            "followup_questions_asked": 3,
        }})

        r = requests.post(
            f"{BASE_URL}/api/system/user/{TEST_PHONE}/reset?client_id={CLIENT_ID}",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text

        user = users.find_one(query)
        assert user is not None, "profile row should still exist"
        assert user.get("chart_json") is None
        assert user.get("birth_details") is None
        assert user.get("user_language") is None
        assert user.get("free_reading_used") is False
        assert user.get("credits") == 0
        assert user.get("followup_questions_asked") == 0
        assert user.get("chat_history") == []
