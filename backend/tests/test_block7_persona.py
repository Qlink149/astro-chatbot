"""Block 7: Samara persona — feminine self-reference, no masculine self-forms."""
import os
import re

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

from kisna_chatbot.prompts.samara_reading import _SHARED_RULES

FORBIDDEN_MASCULINE_SELF = [
    r"\bdekh raha\b",
    r"\bpadh raha\b",
    r"\bbataunga\b",
    r"\bkarunga\b",
    r"\blikhun?ga\b",
    r"\bsamajh raha\b",
]


def test_shared_rules_no_masculine_self_forms():
    """Ensure _SHARED_RULES mentions masculine self-forms ONLY in the ban list.

    Split _SHARED_RULES into paragraphs. Each paragraph containing a
    forbidden form must also contain 'never' or 'forbidden' or 'ban'.
    """
    rules_lower = _SHARED_RULES.lower()
    paragraphs = rules_lower.split("\n\n")
    for pattern in FORBIDDEN_MASCULINE_SELF:
        for para in paragraphs:
            if re.search(pattern, para, re.IGNORECASE):
                assert any(w in para for w in ("never", "forbidden", "ban")), (
                    f"Forbidden masculine form matching '{pattern}' found "
                    f"outside NEVER context in paragraph:\n{para[:200]}"
                )


def test_shared_rules_has_feminine_forms():
    rules_lower = _SHARED_RULES.lower()
    assert "dekh rahi hoon" in rules_lower
    assert "kahungi" in rules_lower
    assert "bataungi" in rules_lower


def test_shared_rules_brand_name():
    assert "Samara, by Clara" in _SHARED_RULES


def test_user_gender_never_assumed():
    assert "NEVER ASSUME USER" in _SHARED_RULES.upper()
