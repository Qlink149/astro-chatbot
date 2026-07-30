"""Unit tests for append-only credit ledger + payment-id idempotency."""

from __future__ import annotations

from kisna_chatbot.payments.credit_ledger import (
    _ledger_balance,
    get_credit_balance,
)


def test_ledger_balance_grant_debit_refund():
    entries = [
        {"type": "grant", "amount": 10},
        {"type": "debit", "amount": 1},
        {"type": "debit", "amount": 1},
        {"type": "refund", "amount": 1},
    ]
    assert _ledger_balance(entries) == 9


def test_get_credit_balance_prefers_ledger():
    profile = {
        "credits": 99,  # stale cache
        "credit_ledger": [
            {"type": "grant", "amount": 10},
            {"type": "debit", "amount": 3},
        ],
    }
    assert get_credit_balance(profile) == 7


def test_get_credit_balance_legacy_int():
    assert get_credit_balance({"credits": 5}) == 5
    assert get_credit_balance({}) == 0


def test_grant_idempotent_on_payment_id(monkeypatch):
    from kisna_chatbot.payments import credit_ledger as cl

    store = {
        "phone_number": "9199",
        "client_id": "samara",
        "credit_ledger": [],
        "credits": 0,
    }

    def fake_find_one(q):
        if q.get("phone_number") == "9199":
            return dict(store)
        return None

    def fake_find_one_and_update(q, update, **kwargs):
        set_fields = update.get("$set") or {}
        store.update(set_fields)
        return dict(store)

    monkeypatch.setattr(cl, "users", type("U", (), {
        "find_one": staticmethod(fake_find_one),
        "find_one_and_update": staticmethod(fake_find_one_and_update),
    })())

    cl.grant_credits(
        phone_number="9199",
        client_id="samara",
        amount=10,
        source="razorpay",
        payment_id="pay_abc",
    )
    assert get_credit_balance(store) == 10
    cl.grant_credits(
        phone_number="9199",
        client_id="samara",
        amount=10,
        source="razorpay",
        payment_id="pay_abc",
    )
    assert get_credit_balance(store) == 10  # no double grant
    assert sum(1 for e in store["credit_ledger"] if e.get("type") == "grant") == 1
