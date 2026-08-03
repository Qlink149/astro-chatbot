import json
import os
import time


def _logger():
    from kisna_chatbot.utils.logger_config import logger

    return logger


DEFAULT_HISTORY_WINDOW = 6  # ~3 turns both sides (user+assistant)


def history_window_size() -> int:
    try:
        from kisna_chatbot.ai.config import get_ai_settings

        return int(get_ai_settings().get("samara_history_window") or DEFAULT_HISTORY_WINDOW)
    except Exception:
        return int(os.getenv("SAMARA_HISTORY_WINDOW", str(DEFAULT_HISTORY_WINDOW)))


def get_recent_history(
    user_profile: dict,
    n: int | None = None,
) -> list[dict]:
    """Return the last n chat turns as [{role, content}, ...]."""
    if n is None:
        n = history_window_size()
    history = user_profile.get("chat_history") or []
    return history[-n:]


def format_recent_history_str(
    user_profile: dict,
    n: int | None = None,
) -> str:
    """Last n turns as a 'Role: content' string for system prompts."""
    turns = get_recent_history(user_profile, n)
    return "\n".join(
        f"{(t.get('role') or '').capitalize()}: {t.get('content', '')}"
        for t in turns
    )


def conversation_summary_text(user_profile: dict) -> str:
    return (user_profile.get("conversation_summary") or "").strip() or "(none)"


def format_prompt_history(user_profile: dict, n: int | None = None) -> str:
    """Rolling summary + recent window for Beat 4 / follow-up prompts."""
    summary = conversation_summary_text(user_profile)
    recent = format_recent_history_str(user_profile, n) or "(no prior turns)"
    return f"earlier_summary:\n{summary}\n\nrecent_turns:\n{recent}"


SUMMARY_PROMPT = """
Summarize older Samara WhatsApp turns for continuity. 3-5 short lines max.
Keep topics the user confirmed, open questions, and user-stated life events only.
Never invent chart facts or life events. Never include another user's data.
Write in the same language mix as the turns (Hindi Roman or English).
"""


async def maybe_refresh_conversation_summary(
    profile: dict,
    *,
    classify_fn=None,
) -> None:
    """Every N turns, fold overflow history into conversation_summary via Haiku."""
    n = history_window_size()
    history = list(profile.get("chat_history") or [])
    if len(history) <= n:
        return
    last_at = int(profile.get("conversation_summary_at_len") or 0)
    if len(history) - last_at < n:
        return
    overflow = history[:-n]
    if not overflow or classify_fn is None:
        return
    blob = "\n".join(
        f"{(t.get('role') or '').capitalize()}: {t.get('content', '')}"
        for t in overflow[-n:]
    )
    prev = conversation_summary_text(profile)
    user_content = f"Previous summary:\n{prev}\n\nOlder turns to fold in:\n{blob}"
    try:
        text = await classify_fn(SUMMARY_PROMPT, user_content)
        if text and text.strip():
            profile["conversation_summary"] = text.strip()[:800]
            profile["conversation_summary_at_len"] = len(history)
    except Exception:
        _logger().exception("conversation_summary refresh failed")


def trim_chat_history(history: list, max_len: int) -> list:
    """Keep only the last max_len entries."""
    if not history or len(history) <= max_len:
        return history
    return history[-max_len:]


def format_assistant(assistant_message, phone_number):
    """Format the assistant message for chat history storage."""
    body = ""
    try:
        for assistant in assistant_message:
            message_type = assistant["type"]

            if message_type == "list":
                body += f"\nSent list - [{assistant.get('list', '')}]"

            elif message_type == "flow":
                body += f"\nSent flow - [{assistant.get('flow', '')}]"

            elif message_type in ("quick_reply", "quickreply"):
                option_titles = ", ".join(
                    opt["title"] for opt in assistant.get("options", [])
                )
                body += f"{assistant.get('text', '')}"
                if option_titles:
                    body += f"\n[Options: {option_titles}]"

            elif message_type == "media":
                captions = [
                    u["caption"]
                    for u in assistant.get("urls", [])
                    if u.get("caption")
                ]
                if captions:
                    body += f"\nShowed product images - {', '.join(captions)}"
                else:
                    body += "\nShowed product images"

            elif message_type == "image_with_cta":
                caption = assistant.get("caption", "")
                cta_url = assistant.get("cta_url", "")
                cta_title = assistant.get("cta_title", "Buy on KISNA")
                # Store only product title (first line), not material/karat/price lines.
                # Full captions bleed material info into the LLM entity extractor context.
                first_line = caption.split("\n")[0].strip("* \n") if caption else ""
                body += f"\n[Product: {first_line}]" if first_line else "\n[Product shown]"
                if cta_url:
                    body += f" [{cta_title} → {cta_url}]"

            elif message_type == "cta_url":
                text = assistant.get("text", "")
                display_text = assistant.get("display_text", "Link")
                url = assistant.get("url", "")
                if text:
                    body += f"\n{text}"
                if url:
                    body += f"\n[Button: {display_text} -> {url}]"

            elif message_type == "text":
                body += f"{assistant.get('text', '')}"

            elif message_type == "skip":
                continue

            else:
                body += f"\nSent {message_type} message"

        return body
    except Exception as e:
        _logger().exception(
            "formatting assistant message failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise


def format_user(user_message, phone_number):
    """Format the user message for chat history storage."""
    try:
        msg_type = user_message.get("type", "")
        if msg_type == "text":
            return user_message["text"]["body"]

        if msg_type == "interactive":
            interactive_type = user_message["interactive"]["type"]
            if interactive_type == "list_reply":
                title = user_message["interactive"]["list_reply"]["title"]
                return f"User Selected - [{title}] from list"
            if interactive_type == "nfm_reply":
                response_json = json.loads(
                    user_message["interactive"]["nfm_reply"]["response_json"]
                )
                body = "Flow Reply - "
                for key, value in response_json.items():
                    body += f"\n{key}: {value}"
                return body
            if interactive_type == "button_reply":
                title = user_message["interactive"]["button_reply"]["title"]
                return f"User Selected - [{title}] from quick reply"

        return str(user_message)
    except Exception as e:
        _logger().exception(
            "formatting user message failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise


def format_chat_history(user, assistant, phone_number, request_id: str | None = None):
    """Format chat history as user/assistant message pairs."""
    try:
        now = int(time.time())
        user_entry = {
            "role": "user",
            "content": format_user(user_message=user, phone_number=phone_number),
            "timestamp": now,
        }
        assistant_entry = {
            "role": "assistant",
            "content": format_assistant(
                assistant_message=assistant, phone_number=phone_number
            ),
            "timestamp": now,
        }
        if request_id:
            user_entry["request_id"] = request_id
            assistant_entry["request_id"] = request_id
        return [user_entry, assistant_entry]
    except Exception as e:
        _logger().exception(
            "formatting chat history failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise
