"""Smoke tests for SAMARA_FIX_V3_FINAL flow — language buttons + no paywall."""
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

from kisna_chatbot.main import app  # noqa: F401  (pre-bootstraps the module graph)

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

import kisna_chatbot.processors.samara_reading_agent as mod


@pytest.fixture(autouse=True)
def _ensure_env():
    """Neutralise conftest env fixtures for this file (no-op)."""
    yield


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_birth_details_asks_language_before_reading():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {"username": "Rahul", "chat_history": []}
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "type": "interactive",
                "interactive": {
                    "nfm_reply": {
                        "response_json": json.dumps({
                            "flow_kind": "birth_details",
                            "birth_date": "1990-05-15",
                            "birth_time": "07:25",
                            "unknown_time": [],
                            "birth_place": "jaipur",
                        })
                    }
                },
            },
        }
        out = await agent.process(data)
        assert profile.get("chart_json"), "chart should be computed"
        assert profile.get("user_language") is None, "language cleared for fresh cycle"
        resp = out["bot_response"]
        assert len(resp) == 1 and resp[0]["type"] == "quickreply"
        ids = [o["postbackText"] for o in resp[0]["options"]]
        assert "samara_lang_en" in ids and "samara_lang_hi" in ids
    _run(go())


def test_language_button_english_triggers_reading_in_english():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {"username": "Rahul", "chat_history": [],
                   "chart_json": {"meta": {"birth_year": 1990}}}
        with patch.object(mod, "complete_chat", new=AsyncMock(return_value="[reading]")) as mock_cc:
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "type": "interactive",
                    "interactive": {"button_reply": {"id": "samara_lang_en", "title": "English"}},
                },
            }
            await agent.process(data)
            called = mock_cc.await_args.kwargs
            assert "english" in called["instruction"].lower()
        assert profile["user_language"] == "english"
        assert profile["free_reading_used"] is True
    _run(go())


def test_language_plain_text_hindi_also_works():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {"username": "Ayesha", "chat_history": [],
                   "chart_json": {"meta": {"birth_year": 1988}}}
        with patch.object(mod, "complete_chat", new=AsyncMock(return_value="[reading]")):
            data = {
                "client_id": "samara",
                "phone_number": "919999900002",
                "user_profile": profile,
                "messages": {"type": "text", "text": {"body": "Hindi"}},
            }
            await agent.process(data)
        assert profile["user_language"] == "hindi"
    _run(go())


def test_followup_is_not_paywalled():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chat_history": [],
            "chart_json": {"meta": {"birth_year": 1990}},
            "free_reading_used": True,
            "user_language": "english",
            "credits": 0,  # zero credits — must NOT block
        }
        with patch.object(mod, "complete_chat", new=AsyncMock(return_value="[follow-up answer]")):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {"type": "text", "text": {"body": "what about my career?"}},
            }
            out = await agent.process(data)
        assert out["bot_response"][0]["text"] == "[follow-up answer]"
        assert "credits chahiye" not in out["bot_response"][0]["text"]
    _run(go())


def test_samara_general_client_id_routes_to_anthropic_when_key_set(monkeypatch):
    from kisna_chatbot.ai import config as cfg
    from kisna_chatbot.ai.factory import _samara_uses_anthropic
    from kisna_chatbot.ai.types import AgentName

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    cfg.refresh_ai_settings()
    assert _samara_uses_anthropic(AgentName.GENERAL, "samara") is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
    cfg.refresh_ai_settings()
    assert _samara_uses_anthropic(AgentName.GENERAL, "samara") is True
    assert _samara_uses_anthropic(AgentName.GENERAL, "kisna") is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    cfg.refresh_ai_settings()
