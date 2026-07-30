"""Block 2: purpose-based Sonnet/Haiku routing."""
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
os.environ["ANTHROPIC_CHAT_MODEL"] = "claude-haiku-test"
os.environ["ANTHROPIC_CHAT_MODEL_SONNET"] = "claude-sonnet-test"
os.environ.pop("ANTHROPIC_CHAT_MODEL_HAIKU", None)

from kisna_chatbot.ai.config import refresh_ai_settings

refresh_ai_settings()

from kisna_chatbot.ai.samara_models import samara_model_for, uses_sonnet
from kisna_chatbot.ai.config import get_ai_settings


def test_sonnet_purposes():
    for p in ("beat1", "beat2", "beat2a", "beat2b", "beat2c", "beat4", "paid_deep"):
        assert uses_sonnet(p)
        primary, fallback = samara_model_for(p)
        assert primary == "claude-sonnet-test"
        assert fallback == "claude-haiku-test"


def test_haiku_purposes():
    for p in ("muhurat", "distress", "intent", "language", "summary"):
        assert not uses_sonnet(p)
        primary, fallback = samara_model_for(p)
        assert primary == "claude-haiku-test"
        assert fallback is None


def test_haiku_env_alias():
    os.environ["ANTHROPIC_CHAT_MODEL_HAIKU"] = "claude-haiku-alias"
    refresh_ai_settings()
    try:
        assert get_ai_settings()["anthropic_chat_model_haiku"] == "claude-haiku-alias"
        primary, _ = samara_model_for("muhurat")
        assert primary == "claude-haiku-alias"
    finally:
        os.environ.pop("ANTHROPIC_CHAT_MODEL_HAIKU", None)
        refresh_ai_settings()
