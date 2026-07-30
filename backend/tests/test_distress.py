"""Distress path: LLM classifier primary; bypass astrology; no debit."""
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

from kisna_chatbot.main import app  # noqa: F401

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

import kisna_chatbot.processors.samara_reading_agent as mod
from kisna_chatbot.payments.credit_ledger import get_credit_balance
from kisna_chatbot.utils.distress import (
    DISTRESS_CLASSIFIER_PROMPT,
    assess_distress,
    parse_classifier_json,
    self_harm_failsafe,
)


def _run(coro):
    return asyncio.run(coro)


MIN_CHART = {
    "meta": {
        "birth_year": 1990,
        "current_age": 35,
        "has_birth_time": True,
        "chart_type": "full",
    },
    "lagna": {"sign_en": "Virgo", "sign_hi": "Kanya"},
    "rashi": {"sign_en": "Cancer", "sign_hi": "Karka"},
    "nakshatra": {"name": "Pushya", "pada": 2},
    "dasha_timeline": [],
}

# (user text, classifier JSON, expect distress, expect self_harm, expect helpline)
LLM_FIXTURES = [
    (
        "I want to die, nothing matters",
        {"distress": True, "self_harm": True},
        True,
        True,
        True,
    ),
    (
        "Kya main mar jaunga",
        {"distress": True, "self_harm": True},
        True,
        True,
        True,
    ),
    (
        "Meri maa ki tabiyat kharab hai, woh theek ho jayengi?",
        {"distress": True, "self_harm": False},
        True,
        False,
        False,
    ),
    (
        "Will my mother survive?",
        {"distress": True, "self_harm": False},
        True,
        False,
        False,
    ),
    (
        "Kya meri shaadi bachegi?",
        {"distress": True, "self_harm": False},
        True,
        False,
        False,
    ),
    (
        "Should I leave my husband?",
        {"distress": True, "self_harm": False},
        True,
        False,
        False,
    ),
    (
        "Kya zindagi mein kuch achha hoga? Main thak gaya hoon.",
        {"distress": True, "self_harm": False},
        True,
        False,
        False,
    ),
    (
        "Mera business doob raha hai, kya karun?",
        {"distress": True, "self_harm": False},
        True,
        False,
        False,
    ),
    (
        "What is my career dasha now?",
        {"distress": False, "self_harm": False},
        False,
        False,
        False,
    ),
]


@pytest.fixture(autouse=True)
def _mute_funnel():
    with patch("kisna_chatbot.processors.samara_reading_agent.emit_funnel_event"):
        yield


def test_parse_classifier_json():
    r = parse_classifier_json('{"distress": true, "self_harm": false}')
    assert r and r.distress and not r.self_harm and r.source == "llm"


def test_assess_uses_llm_not_regex_for_crisis_phrases():
    async def go():
        async def classify(_inst, _text):
            return json.dumps({"distress": True, "self_harm": False})

        # Phrase that has no failsafe self-harm regex — must come from LLM
        r = await assess_distress(
            "Kya meri shaadi bachegi?", classify_fn=classify
        )
        assert r.distress is True
        assert r.source == "llm"

    _run(go())


def test_failsafe_only_when_llm_missing():
    async def go():
        r = await assess_distress("I want to die", classify_fn=None)
        assert r.distress is True and r.self_harm is True
        assert r.source == "failsafe"
        assert self_harm_failsafe("I want to die")

        r2 = await assess_distress("Kya meri shaadi bachegi?", classify_fn=None)
        assert r2.distress is False  # no LLM → no false regex crisis

    _run(go())


@pytest.mark.parametrize(
    "text,cls,exp_distress,exp_sh,exp_help", LLM_FIXTURES
)
def test_distress_fixtures_via_llm(
    text, cls, exp_distress, exp_sh, exp_help
):
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "hindi" if "Kya" in text or "Mera" in text or "Meri" in text else "english",
            "free_deep_answer_used": True,
            "credits": 5,
            "credit_ledger": [
                {"type": "grant", "amount": 5, "source": "test", "timestamp": 1}
            ],
            "conversation_beat": "post_free_deep",
            "chat_history": [],
        }
        before = get_credit_balance(profile)

        async def fake_complete(**kwargs):
            if kwargs.get("agent_display_name") == "SamaraDistress":
                return json.dumps(cls)
            if exp_distress:
                raise AssertionError("astrology LLM must not run on distress")
            return "Career looks steady."

        def fake_debit(**kwargs):
            entries = list(profile.get("credit_ledger") or [])
            entries.append(
                {
                    "type": "debit",
                    "amount": 1,
                    "source": "deep_answer",
                    "timestamp": 2,
                }
            )
            profile["credit_ledger"] = entries
            profile["credits"] = get_credit_balance(profile)
            return profile

        with patch.object(mod, "complete_chat", new=AsyncMock(side_effect=fake_complete)):
            with patch.object(mod, "debit_credit", side_effect=fake_debit):
                data = {
                    "client_id": "samara",
                    "phone_number": "919999900001",
                    "user_profile": profile,
                    "messages": {
                        "id": f"wamid.{hash(text) & 0xffff}",
                        "type": "text",
                        "text": {"body": text},
                    },
                }
                out = await agent.process(data)

        body = out["bot_response"][0]["text"]
        if exp_distress:
            assert get_credit_balance(profile) == before
            assert (
                "kundli nahi" in body.lower()
                or "astrology" in body.lower()
                or "chart" in body.lower()
            )
            if exp_help:
                assert "14416" in body and "1800-599-0019" in body
            else:
                assert "14416" not in body
        else:
            assert "Career" in body or "steady" in body.lower()

    _run(go())


def test_distress_classifier_uses_haiku_not_sonnet():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Alex",
            "chart_json": MIN_CHART,
            "user_language": "english",
            "free_deep_answer_used": True,
            "credits": 1,
            "conversation_beat": "post_free_deep",
        }
        captured = {}

        async def fake_complete(**kwargs):
            captured["model"] = kwargs.get("model")
            captured["fallback"] = kwargs.get("model_fallback")
            captured["name"] = kwargs.get("agent_display_name")
            assert DISTRESS_CLASSIFIER_PROMPT.split("\n")[1].strip() in (
                kwargs.get("instruction") or ""
            ) or "distress" in (kwargs.get("instruction") or "").lower()
            return json.dumps({"distress": True, "self_harm": False})

        with patch.object(mod, "complete_chat", new=AsyncMock(side_effect=fake_complete)):
            with patch.object(
                mod,
                "_sonnet_models",
                return_value=("claude-sonnet-test", "claude-haiku-test"),
            ):
                data = {
                    "client_id": "samara",
                    "phone_number": "919999900099",
                    "user_profile": profile,
                    "messages": {
                        "id": "wamid.modelcheck",
                        "type": "text",
                        "text": {"body": "I feel hopeless about everything"},
                    },
                }
                await agent.process(data)

        assert captured.get("name") == "SamaraDistress"
        assert captured.get("model") == "claude-haiku-test"
        assert captured.get("fallback") in (None, "")

    _run(go())
