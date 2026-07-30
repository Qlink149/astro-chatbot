"""Block 3: history window bounds + no context bleed into prompt payload."""
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
os.environ["SAMARA_HISTORY_WINDOW"] = "10"

from kisna_chatbot.main import app  # noqa: F401
from kisna_chatbot.ai.config import refresh_ai_settings

refresh_ai_settings()

from kisna_chatbot.utils.format_chathistory import (
    format_prompt_history,
    format_recent_history_str,
    get_recent_history,
    history_window_size,
)


def test_history_window_default_10():
    assert history_window_size() == 10


def test_50_turn_prompt_bounded_no_bleed():
    profile = {
        "conversation_summary": "User asked about career earlier.",
        "chat_history": [],
    }
    for i in range(50):
        topic = "marriage-secret-topic" if i < 30 else f"money-turn-{i}"
        profile["chat_history"].append(
            {"role": "user", "content": f"Ask about {topic}"}
        )
        profile["chat_history"].append(
            {"role": "assistant", "content": f"Reply about {topic}"}
        )

    recent = get_recent_history(profile)
    assert len(recent) == 10
    blob = format_recent_history_str(profile)
    assert "marriage-secret-topic" not in blob
    assert "money-turn" in blob

    prompt_hist = format_prompt_history(profile)
    # Older topic may live only in summary if we put it there — ensure raw recent
    # window does not contain the early marriage turns.
    assert prompt_hist.count("Ask about") <= 10
    assert "earlier_summary:" in prompt_hist
    assert "User asked about career earlier." in prompt_hist
