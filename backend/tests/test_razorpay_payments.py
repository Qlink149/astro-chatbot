"""Tests for Razorpay payment-link create + webhook signature verify."""

from __future__ import annotations

import hashlib
import hmac
import json
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def razorpay_env(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setenv("SAMARA_TEST_PAYMENT_AMOUNT_INR", "1")
    monkeypatch.setenv("ENV_MODE", "dev")
    monkeypatch.setenv("SYSTEM_API_KEY", "test_system_api_key")
    monkeypatch.setenv("MONGO_URI", os.getenv("MONGO_URI") or "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "astro_chatbot_test")


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_verify_webhook_signature_valid(razorpay_env):
    from kisna_chatbot.payments.razorpay_client import verify_webhook_signature

    body = b'{"event":"payment_link.paid"}'
    sig = _sign(body, "whsec_test_secret")
    assert verify_webhook_signature(body, sig) is True


def test_verify_webhook_signature_invalid(razorpay_env):
    from kisna_chatbot.payments.razorpay_client import verify_webhook_signature

    body = b'{"event":"payment_link.paid"}'
    assert verify_webhook_signature(body, "deadbeef") is False
    assert verify_webhook_signature(body, "") is False


def test_webhook_endpoint_rejects_bad_signature(razorpay_env, monkeypatch):
    monkeypatch.setenv("GUPSHUP_WEBHOOK_SECRET", "")
    from kisna_chatbot.main import app

    client = TestClient(app)
    body = json.dumps({"event": "payment_link.paid", "payload": {}}).encode()
    resp = client.post(
        "/razorpay/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "invalid",
        },
    )
    assert resp.status_code == 400


def test_webhook_endpoint_accepts_valid_signature(razorpay_env, monkeypatch):
    monkeypatch.setenv("GUPSHUP_WEBHOOK_SECRET", "")

    calls = {"handled": False}

    def _fake_handle(event):
        calls["handled"] = True
        return {"ok": True, "event": event.get("event"), "ignored": True}

    monkeypatch.setattr(
        "kisna_chatbot.payments.webhook_handler.handle_razorpay_event",
        _fake_handle,
    )

    from kisna_chatbot.main import app

    client = TestClient(app)
    payload = {"event": "payment_link.cancelled", "payload": {}}
    body = json.dumps(payload).encode()
    sig = _sign(body, "whsec_test_secret")
    resp = client.post(
        "/razorpay/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("success") is True
    assert calls["handled"] is True


def test_create_payment_link_persists_and_returns(razorpay_env, monkeypatch):
    saved = {}

    class _FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "id": "plink_test_123",
                "short_url": "https://rzp.io/rzp/test123",
                "status": "created",
                "amount": 100,
            }

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert "payment_links" in url
            assert json["amount"] == 100
            assert json["currency"] == "INR"
            assert json["reference_id"] == "samara_test_1"
            assert json["customer"]["contact"] == "+919999999999"
            return _FakeResp()

    monkeypatch.setattr("httpx.Client", lambda **kwargs: _FakeClient())

    def _fake_save(record):
        saved.update(record)
        return record

    monkeypatch.setattr(
        "kisna_chatbot.payments.service.save_payment",
        _fake_save,
    )

    from kisna_chatbot.payments.service import create_and_store_payment_link

    result = create_and_store_payment_link(
        order_id="samara_test_1",
        amount_in_rupees=1,
        currency="INR",
        customer={"name": "Test User", "contact": "919999999999"},
        notes={"client_id": "samara"},
        phone_number="919999999999",
        client_id="samara",
    )

    assert result["payment_link_id"] == "plink_test_123"
    assert result["short_url"] == "https://rzp.io/rzp/test123"
    assert result["order_id"] == "samara_test_1"
    assert saved["payment_link_id"] == "plink_test_123"
    assert saved["amount_paise"] == 100
    assert saved["phone_number"] == "919999999999"


def test_create_payment_link_http_endpoint(razorpay_env, monkeypatch):
    class _FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "id": "plink_http_1",
                "short_url": "https://rzp.io/rzp/http1",
                "status": "created",
                "amount": 100,
            }

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            return _FakeResp()

    monkeypatch.setattr("httpx.Client", lambda **kwargs: _FakeClient())
    monkeypatch.setattr(
        "kisna_chatbot.payments.service.save_payment",
        lambda record: record,
    )
    monkeypatch.setenv("SYSTEM_API_KEY", "test_system_api_key")
    monkeypatch.setattr(
        "kisna_chatbot.routes.dependencies.system_dependencies.system_api_key",
        "test_system_api_key",
    )

    from kisna_chatbot.main import app

    client = TestClient(app)
    resp = client.post(
        "/system/payments/create-payment-link",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test_system_api_key",
        },
        json={
            "order_id": "samara_http_1",
            "amount_in_rupees": 1,
            "currency": "INR",
            "customer": {"name": "Test", "contact": "919999999999"},
            "notes": {"client_id": "samara"},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["payment_link_id"] == "plink_http_1"
    assert data["short_url"].startswith("https://rzp.io/")
    assert data["order_id"] == "samara_http_1"
