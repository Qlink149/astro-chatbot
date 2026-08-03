"""PWYW amount parse, credits formula, webhook amount verify."""

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

import pytest

from kisna_chatbot.utils.pwyw_amount import (
    check_amount,
    credits_for_amount,
    parse_amount_inr,
)
from kisna_chatbot.utils.samara_beats import paywall_buttons


@pytest.fixture(autouse=True)
def _pwyw_env(monkeypatch):
    monkeypatch.setenv("SAMARA_MIN_PAYMENT_INR", "39")
    monkeypatch.setenv("SAMARA_MAX_PAYMENT_INR", "5000")
    monkeypatch.setenv("SAMARA_RUPEES_PER_CREDIT", "4.0")
    monkeypatch.setenv("SAMARA_MIN_CREDITS_GRANT", "10")


def test_parse_amounts():
    assert parse_amount_inr("₹39") == 39.0
    assert parse_amount_inr("rs 50") == 50.0
    assert parse_amount_inr("Rs.99") == 99.0
    assert parse_amount_inr("३९") == 39.0
    assert parse_amount_inr("99.5") == 99.5
    assert parse_amount_inr("hello") is None
    assert parse_amount_inr("") is None


def test_credits_formula():
    assert credits_for_amount(39) == 10
    assert credits_for_amount(99) == 25
    assert credits_for_amount(40) == 10  # round(40/4)=10
    assert credits_for_amount(100) == 25


def test_min_reject_and_large_confirm():
    assert check_amount("20").verdict == "under_min"
    assert check_amount("oops").verdict == "unparseable"
    ok = check_amount("39")
    assert ok.verdict == "ok"
    assert ok.credits == 10
    big = check_amount("6000")
    assert big.verdict == "needs_confirm"
    assert big.amount_inr == 6000.0


def test_paywall_buttons_later_only_no_fixed_rupee():
    qr = paywall_buttons(lang="hindi", body="door", amount_inr=39)
    opts = qr.get("options") or []
    titles = " ".join(o.get("title", "") for o in opts)
    assert "Baad mein" in titles or "Later" in titles
    assert "₹" not in titles
    assert len(opts) == 1


def test_create_rejects_under_min(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    from kisna_chatbot.payments.service import create_and_store_payment_link

    with pytest.raises(ValueError, match="at least"):
        create_and_store_payment_link(
            order_id="samara_under",
            amount_in_rupees=10,
            customer={"name": "T", "contact": "919999999999"},
            phone_number="919999999999",
        )


def test_webhook_mismatch_no_grant(monkeypatch):
    from kisna_chatbot.payments import webhook_handler as wh

    monkeypatch.setattr(
        wh,
        "get_payment_by_link_id",
        lambda _id: {
            "payment_link_id": "plink_x",
            "amount_paise": 3900,
            "phone_number": "919999999999",
            "client_id": "samara",
            "notes": {},
        },
    )
    updates = []
    monkeypatch.setattr(
        wh,
        "update_payment_by_link_id",
        lambda _id, patch: updates.append(patch),
    )
    grants = []

    def _grant(**kwargs):
        grants.append(kwargs)
        return {"credits": 10}

    monkeypatch.setattr(wh, "grant_credits_for_payment", _grant)

    event = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_x",
                    "amount": 3900,
                    "amount_paid": 100,  # underpay / mismatch
                    "status": "paid",
                }
            },
            "payment": {"entity": {"id": "pay_abc", "amount": 100}},
        },
    }
    result = wh.handle_razorpay_event(event)
    assert result.get("credits_granted") is False
    assert result.get("amount_rejected") is True
    assert grants == []


def test_webhook_grants_scaled_credits(monkeypatch):
    from kisna_chatbot.payments import webhook_handler as wh

    monkeypatch.setattr(
        wh,
        "get_payment_by_link_id",
        lambda _id: {
            "payment_link_id": "plink_ok",
            "amount_paise": 9900,
            "phone_number": "919999999999",
            "client_id": "samara",
            "notes": {},
        },
    )
    monkeypatch.setattr(wh, "update_payment_by_link_id", lambda *_a, **_k: None)
    grants = []

    def _grant(**kwargs):
        grants.append(kwargs)
        return {"credits": kwargs["credits"]}

    monkeypatch.setattr(wh, "grant_credits_for_payment", _grant)
    monkeypatch.setattr(
        wh,
        "_send_payment_confirmation_and_resume",
        lambda *a, **k: None,
    )

    class _Users:
        def find_one(self, *_a, **_k):
            return {"phone_number": "919999999999", "client_id": "samara", "credits": 0}

    monkeypatch.setattr(
        "kisna_chatbot.database.collections.users",
        _Users(),
        raising=False,
    )
    monkeypatch.setattr(
        "kisna_chatbot.payments.credit_ledger.get_credit_balance",
        lambda u: int((u or {}).get("credits") or 0),
    )

    # Patch imports inside handler
    import kisna_chatbot.payments.credit_ledger as cl
    import kisna_chatbot.database.collections as cols

    monkeypatch.setattr(cl, "get_credit_balance", lambda u: int((u or {}).get("credits") or 0))
    monkeypatch.setattr(cols, "users", _Users())

    event = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_ok",
                    "amount": 9900,
                    "amount_paid": 9900,
                    "status": "paid",
                }
            },
            "payment": {"entity": {"id": "pay_ok99", "amount": 9900}},
        },
    }
    result = wh.handle_razorpay_event(event)
    assert result.get("credits_granted") is True
    assert grants and grants[0]["credits"] == 25
    assert grants[0]["payment_id"] == "pay_ok99"


def test_webhook_idempotent_replay(monkeypatch):
    from kisna_chatbot.payments import webhook_handler as wh

    monkeypatch.setattr(
        wh,
        "get_payment_by_link_id",
        lambda _id: {
            "payment_link_id": "plink_idemp",
            "amount_paise": 3900,
            "phone_number": "919999999999",
            "client_id": "samara",
            "credits_granted_payment_id": "pay_once",
            "notes": {},
        },
    )
    monkeypatch.setattr(wh, "update_payment_by_link_id", lambda *_a, **_k: None)
    grants = []
    monkeypatch.setattr(
        wh,
        "grant_credits_for_payment",
        lambda **kwargs: grants.append(kwargs),
    )

    event = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_idemp",
                    "amount_paid": 3900,
                    "amount": 3900,
                }
            },
            "payment": {"entity": {"id": "pay_once", "amount": 3900}},
        },
    }
    result = wh.handle_razorpay_event(event)
    assert result.get("credits_granted") is False
    assert grants == []
