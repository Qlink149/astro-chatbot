"""Smoke tests for Samara beat-based conversation (Phase 1)."""
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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import kisna_chatbot.processors.samara_reading_agent as mod
from kisna_chatbot.utils.samara_beats import (
    BEAT_1_AWAITING_CONFIRM,
    BEAT_2_AWAITING_ADVANCE,
    BEAT_2A_AWAITING_CONFIRM,
    BEAT_2B_AWAITING_CONFIRM,
    BEAT_2B_ALT_AWAITING,
    BEAT_2C_AWAITING_DETAIL,
    BEAT_AWAITING_ITEMS,
    BEAT_AWAITING_TOPIC,
    BEAT_POST_FREE_DEEP,
    BEAT_TRUST_RECOVERY,
    BTN_BEAT1_YES,
    BTN_BEAT2_NEXT,
    BTN_BEAT2A_NO,
    BTN_BEAT2A_YES,
    BTN_BEAT2B_NO,
    BTN_BEAT2B_YES,
    BTN_TOPIC_CAREER,
    claim_beat_transition,
    split_whatsapp_text,
)
from kisna_chatbot.utils.samara_gate import count_gate_messages


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
    "dasha_timeline": [
        {
            "planet_en": "Saturn",
            "is_relevant": True,
            "age_start": 20,
            "age_end": 36,
            "phase": "past",
        }
    ],
}

DATED_CHART = {
    **MIN_CHART,
    "meta": {
        **MIN_CHART["meta"],
        "dated_anchors_available": True,
    },
    "turning_points": [
        {
            "start": "2011-03-15",
            "end": "2012-01-01",
            "window_label_en": "early 2011",
            "window_label_hi": "2011 ke shuruaat",
            "theme_en": "responsibility",
            "theme_hi": "zimmedari",
            "antar_planet_en": "Saturn",
            "is_relevant": True,
            "age_start": 21,
            "age_end": 22,
        },
        {
            "start": "2015-09-01",
            "end": "2016-06-01",
            "window_label_en": "late 2015",
            "window_label_hi": "2015 ke ant",
            "theme_en": "letting go",
            "theme_hi": "chorna",
            "antar_planet_en": "Rahu",
            "is_relevant": True,
            "age_start": 25,
            "age_end": 26,
        },
    ],
}

NO_TIME_CHART = {
    "meta": {
        "birth_year": 1990,
        "current_age": 35,
        "has_birth_time": False,
        "chart_type": "moon_only",
        "dated_anchors_available": False,
    },
    "lagna": None,
    "rashi": {"sign_en": "Cancer", "sign_hi": "Karka"},
    "nakshatra": {"name": "Pushya", "pada": 2},
    "dasha_timeline": MIN_CHART["dasha_timeline"],
    "turning_points": [],
}


@pytest.fixture(autouse=True)
def _mute_funnel():
    with patch("kisna_chatbot.processors.samara_reading_agent.emit_funnel_event"):
        yield


def test_split_whatsapp_respects_line_budget():
    text = "\n".join(f"line {i}" for i in range(14))
    chunks = split_whatsapp_text(text, max_lines=6)
    assert len(chunks) >= 2
    assert all(c.count("\n") <= 5 for c in chunks)


def test_claim_beat_transition_idempotent():
    profile = {"conversation_beat": BEAT_1_AWAITING_CONFIRM}
    assert claim_beat_transition(
        profile,
        expected_beats=(BEAT_1_AWAITING_CONFIRM,),
        next_beat=BEAT_2_AWAITING_ADVANCE,
        inbound_id="wamid.1",
    )
    assert profile["conversation_beat"] == BEAT_2_AWAITING_ADVANCE
    profile["conversation_beat"] = BEAT_1_AWAITING_CONFIRM
    assert not claim_beat_transition(
        profile,
        expected_beats=(BEAT_1_AWAITING_CONFIRM,),
        next_beat=BEAT_2_AWAITING_ADVANCE,
        inbound_id="wamid.1",
    )


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
                        "response_json": json.dumps(
                            {
                                "flow_kind": "birth_details",
                                "birth_date": "1990-05-15",
                                "birth_time": "07:25",
                                "unknown_time": [],
                                "birth_place": "jaipur",
                            }
                        )
                    }
                },
            },
        }
        fake_birth = MagicMock()
        BirthDetails = MagicMock(return_value=fake_birth)
        compute_chart = MagicMock(return_value=MIN_CHART)
        with patch.object(mod, "geocode_place", return_value=(26.9, 75.8)), patch.object(
            mod, "timezone_offset_for", return_value=5.5
        ), patch.object(mod, "_kundli", return_value=(BirthDetails, compute_chart)):
            out = await agent.process(data)
        assert profile.get("chart_json")
        assert profile.get("user_language") is None
        assert profile.get("conversation_beat") == "awaiting_language"
        resp = out["bot_response"]
        assert len(resp) == 1 and resp[0]["type"] == "quickreply"
        ids = [o["postbackText"] for o in resp[0]["options"]]
        assert "samara_lang_en" in ids and "samara_lang_hi" in ids

    _run(go())


def test_language_button_triggers_beat1_not_long_reading():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "conversation_beat": "awaiting_language",
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="You feel thoughtful.\nDoes this ring true?"),
        ) as mock_cc:
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.lang1",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": "samara_lang_en", "title": "English"}
                    },
                },
            }
            out = await agent.process(data)
            assert mock_cc.await_args.kwargs.get("model")
        assert profile["user_language"] == "english"
        assert profile["conversation_beat"] == BEAT_1_AWAITING_CONFIRM
        assert profile["free_reading_used"] is True
        assert out["bot_response"][-1]["type"] == "quickreply"
        ids = [o["postbackText"] for o in out["bot_response"][-1]["options"]]
        assert BTN_BEAT1_YES in ids

    _run(go())


def test_duplicate_language_webhook_does_not_regenerate_beat1():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "conversation_beat": "awaiting_language",
        }
        mock_cc = AsyncMock(return_value="Identity line.")
        with patch.object(mod, "complete_chat", new=mock_cc):
            msg = {
                "id": "wamid.dup",
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": "samara_lang_en", "title": "English"}
                },
            }
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": msg,
            }
            await agent.process(data)
            assert mock_cc.await_count == 1
            # Fresh webhook payload (pipeline builds a new data dict each time)
            data2 = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": msg,
            }
            out2 = await agent.process(data2)
            assert mock_cc.await_count == 1
            assert out2["bot_response"][0]["type"] == "skip"

    _run(go())


def test_beat1_confirm_sends_beat2():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_1_AWAITING_CONFIRM,
            "free_reading_used": True,
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="Around age 28-33 a heavy chapter."),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.b1",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_BEAT1_YES, "title": "Haan, bilkul"}
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2_AWAITING_ADVANCE
        assert out["bot_response"][-1]["type"] == "quickreply"
        assert BTN_BEAT2_NEXT in [
            o["postbackText"] for o in out["bot_response"][-1]["options"]
        ]

    _run(go())


def test_beat2_advance_shows_topic_picker():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2_AWAITING_ADVANCE,
            "free_reading_used": True,
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "id": "wamid.b2",
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": BTN_BEAT2_NEXT, "title": "Aage batao"}
                },
            },
        }
        out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
        assert out["bot_response"][0]["type"] == "quickreply"
        assert len(out["bot_response"][0]["options"]) == 3  # Meta max

    _run(go())


def test_topic_choice_sends_free_deep_and_sets_flag():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "user_language": "english",
            "conversation_beat": BEAT_AWAITING_TOPIC,
            "free_reading_used": True,
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(
                return_value=(
                    "Career looks active now.\n"
                    "The open question is when the next shift lands."
                )
            ),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.topic",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_TOPIC_CAREER, "title": "Career"}
                    },
                },
            }
            out = await agent.process(data)
        # Topic pick now collects the user's own items first — still free,
        # still pre-gate (RULE 6): the free deep answer consumes the reply.
        assert profile["chosen_topic"] == "career"
        assert profile["conversation_beat"] == BEAT_AWAITING_ITEMS
        assert profile.get("free_deep_answer_used") is not True
        assert out["bot_response"][-1]["msgid"] == "samara_items_ask"

        # Answering (or skipping) delivers the complete free demo.
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(
                return_value=(
                    "Career looks active now.\n"
                    "The open question is when the next shift lands."
                )
            ),
        ):
            out = await agent.process(
                {
                    "client_id": "samara",
                    "phone_number": "919999900001",
                    "user_profile": profile,
                    "messages": {
                        "id": "wamid.items",
                        "type": "text",
                        "text": {"body": "freelance work, a side project"},
                    },
                }
            )
        assert profile["free_deep_answer_used"] is True
        assert profile["conversation_beat"] == BEAT_POST_FREE_DEEP
        assert profile["user_items"] == ["freelance work", "a side project"]
        assert out["bot_response"][0]["type"] == "text"
        # Complete demo — not cliff-only QR
        assert out["bot_response"][0].get("msgid") != "samara_want_more"

    _run(go())


def test_followup_is_paywalled_after_free_deep():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "english",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "credits": 0,
            "credit_ledger": [],
            "trust_score": 4,
            "trust_scored": True,
            "bot_asked_question": False,
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "type": "text",
                "text": {"body": "what about my career?"},
            },
        }
        out = await agent.process(data)
        assert out["bot_response"][0]["type"] == "quickreply"
        assert profile.get("pending_deep_question")
        joined = out["bot_response"][0]["text"].lower()
        assert "coming soon" not in joined
        assert "last credit" not in joined

    _run(go())


def test_followup_with_credits_answers_and_debts():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chat_history": [],
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "english",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "credits": 2,
            "credit_ledger": [
                {
                    "type": "grant",
                    "amount": 2,
                    "source": "test",
                    "timestamp": 1,
                }
            ],
        }
        with patch.object(
            mod, "complete_chat", new=AsyncMock(return_value="[paid answer]")
        ), patch.object(
            mod,
            "debit_credit",
            return_value={"credits": 1, "credit_ledger": profile["credit_ledger"]},
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "type": "text",
                    "text": {"body": "what about my career?"},
                },
            }
            out = await agent.process(data)
        assert "[paid answer]" in out["bot_response"][0]["text"]

    _run(go())


def test_returning_greeting_shows_continuity_menu():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": MIN_CHART,
            "free_reading_used": True,
            "free_deep_answer_used": True,
            "user_language": "hindi",
            "conversation_beat": BEAT_POST_FREE_DEEP,
            "chosen_topic": "career",
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {"type": "text", "text": {"body": "Namaste"}},
        }
        out = await agent.process(data)
        assert out["bot_response"][0]["type"] == "quickreply"
        titles = [o["title"] for o in out["bot_response"][0]["options"]]
        assert any("Wahi" in t or "baat" in t for t in titles)
        body = out["bot_response"][0]["text"].lower()
        assert "career" in body
        assert "wapas" in body or "pichli" in body

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


def test_beat2a_reject_skips_dates_to_topic():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": DATED_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2A_AWAITING_CONFIRM,
            "free_reading_used": True,
        }
        data = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "id": "wamid.2a.no",
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": BTN_BEAT2A_NO, "title": "Nahi, aisa nahi"}
                },
            },
        }
        out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_TRUST_RECOVERY
        assert out["bot_response"][0]["type"] == "text"
        assert count_gate_messages(out["bot_response"]) == 0

    _run(go())


def test_beat2a_yes_offers_one_dated_window():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": DATED_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2A_AWAITING_CONFIRM,
            "free_reading_used": True,
            "beat2_windows_offered": 0,
            "beat2_offered_starts": [],
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="2011 ke shuruaat ke aas-paas kuch badla tha?"),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.2a.yes",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {
                            "id": BTN_BEAT2A_YES,
                            "title": "Haan, sahi hai",
                        }
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2B_AWAITING_CONFIRM
        assert profile["beat2_windows_offered"] == 1
        assert profile["beat2_pending_window"]["start"] == "2015-09-01"  # newest first
        assert BTN_BEAT2B_YES in [
            o["postbackText"] for o in out["bot_response"][-1]["options"]
        ]
        # Engine label must be injectable — LLM mock is opaque; pending window is source of truth
        assert profile["beat2_pending_window"]["window_label_en"] == "late 2015"

    _run(go())


def test_beat2b_reject_offers_one_alt_then_stops():
    async def go():
        agent = mod.SamaraReadingAgent()
        pending = DATED_CHART["turning_points"][1]
        profile = {
            "username": "Rahul",
            "chart_json": DATED_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2B_AWAITING_CONFIRM,
            "free_reading_used": True,
            "beat2_windows_offered": 1,
            "beat2_offered_starts": [pending["start"]],
            "beat2_pending_window": pending,
            "rejected_windows": [],
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="2011 ke shuruaat — kuch badla?"),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.2b.no1",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_BEAT2B_NO, "title": "Nahi"}
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2B_ALT_AWAITING
        assert len(profile["rejected_windows"]) == 1
        assert profile["beat2_windows_offered"] == 2
        assert profile["beat2_pending_window"]["start"] == "2011-03-15"

        # Second reject → topic, no third window
        data2 = {
            "client_id": "samara",
            "phone_number": "919999900001",
            "user_profile": profile,
            "messages": {
                "id": "wamid.2b.no2",
                "type": "interactive",
                "interactive": {
                    "button_reply": {"id": BTN_BEAT2B_NO, "title": "Nahi"}
                },
            },
        }
        out2 = await agent.process(data2)
        assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
        assert profile["beat2_windows_offered"] == 2
        assert out2["bot_response"][-1]["type"] == "quickreply"

    _run(go())


def test_beat2b_freetext_stores_confirmed_events():
    async def go():
        agent = mod.SamaraReadingAgent()
        pending = DATED_CHART["turning_points"][1]
        profile = {
            "username": "Rahul",
            "chart_json": DATED_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2B_AWAITING_CONFIRM,
            "free_reading_used": True,
            "beat2_windows_offered": 1,
            "beat2_offered_starts": [pending["start"]],
            "beat2_pending_window": pending,
            "confirmed_events": [],
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="Dhanyavaad — woh waqt bhari thi."),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.2b.txt",
                    "type": "text",
                    "text": {"body": "Job chhod di thi us saal"},
                },
            }
            out = await agent.process(data)
        assert len(profile["confirmed_events"]) == 1
        ev = profile["confirmed_events"][0]
        assert "Job chhod" in ev["user_description"]
        assert ev["start_date"] == "2015-09-01"
        assert profile["conversation_beat"] == BEAT_AWAITING_TOPIC
        assert out["bot_response"][-1]["type"] == "quickreply"

    _run(go())


def test_beat1_dated_chart_enters_beat2a():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": DATED_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_1_AWAITING_CONFIRM,
            "free_reading_used": True,
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="Ek soft theme — zimmedari badhi."),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.b1.dated",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_BEAT1_YES, "title": "Haan, bilkul"}
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2A_AWAITING_CONFIRM
        assert BTN_BEAT2A_YES in [
            o["postbackText"] for o in out["bot_response"][-1]["options"]
        ]

    _run(go())


def test_no_time_chart_uses_undated_beat2():
    async def go():
        agent = mod.SamaraReadingAgent()
        profile = {
            "username": "Rahul",
            "chart_json": NO_TIME_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_1_AWAITING_CONFIRM,
            "free_reading_used": True,
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="Around age 28-33 a heavy chapter."),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.b1.notime",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": BTN_BEAT1_YES, "title": "Haan, bilkul"}
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2_AWAITING_ADVANCE
        assert BTN_BEAT2_NEXT in [
            o["postbackText"] for o in out["bot_response"][-1]["options"]
        ]

    _run(go())


def test_beat2b_bare_haan_awaits_detail():
    async def go():
        agent = mod.SamaraReadingAgent()
        pending = DATED_CHART["turning_points"][0]
        profile = {
            "username": "Rahul",
            "chart_json": DATED_CHART,
            "user_language": "hindi",
            "conversation_beat": BEAT_2B_AWAITING_CONFIRM,
            "free_reading_used": True,
            "beat2_pending_window": pending,
            "confirmed_events": [],
        }
        with patch.object(
            mod,
            "complete_chat",
            new=AsyncMock(return_value="Agar share karna ho, bataiye."),
        ):
            data = {
                "client_id": "samara",
                "phone_number": "919999900001",
                "user_profile": profile,
                "messages": {
                    "id": "wamid.2b.yes",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {
                            "id": BTN_BEAT2B_YES,
                            "title": "Haan, hua tha",
                        }
                    },
                },
            }
            out = await agent.process(data)
        assert profile["conversation_beat"] == BEAT_2C_AWAITING_DETAIL
        assert len(profile["confirmed_events"]) == 1
        assert out["bot_response"][0]["type"] == "text"

    _run(go())
