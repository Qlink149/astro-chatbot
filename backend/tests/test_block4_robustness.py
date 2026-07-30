"""Block 4: free-text parsing, restart preserves credits."""
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

from kisna_chatbot.utils.samara_beats import (
    parse_beat1_confirm,
    parse_yes_no_freetext,
    detect_restart_intent,
    detect_language_switch,
)


def _text_msg(body: str) -> dict:
    return {"type": "text", "text": {"body": body}}


def test_haan_bhai_advances_beat1():
    assert parse_beat1_confirm(_text_msg("haan bhai")) == "yes"


def test_bilkul_advances_beat1():
    assert parse_beat1_confirm(_text_msg("bilkul")) == "yes"


def test_theek_hai_is_yes():
    assert parse_yes_no_freetext("theek hai") == "yes"


def test_yeah_is_yes():
    assert parse_yes_no_freetext("yeah") == "yes"


def test_nahi_yaar_is_no():
    assert parse_yes_no_freetext("nahi yaar") == "no"


def test_nahi_bhai_is_no():
    assert parse_yes_no_freetext("nahi bhai") == "no"


def test_no_thanks_is_no():
    assert parse_yes_no_freetext("no thanks") == "no"


def test_random_text_is_none():
    assert parse_yes_no_freetext("my cat is orange") is None


def test_restart_preserves_credits():
    profile = {
        "credits": 5,
        "credit_ledger": [{"type": "grant", "amount": 10}],
        "chart_json": {"rashi": "Aries"},
        "birth_details": {"date_of_birth": "2000-01-01"},
        "confirmed_events": [{"window_label": "test"}],
        "conversation_beat": "beat1_awaiting_confirm",
        "user_language": "hindi",
        "free_deep_answer_used": True,
    }
    assert detect_restart_intent("start over") is True
    assert detect_restart_intent("dobara shuru") is True
    assert detect_restart_intent("galat details") is True

    for key in (
        "birth_details", "chart_json", "confirmed_events",
        "conversation_beat", "user_language", "free_deep_answer_used",
    ):
        profile.pop(key, None)

    assert profile["credits"] == 5
    assert len(profile["credit_ledger"]) == 1


def test_language_switch_detect():
    assert detect_language_switch("english mein bhejo") == "english"
    assert detect_language_switch("switch to english") == "english"
    assert detect_language_switch("hindi mein") == "hindi"
    assert detect_language_switch("random text") is None
