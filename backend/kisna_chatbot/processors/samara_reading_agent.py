"""Samara jyotishi reading processor — beat-based conversation.

THE GOLDEN RULE: the LLM never calculates the chart. kundli_engine.compute_chart()
produces every number; the LLM only writes the warm interpretation on top.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

from kisna_chatbot.ai import complete_chat
from kisna_chatbot.ai.config import get_ai_settings
from kisna_chatbot.ai.types import AgentName
from kisna_chatbot.processors.abstract_processor import Processor
from kisna_chatbot.prompts.samara_reading import (
    SAMARA_BEAT1_IDENTITY_PROMPT,
    SAMARA_BEAT2_PAST_PROMPT,
    SAMARA_BEAT2A_THEME_PROMPT,
    SAMARA_BEAT2B_DATE_ASK_PROMPT,
    SAMARA_BEAT2C_REFLECT_PROMPT,
    SAMARA_BEAT4_DEEP_PROMPT,
    SAMARA_FOLLOWUP_SYSTEM_PROMPT,
    SAMARA_MUHURAT_PROMPT,
)
from kisna_chatbot.payments.credit_ledger import debit_credit, get_credit_balance
from kisna_chatbot.utils.format_chathistory import (
    format_prompt_history,
    format_recent_history_str,
    maybe_refresh_conversation_summary,
)
from kisna_chatbot.utils.funnel_events import emit_funnel_event
from kisna_chatbot.utils.samara_gate import (
    bump_trust,
    clear_bot_asked_question,
    count_gate_messages,
    decide_gate_action,
    door_gate_body,
    mark_bot_asked_question,
    needs_trust_recovery,
)
from kisna_chatbot.utils.geocode_in import timezone_offset_for
from kisna_chatbot.utils.place_resolve import resolve_place_candidates
from kisna_chatbot.utils.slim_chart import slim_chart_for_beat
from kisna_chatbot.utils.distress import (
    assess_distress,
    crisis_response_text,
    extract_inbound_text,
)
from kisna_chatbot.utils.logger_config import logger
from kisna_chatbot.utils.nasa_copy_guard import (
    APPROVED_NASA_LINEAGE,
    sanitize_nasa_endorsement,
)
from kisna_chatbot.utils.llm_output_guard import strip_llm_meta
from kisna_chatbot.utils.samara_beats import (
    ACK_RE_OFFER_TEXT_EN,
    ACK_RE_OFFER_TEXT_HI,
    ACTIVE_INTRO_BEATS,
    BEAT_1_AWAITING_CONFIRM,
    BEAT_2_AWAITING_ADVANCE,
    BEAT_2A_AWAITING_CONFIRM,
    BEAT_2B_ALT_AWAITING,
    BEAT_2B_AWAITING_CONFIRM,
    BEAT_2C_AWAITING_DETAIL,
    BEAT_AWAITING_LANGUAGE,
    BEAT_AWAITING_NAME,
    BEAT_AWAITING_PLACE_CONFIRM,
    BEAT_AWAITING_PWYW_AMOUNT,
    BEAT_AWAITING_PWYW_CONFIRM,
    BEAT_AWAITING_TOPIC,
    BEAT_POST_FREE_DEEP,
    BEAT_RETURNING_MENU,
    BEAT_TRUST_RECOVERY,
    MAX_DATED_WINDOWS_PER_SESSION,
    TOPIC_LABELS,
    beat1_confirm_buttons,
    beat2_next_button,
    beat2a_confirm_buttons,
    beat2a_quality_points,
    beat2b_confirm_buttons,
    claim_beat_transition,
    dated_anchors_available,
    detect_language_switch,
    detect_restart_intent,
    display_user_name,
    inbound_message_id,
    looks_like_greeting,
    mark_beat_send,
    needs_conversational_name,
    next_turning_point,
    parse_beat1_confirm,
    parse_beat2_advance,
    parse_beat2a_confirm,
    parse_beat2b_confirm,
    parse_paywall_choice,
    parse_pay_intent,
    parse_place_confirm,
    parse_pwyw_confirm,
    parse_returning_choice,
    parse_topic_choice,
    parse_want_more_choice,
    parse_yes_no_freetext,
    paywall_buttons,
    place_confirm_ui,
    is_clear_place_winner,
    is_beat2c_skip_token,
    pwyw_confirm_buttons,
    looks_like_broke_objection,
    relevant_dasha_slice,
    returning_menu_buttons,
    soft_past_range_from_chart,
    strip_exact_dates_from_beat1,
    text_responses,
    topic_label_for,
    topic_picker_buttons,
    want_more_buttons,
)


def _kundli():
    """Lazy import — keeps Vercel cold start from crashing if chart deps fail early."""
    from kundli_engine import BirthDetails, compute_chart

    return BirthDetails, compute_chart


def _now_context(chart: dict | None) -> dict:
    """Today's date + user's current age (birth-anchored). LLM never guesses these."""
    now = datetime.now(timezone.utc)
    meta = (chart or {}).get("meta") or {}
    birth_year = meta.get("birth_year")
    current_age = meta.get("current_age")
    if current_age is None and birth_year:
        current_age = now.year - int(birth_year)
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_year": now.year,
        "current_age": current_age if current_age is not None else "unknown",
    }


def _sonnet_models() -> tuple[str, str]:
    from kisna_chatbot.ai.samara_models import haiku_model_id, sonnet_model_id

    return sonnet_model_id(), haiku_model_id()


_TIME_RE = re.compile(r"^\s*([01]?\d|2[0-3])[:.\s]([0-5]\d)\s*$")
_TEXT_DATE_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")
_TEXT_DATE_ISO_RE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_TEXT_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")

# First-time greeting. NASA line is DATA lineage only — never endorsement.
# META ADS: ad review is stricter than in-chat. Do NOT reuse this NASA lineage
# line verbatim in Meta ad creative without brand/legal review.
GREETING_TEXT_HI = (
    "Namaste 🙏 Main Samara hoon — aapki apni jyotishi.\n"
    f"Aapki asli kundli banaungi, {APPROVED_NASA_LINEAGE}.\n"
    "Bas teen cheezein chahiye 🌙"
)
GREETING_TEXT_EN = (
    "Namaste — I'm Samara, your personal jyotishi.\n"
    f"I'll build your real kundli, {APPROVED_NASA_LINEAGE}.\n"
    "Just three things 🌙"
)
GREETING_TEXT = GREETING_TEXT_EN

NUDGE_TEXT_HI = (
    "Bas ek chhota sa step ✨ — neeche form se date, time aur place "
    "share kar dijiye 🌙"
)
NUDGE_TEXT_EN = (
    "Just one small step ✨ — share date, time, and place in the form below 🌙"
)
NUDGE_TEXT = NUDGE_TEXT_EN

NAME_ASK_TEXT_HI = "Aapko kya bulaun? 🌙"
NAME_ASK_TEXT_EN = "What should I call you? 🌙"

# First-gate / door — never meter consumption language as primary.
PAYWALL_TEXT_HI = (
    "Woh jawab poora hai 🌙 "
    "Chart ke clear windows aur poori tasveer — jab ready ho.\n\n"
    "Jo dena chaho type karo (minimum ₹39), ya Baad mein — bilkul theek hai."
)
PAYWALL_TEXT_EN = (
    "That answer stands on its own 🌙 "
    "The clearer windows and full picture are here when you're ready.\n\n"
    "Type an amount (minimum ₹39), or Later — both are fine."
)
# Back-compat alias (tests / grep); must NOT contain "coming soon" or "last credit".
PAYWALL_TEXT = PAYWALL_TEXT_HI

BTN_PAYWALL_PAY = "samara_paywall_pay"
BTN_PAYWALL_LATER = "samara_paywall_later"

ENOUGH_ACK_HI = (
    "Bilkul theek hai 🙏 Jab ready ho, pay likh dena — "
    "main wahi thread yaad rakhungi."
)
ENOUGH_ACK_EN = (
    "Of course 🙏 When you're ready, type pay — "
    "I'll keep this thread."
)

SOFT_ACK_NUDGE_EN = (
    "Glad that landed. If you want to go deeper on this, tap Want more — "
    "or Enough for now if you'd rather pause."
)
SOFT_ACK_NUDGE_HI = (
    "Achha laga ye sunke. Aur depth chahiye to Want more dabao — "
    "warna Abhi bas se yahin ruk sakte ho."
)

BROKE_TEXT_HI = (
    "Samajh sakti hoon 🙏 Koi rush nahi. Jab ready ho unlock kariye, "
    "ya Baad mein — main yahin hoon."
)
BROKE_TEXT_EN = (
    "I hear you 🙏 No rush. Unlock when you're ready, "
    "or Later — I'm here."
)

CANNED_MUHURAT_HI = (
    "Aaj ka short note ✨ Din calm rakho, bade faisle rush mein mat lo."
)
CANNED_MUHURAT_EN = (
    "Quick note for today ✨ Keep the day calm — don't rush big calls."
)

GEOCODE_FAIL_TEXT = (
    "Hmm, I couldn't find that place 😔 Try being more specific — "
    "e.g. 'Udaipur Rajasthan' or 'Hyderabad Telangana'. 🙏"
)

PLACE_RETYPE_TEXT = (
    "No problem — type the place again a bit more specifically "
    "(e.g. 'Udaipur Rajasthan'). 🌙"
)

PLACE_MAX_ATTEMPTS_TEXT = (
    "Let's pick from the closest matches below — tap one, or type a more "
    "specific place. 🙏"
)

ERROR_TEXT = (
    "Maaf kijiye, abhi kuch gadbad ho gayi 😔 "
    "Thodi der baad phir se try kijiye — main yahin hoon. 🙏"
)

ERROR_TEXT_LLM_TIMEOUT = (
    "Abhi thoda time lag raha hai mujhe sochne mein 😔 "
    "Ek minute baad phir se poochiye — main ready hoon. 🙏"
)

ERROR_TEXT_ENGINE_FAIL = (
    "Maaf kijiye, kundli banate waqt kuch gadbad ho gayi 😔 "
    "Please form dobara bhar kar try kijiye. 🙏"
)

ERROR_TEXT_PAYMENT_LINK = (
    "Maaf kijiye, payment link abhi nahi ban paya 😔 "
    "Thodi der baad 'PAY' likh kar try kijiye. 🙏"
)

LANG_SWITCH_CONFIRM_HI = "Theek hai, ab se Hindi mein baat karungi 🙏"
LANG_SWITCH_CONFIRM_EN = "Sure, I'll write in English from now on 🙏"

RESTART_CONFIRM_TEXT_HI = (
    "Theek hai, purani details clear kar di hain 🙏 "
    "Neeche form se naye birth details bhejiye — phir se fresh start. 🌙"
)
RESTART_CONFIRM_TEXT_EN = (
    "Done — I've cleared your earlier details 🙏 "
    "Send your birth details again via the form below for a fresh start. 🌙"
)

LANG_ASK_TEXT = (
    "🌸 Aapki kundli ready ho gayi hai.\n\n"
    "Reading kis bhasha mein chahiye? Please pick one below.\n"
    "In which language would you like your reading?"
)
LANG_ASK_CAPTION = "Choose one to continue"
LANG_BTN_ENGLISH = "samara_lang_en"
LANG_BTN_HINDI = "samara_lang_hi"


def _language_quickreply_response() -> dict:
    return {
        "type": "quickreply",
        "text": LANG_ASK_TEXT,
        "caption": LANG_ASK_CAPTION,
        "msgid": "samara_language_choice",
        "options": [
            {"type": "text", "title": "English", "postbackText": LANG_BTN_ENGLISH},
            {"type": "text", "title": "Hindi", "postbackText": LANG_BTN_HINDI},
        ],
    }


def _parse_language_choice(messages: dict) -> str | None:
    if not isinstance(messages, dict):
        return None
    mtype = messages.get("type")
    if mtype == "interactive":
        inter = messages.get("interactive") or {}
        br = inter.get("button_reply") or {}
        raw_id = str(br.get("id") or "")
        title = str(br.get("title") or "").strip().lower()
        try:
            parsed = json.loads(raw_id) if raw_id else None
            if isinstance(parsed, dict):
                raw_id = str(parsed.get("msgid") or parsed.get("postbackText") or raw_id)
        except (json.JSONDecodeError, TypeError):
            pass
        if raw_id == LANG_BTN_ENGLISH or title == "english":
            return "english"
        if raw_id == LANG_BTN_HINDI or title == "hindi":
            return "hindi"
    if mtype == "button":
        payload = ((messages.get("button") or {}).get("payload") or "").strip()
        text = ((messages.get("button") or {}).get("text") or "").strip().lower()
        if payload == LANG_BTN_ENGLISH or text == "english":
            return "english"
        if payload == LANG_BTN_HINDI or text == "hindi":
            return "hindi"
    if mtype == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip().lower()
        if body in ("english", "en", "eng", "angrezi"):
            return "english"
        if body in ("hindi", "hi", "हिंदी", "hindi/hinglish", "hinglish"):
            return "hindi"
    return None


def _parse_birth_flow_reply(messages: dict) -> dict | None:
    if not isinstance(messages, dict) or messages.get("type") != "interactive":
        return None
    interactive = messages.get("interactive") or {}
    nfm_reply = interactive.get("nfm_reply")
    if not nfm_reply or "response_json" not in nfm_reply:
        return None
    try:
        flow_data = json.loads(nfm_reply["response_json"])
    except (json.JSONDecodeError, TypeError):
        return None
    token = str(flow_data.get("flow_token") or "")
    if flow_data.get("flow_kind") == "birth_details" or token.startswith("samara_birth"):
        return flow_data
    return None


def _parse_birth_date(raw) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw.isdigit() and len(raw) >= 12:
        dt = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
        return (dt.year, dt.month, dt.day)
    try:
        dt = datetime.strptime(raw[:10], "%Y-%m-%d")
        return (dt.year, dt.month, dt.day)
    except ValueError:
        return None


def _unknown_time_selected(flow_data: dict) -> bool:
    """True when the Flow OptIn / legacy flag says birth time is unknown."""
    raw = flow_data.get("unknown_time")
    if raw is True:
        return True
    if isinstance(raw, (list, tuple)):
        # WhatsApp OptIn often sends ["unknown_time"] when checked.
        return any(str(x).strip().lower() in ("unknown_time", "true", "1") for x in raw)
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes", "unknown_time", "on")
    return False


def _parse_birth_time(flow_data: dict) -> tuple[int, int] | None:
    # Explicit "I don't know" → surya_kundli path (no fabricated noon time).
    if _unknown_time_selected(flow_data):
        return None

    raw_h_in = str(flow_data.get("birth_hour_input") or "").strip()
    raw_m_in = str(flow_data.get("birth_minute_input") or "").strip()
    raw_ampm = str(flow_data.get("birth_ampm") or "").strip().upper()
    if raw_h_in.isdigit() and raw_m_in.isdigit() and raw_ampm in ("AM", "PM"):
        h12, m = int(raw_h_in), int(raw_m_in)
        if 1 <= h12 <= 12 and 0 <= m <= 59:
            if raw_ampm == "AM":
                h24 = 0 if h12 == 12 else h12
            else:
                h24 = 12 if h12 == 12 else h12 + 12
            return (h24, m)

    raw_hour = str(flow_data.get("birth_hour") or "").strip()
    raw_minute = str(flow_data.get("birth_minute") or "").strip()
    if raw_hour.isdigit() and raw_minute.isdigit():
        h, m = int(raw_hour), int(raw_minute)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    raw_time = str(flow_data.get("birth_time") or "").strip().lower()
    match = _TIME_RE.match(raw_time) if raw_time else None
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return None


def _parse_birth_text(text: str) -> dict | None:
    if not text:
        return None
    iso = _TEXT_DATE_ISO_RE.search(text)
    dmy = _TEXT_DATE_RE.search(text)
    if iso:
        date_str = f"{int(iso.group(1)):04d}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d}"
        date_span = iso.span()
    elif dmy:
        date_str = f"{int(dmy.group(3)):04d}-{int(dmy.group(2)):02d}-{int(dmy.group(1)):02d}"
        date_span = dmy.span()
    else:
        return None

    remainder = text[: date_span[0]] + " " + text[date_span[1] :]
    time_match = _TEXT_TIME_RE.search(remainder)
    time_str = ""
    if time_match:
        time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        remainder = (
            remainder[: time_match.span()[0]] + " " + remainder[time_match.span()[1] :]
        )

    place = re.sub(r"[^A-Za-z\s]", " ", remainder)
    place = " ".join(
        w
        for w in place.split()
        if w.lower() not in ("dob", "time", "place", "at", "in", "born")
    ).strip()
    if len(place) < 3:
        return None
    return {
        "flow_kind": "typed_text",
        "birth_date": date_str,
        "birth_time": time_str,
        "birth_place": place,
    }


DAILY_CAP_TEXT_HI = (
    "Aaj ke liye Samara ki generation limit ho gayi hai 🌙 "
    "Kal phir se poochiye — main yahin rahungi. 🙏"
)
DAILY_CAP_TEXT_EN = (
    "Samara has reached today's generation limit 🌙 "
    "Ask me again tomorrow — I'll be right here. 🙏"
)


def _check_daily_gen_cap(profile: dict) -> bool:
    """Return True if daily cap is reached. Increment counter if not."""
    from kisna_chatbot.ai.config import get_ai_settings
    cap = get_ai_settings().get("samara_daily_gen_cap", 40)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if profile.get("daily_gen_day") != today:
        profile["daily_gen_day"] = today
        profile["daily_gen_count"] = 0
    count = int(profile.get("daily_gen_count") or 0)
    if count >= cap:
        return True
    profile["daily_gen_count"] = count + 1
    return False


def _has_completed_free_path(profile: dict) -> bool:
    return bool(
        profile.get("free_deep_answer_used") or profile.get("free_reading_used")
    )


def _is_post_gate_locked(profile: dict) -> bool:
    """Free surface used + no credits → no generative astrology LLM."""
    return bool(
        profile.get("free_deep_answer_used")
        and get_credit_balance(profile) <= 0
    )


def _payment_amount_inr() -> float:
    from kisna_chatbot.payments.service import test_payment_amount_inr

    return test_payment_amount_inr()


def _emit_door_gate(
    data: dict,
    profile: dict,
    phone_number: str,
    *,
    pending: str | None = None,
    body: str | None = None,
) -> dict:
    """Single gate emitter — door framing only; at most one paywall QR."""
    if pending:
        profile["pending_deep_question"] = pending
    emit_funnel_event("gate_shown", phone_number=phone_number)
    amt = _payment_amount_inr()
    text = body or door_gate_body(profile, amount_inr=amt)
    data["bot_response"] = [
        paywall_buttons(lang=_lang(profile), body=text, amount_inr=amt)
    ]
    assert count_gate_messages(data["bot_response"]) <= 1
    return data


def _warm_paywall_body(profile: dict) -> str:
    """Back-compat alias → door body (no meter language)."""
    return door_gate_body(profile, amount_inr=_payment_amount_inr())


def _emit_warm_paywall(
    data: dict, profile: dict, phone_number: str, *, pending: str | None = None
) -> dict:
    return _emit_door_gate(data, profile, phone_number, pending=pending)


def _lang(profile: dict) -> str:
    return profile.get("user_language") or "hindi"


def _confirmed_events_json(profile: dict) -> str:
    events = profile.get("confirmed_events") or []
    return json.dumps(events, ensure_ascii=False) if events else "[]"


def _record_rejected_window(profile: dict, window: dict | None) -> None:
    if not window:
        return
    rejected = list(profile.get("rejected_windows") or [])
    start = str(window.get("start") or "")
    if any(str(r.get("start_date") or "") == start for r in rejected if isinstance(r, dict)):
        return
    rejected.append({
        "start_date": start,
        "window_label": window.get("window_label_en") or window.get("window_label_hi"),
        "rejected_at": int(datetime.now(timezone.utc).timestamp()),
    })
    profile["rejected_windows"] = rejected


def _record_confirmed_event(
    profile: dict, window: dict | None, description: str = ""
) -> None:
    if not window:
        return
    events = list(profile.get("confirmed_events") or [])
    events.append({
        "window_label": (
            window.get("window_label_hi")
            if _lang(profile) != "english"
            else window.get("window_label_en")
        ),
        "start_date": window.get("start"),
        "antar_planet": window.get("antar_planet_en"),
        "user_description": (description or "").strip(),
        "confirmed_at": int(datetime.now(timezone.utc).timestamp()),
    })
    profile["confirmed_events"] = events
    if (description or "").strip():
        emit_funnel_event("event_description_captured")


_DELETE_DATA_PHRASES = frozenset({
    "delete my data", "mera data delete karo", "data delete",
    "delete data", "mera data hatao", "data hatao",
    "remove my data", "erase my data",
})

DATA_DELETED_TEXT_HI = (
    "Aapka data delete kar diya gaya hai 🙏 "
    "Birth details, chart, aur chat history sab hata di gayi hai. "
    "Agar aap phir se shuru karna chahein, toh 'hi' likh dijiye. 🌙"
)
DATA_DELETED_TEXT_EN = (
    "Your data has been deleted 🙏 "
    "Birth details, chart, and chat history have all been removed. "
    "If you'd like to start again, just type 'hi'. 🌙"
)


def _is_delete_data_request(text: str) -> bool:
    t = (text or "").strip().lower().rstrip("!.?")
    return t in _DELETE_DATA_PHRASES


class SamaraReadingAgent(Processor):
    """Beat-based Samara reading flow for client_id=samara."""

    def should_run(self, data: dict) -> bool:
        return "bot_response" not in data and data.get("client_id") == "samara"

    async def process(self, data: dict) -> dict:
        if not self.should_run(data):
            return data

        phone_number = data["phone_number"]
        profile = data["user_profile"]
        profile.setdefault("credits", 0)
        profile.setdefault("free_reading_used", False)
        profile.setdefault("free_deep_answer_used", False)
        profile.setdefault("bot_asked_question", False)
        profile.setdefault("bot_question_context", None)
        profile.setdefault("trust_score", 0)
        profile.setdefault("trust_recovery_attempts", 0)
        profile.setdefault("gate_suppressed_session", False)
        profile.setdefault("in_trust_recovery", False)
        profile.setdefault("paywall_pitch_suppressed", False)
        messages = data.get("messages") or {}
        inbound_id = inbound_message_id(messages)

        # Distress path — BEFORE paywall, beats, or any astrology LLM.
        inbound_text = extract_inbound_text(messages)
        if inbound_text:
            # Post-gate: keyword failsafe only (no Haiku) — still catch self-harm.
            classify_fn = None
            if not _is_post_gate_locked(profile):

                async def _distress_classify(instruction: str, user_text: str) -> str:
                    return await self._llm(
                        instruction=instruction,
                        user_content=user_text,
                        phone_number=phone_number,
                        agent_display_name="SamaraDistress",
                        max_output_tokens=80,
                        purpose="distress",
                    )

                classify_fn = _distress_classify

            flagged = await assess_distress(
                inbound_text, classify_fn=classify_fn
            )
            if flagged.distress:
                emit_funnel_event("distress_flagged", phone_number=phone_number)
                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": crisis_response_text(
                            lang=_lang(profile),
                            self_harm=flagged.self_harm,
                        ),
                    }
                ]
                return data

        # Post-free continue hook (Want more / Enough / soft ack) — even when
        # bot_asked_question is set from the cliff QR.
        if _is_post_gate_locked(profile) and not profile.get("in_trust_recovery"):
            want_early = parse_want_more_choice(messages)
            if want_early == "more":
                clear_bot_asked_question(profile)
                if profile.get("gate_suppressed_session") or profile.get(
                    "paywall_pitch_suppressed"
                ):
                    lang = _lang(profile)
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                "I'm here when you're ready — no rush."
                                if lang == "english"
                                else "Jab ready ho, main yahin hoon — koi rush nahi."
                            ),
                        }
                    ]
                    return data
                action = decide_gate_action(
                    profile, amount_inr=_payment_amount_inr()
                )
                if action.kind == "door":
                    return _emit_door_gate(
                        data,
                        profile,
                        phone_number,
                        pending="want_more",
                        body=action.body,
                    )
                if needs_trust_recovery(profile):
                    return self._enter_trust_recovery(data, profile, phone_number)
                return data
            if want_early == "enough":
                clear_bot_asked_question(profile)
                lang = _lang(profile)
                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": ENOUGH_ACK_EN if lang == "english" else ENOUGH_ACK_HI,
                    }
                ]
                return data
            if want_early == "ack":
                lang = _lang(profile)
                nudge = SOFT_ACK_NUDGE_EN if lang == "english" else SOFT_ACK_NUDGE_HI
                profile["bot_asked_question"] = True
                profile["bot_question_context"] = nudge[-400:]
                data["bot_response"] = [want_more_buttons(lang=lang, body=nudge)]
                return data

        # Task 1: solicited reply — always free, never gate/debit.
        if profile.get("bot_asked_question") and (
            inbound_text
            or (messages.get("type") in ("interactive", "button", "text"))
        ):
            beat_now = profile.get("conversation_beat")
            if beat_now == BEAT_TRUST_RECOVERY and inbound_text:
                return await self._handle_trust_recovery_reply(
                    data, profile, phone_number, inbound_text
                )
            if beat_now not in ACTIVE_INTRO_BEATS and inbound_text:
                return await self._handle_solicited_reply(
                    data, profile, phone_number, inbound_text
                )

        # Exact PAY or natural-language pay intent → PWYW amount ask
        if messages.get("type") == "text":
            text_body = ((messages.get("text") or {}).get("body") or "")
            if text_body.strip() == "PAY" or parse_pay_intent(messages):
                return self._enter_pwyw_amount(data, profile, phone_number)
        elif parse_pay_intent(messages) or parse_paywall_choice(messages) == "pay":
            return self._enter_pwyw_amount(data, profile, phone_number)

        # PWYW amount / large-amount confirm beats
        beat_pay = profile.get("conversation_beat")
        if beat_pay in (BEAT_AWAITING_PWYW_AMOUNT, BEAT_AWAITING_PWYW_CONFIRM):
            return await self._handle_pwyw_beat(
                data, profile, phone_number, messages
            )

        # After door: typed amount without explicit PAY keyword
        if (
            _is_post_gate_locked(profile)
            and not profile.get("bot_asked_question")
            and messages.get("type") == "text"
        ):
            from kisna_chatbot.utils.pwyw_amount import parse_amount_inr

            raw_amt = ((messages.get("text") or {}).get("body") or "").strip()
            if parse_amount_inr(raw_amt) is not None and not looks_like_broke_objection(
                raw_amt
            ):
                profile["conversation_beat"] = BEAT_AWAITING_PWYW_AMOUNT
                return await self._handle_pwyw_beat(
                    data, profile, phone_number, messages
                )

        # Baad mein — graceful exit, schedule one-shot nudge
        if parse_paywall_choice(messages) == "later":
            return self._handle_paywall_later(data, profile, phone_number)

        # Post-gate: free deep used + 0 credits → door gate (unless suppressed/recovery).
        if _is_post_gate_locked(profile) and not profile.get("bot_asked_question"):
            if profile.get("gate_suppressed_session") or profile.get("in_trust_recovery"):
                pass  # fall through — no gate this session
            elif profile.get("paywall_pitch_suppressed"):
                lang = _lang(profile)
                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": (
                            "I'm here when you're ready — no rush."
                            if lang == "english"
                            else "Jab ready ho, main yahin hoon — koi rush nahi."
                        ),
                    }
                ]
                return data
            else:
                want = parse_want_more_choice(messages)
                if want == "more":
                    clear_bot_asked_question(profile)
                    action = decide_gate_action(
                        profile, amount_inr=_payment_amount_inr()
                    )
                    if action.kind == "door":
                        return _emit_door_gate(
                            data, profile, phone_number, pending="want_more", body=action.body
                        )
                    if needs_trust_recovery(profile):
                        return self._enter_trust_recovery(data, profile, phone_number)
                    return data
                if want == "enough":
                    clear_bot_asked_question(profile)
                    lang = _lang(profile)
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": ENOUGH_ACK_EN if lang == "english" else ENOUGH_ACK_HI,
                        }
                    ]
                    return data
                if want == "ack":
                    # Soft ack — re-offer continue hook; do NOT open the door.
                    lang = _lang(profile)
                    nudge = (
                        SOFT_ACK_NUDGE_EN if lang == "english" else SOFT_ACK_NUDGE_HI
                    )
                    profile["bot_asked_question"] = True
                    profile["bot_question_context"] = nudge[-400:]
                    data["bot_response"] = [
                        want_more_buttons(lang=lang, body=nudge)
                    ]
                    return data
                if inbound_text and looks_like_broke_objection(inbound_text):
                    clear_bot_asked_question(profile)
                    action = decide_gate_action(
                        profile, amount_inr=_payment_amount_inr()
                    )
                    if action.kind == "door":
                        return _emit_door_gate(
                            data, profile, phone_number, pending="broke", body=action.body
                        )
                    return data
                ret = parse_returning_choice(messages)
                if ret == "continue" or ret == "new":
                    clear_bot_asked_question(profile)
                    action = decide_gate_action(
                        profile, amount_inr=_payment_amount_inr()
                    )
                    if action.kind == "door":
                        return _emit_door_gate(
                            data, profile, phone_number, pending=ret, body=action.body
                        )
                    if needs_trust_recovery(profile):
                        return self._enter_trust_recovery(data, profile, phone_number)
                    return data
                if ret == "muhurat":
                    lang = _lang(profile)
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                CANNED_MUHURAT_EN
                                if lang == "english"
                                else CANNED_MUHURAT_HI
                            ),
                        }
                    ]
                    return data
                text_body = ""
                if messages.get("type") == "text":
                    text_body = ((messages.get("text") or {}).get("body") or "").strip()
                if text_body and not looks_like_greeting(text_body):
                    # Depth / free-text ask after free demo → door
                    clear_bot_asked_question(profile)
                    if needs_trust_recovery(profile):
                        return self._enter_trust_recovery(data, profile, phone_number)
                    action = decide_gate_action(
                        profile, amount_inr=_payment_amount_inr()
                    )
                    if action.kind == "door":
                        return _emit_door_gate(
                            data,
                            profile,
                            phone_number,
                            pending=text_body,
                            body=action.body,
                        )
                # Greetings / empty → fall through to returning menu

        # ── Language switch (any time) ─────────────────────────────────
        if inbound_text:
            lang_switch = detect_language_switch(inbound_text)
            if lang_switch and profile.get("user_language") and lang_switch != profile.get("user_language"):
                profile["user_language"] = lang_switch
                confirm = LANG_SWITCH_CONFIRM_EN if lang_switch == "english" else LANG_SWITCH_CONFIRM_HI
                data["bot_response"] = [{"type": "text", "text": confirm}]
                return data

        # ── Data deletion (DPDP) ──────────────────────────────────────
        if inbound_text and _is_delete_data_request(inbound_text):
            return self._handle_data_deletion(data, profile, phone_number)

        # ── Restart intent (preserve credits + ledger) ─────────────────
        if inbound_text and detect_restart_intent(inbound_text):
            lang = _lang(profile)
            for key in (
                "birth_details", "chart_json", "confirmed_events",
                "rejected_windows", "beat2_windows_offered",
                "beat2_offered_starts", "beat2_pending_window",
                "conversation_beat", "user_language",
                "free_deep_answer_used", "free_reading_used",
                "open_loop_summary", "chosen_topic",
                "beat_last_inbound_id", "conversation_summary",
                "pending_deep_question",
                "bot_asked_question", "bot_question_context",
                "trust_score", "trust_recovery_attempts",
                "gate_suppressed_session", "in_trust_recovery",
                "paywall_pitch_suppressed",
            ):
                profile.pop(key, None)
            confirm = RESTART_CONFIRM_TEXT_EN if lang == "english" else RESTART_CONFIRM_TEXT_HI
            emit_funnel_event("restart", phone_number=phone_number)
            data["bot_response"] = [
                {"type": "text", "text": confirm},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        # Idempotent: duplicate Gupshup delivery of an already-handled inbound
        # must not advance or regenerate beats.
        if inbound_id and profile.get("beat_last_inbound_id") == inbound_id:
            data["bot_response"] = [{"type": "skip"}]
            return data

        flow_data = _parse_birth_flow_reply(messages)
        if flow_data is not None:
            return await self._handle_birth_details(data, profile, phone_number, flow_data)

        # Place confirmation before chart exists
        if profile.get("conversation_beat") == BEAT_AWAITING_PLACE_CONFIRM:
            return await self._handle_place_confirm(
                data, profile, phone_number, inbound_id, messages
            )

        if not profile.get("chart_json"):
            text_body = ""
            if messages.get("type") == "text":
                text_body = ((messages.get("text") or {}).get("body") or "").strip()
            # Retype place while awaiting confirm (free text without flow)
            if profile.get("pending_birth") and text_body and not _parse_birth_text(text_body):
                return await self._resolve_and_ask_place(
                    data, profile, phone_number, inbound_id, text_body, retype=True
                )
            typed = _parse_birth_text(text_body)
            if typed:
                return await self._handle_birth_details(
                    data, profile, phone_number, typed
                )
            is_new = not profile.get("chat_history")
            emit_funnel_event("birth_flow_opened", phone_number=phone_number)
            # Pre-language: always English. After Hindi is chosen, nudge uses HI.
            greet = GREETING_TEXT_EN
            nudge = (
                NUDGE_TEXT_HI
                if profile.get("user_language") == "hindi"
                else NUDGE_TEXT_EN
            )
            outbound = greet if is_new else nudge
            outbound, _ = sanitize_nasa_endorsement(outbound)
            data["bot_response"] = [
                {"type": "text", "text": outbound},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        # ── Chart ready: language → beats → follow-ups / returning ───────────
        beat = profile.get("conversation_beat")

        if not profile.get("user_language"):
            lang = _parse_language_choice(messages)
            if lang:
                profile["user_language"] = lang
                emit_funnel_event("language_chosen", phone_number=phone_number)
                return await self._after_language_chosen(
                    data, profile, phone_number, inbound_id
                )
            mark_beat_send(profile, BEAT_AWAITING_LANGUAGE)
            data["bot_response"] = [_language_quickreply_response()]
            return data

        # Conversational name capture (no form field) before Beat 1
        if beat == BEAT_AWAITING_NAME:
            return await self._handle_name_reply(
                data, profile, phone_number, inbound_id, messages
            )

        # Mid-intro beat handling
        if beat == BEAT_1_AWAITING_CONFIRM:
            conf = parse_beat1_confirm(messages)
            if conf:
                next_state = (
                    BEAT_2A_AWAITING_CONFIRM
                    if dated_anchors_available(profile.get("chart_json"))
                    else BEAT_2_AWAITING_ADVANCE
                )
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_1_AWAITING_CONFIRM,),
                    next_beat=next_state,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "Mil gaya — thoda intezaar, next part aa raha hai. 🙏"
                            if _lang(profile) != "english"
                            else "Got it — the next part is on its way. 🙏",
                        }
                    ]
                    return data
                emit_funnel_event("beat1_confirmed", phone_number=phone_number)
                if conf == "yes":
                    bump_trust(profile, 2)
                elif conf == "soft":
                    bump_trust(profile, 0)
                else:
                    bump_trust(profile, -2)
                    if needs_trust_recovery(profile):
                        return self._enter_trust_recovery(data, profile, phone_number)
                return await self._send_beat2_entry(
                    data, profile, phone_number, inbound_id, confirm_signal=conf
                )
            # Unrecognised free-text: short ack + re-offer buttons (never silent drop)
            ack = ACK_RE_OFFER_TEXT_EN if _lang(profile) == "english" else ACK_RE_OFFER_TEXT_HI
            data["bot_response"] = [
                beat1_confirm_buttons(ack, lang=_lang(profile), profile=profile)
            ]
            return data

        # ── Dated Beat 2 ladder ─────────────────────────────────────────────
        if beat == BEAT_2A_AWAITING_CONFIRM:
            ans = parse_beat2a_confirm(messages)
            if ans == "yes":
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2A_AWAITING_CONFIRM,),
                    next_beat=BEAT_2B_AWAITING_CONFIRM,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [{"type": "skip"}]
                    return data
                emit_funnel_event("beat_2a_confirmed", phone_number=phone_number)
                bump_trust(profile, 2)
                return await self._send_beat2b(
                    data, profile, phone_number, inbound_id, alt=False
                )
            if ans == "no":
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2A_AWAITING_CONFIRM,),
                    next_beat=BEAT_AWAITING_TOPIC,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [{"type": "skip"}]
                    return data
                emit_funnel_event("beat_2a_rejected", phone_number=phone_number)
                bump_trust(profile, -2)
                if needs_trust_recovery(profile):
                    return self._enter_trust_recovery(data, profile, phone_number)
                warm = (
                    "Har chart alag hota hai — chaliye aage dekhte hain. 🙏"
                    if _lang(profile) != "english"
                    else "Every chart is different — let's look ahead. 🙏"
                )
                data["bot_response"] = [
                    {"type": "text", "text": warm},
                    topic_picker_buttons(lang=_lang(profile)),
                ]
                mark_beat_send(profile, BEAT_AWAITING_TOPIC, inbound_id)
                return data
            ack = ACK_RE_OFFER_TEXT_EN if _lang(profile) == "english" else ACK_RE_OFFER_TEXT_HI
            data["bot_response"] = [
                beat2a_confirm_buttons(ack, lang=_lang(profile), profile=profile)
            ]
            return data

        if beat in (BEAT_2B_AWAITING_CONFIRM, BEAT_2B_ALT_AWAITING):
            result, free_text = parse_beat2b_confirm(messages)
            pending = profile.get("beat2_pending_window")
            if result in ("yes", "text"):
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2B_AWAITING_CONFIRM, BEAT_2B_ALT_AWAITING),
                    next_beat=BEAT_2C_AWAITING_DETAIL,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [{"type": "skip"}]
                    return data
                emit_funnel_event("beat_2b_date_confirmed", phone_number=phone_number)
                bump_trust(profile, 3)
                if free_text.strip():
                    bump_trust(profile, 1)
                _record_confirmed_event(profile, pending, free_text)
                return await self._send_beat2c(
                    data,
                    profile,
                    phone_number,
                    inbound_id,
                    description=free_text,
                    bare_haan=(result == "yes" and not free_text),
                )
            if result == "no":
                emit_funnel_event("beat_2b_date_rejected", phone_number=phone_number)
                bump_trust(profile, -1)
                _record_rejected_window(profile, pending)
                profile["beat2_pending_window"] = None
                offered = int(profile.get("beat2_windows_offered") or 0)
                # At most one alternative after first reject
                if (
                    beat == BEAT_2B_AWAITING_CONFIRM
                    and offered < MAX_DATED_WINDOWS_PER_SESSION
                    and next_turning_point(profile, profile.get("chart_json"))
                ):
                    if not claim_beat_transition(
                        profile,
                        expected_beats=(BEAT_2B_AWAITING_CONFIRM,),
                        next_beat=BEAT_2B_ALT_AWAITING,
                        inbound_id=inbound_id,
                    ):
                        data["bot_response"] = [{"type": "skip"}]
                        return data
                    emit_funnel_event("alt_window_offered", phone_number=phone_number)
                    return await self._send_beat2b(
                        data, profile, phone_number, inbound_id, alt=True
                    )
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2B_AWAITING_CONFIRM, BEAT_2B_ALT_AWAITING),
                    next_beat=BEAT_AWAITING_TOPIC,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [{"type": "skip"}]
                    return data
                warm = (
                    "Theek hai — har zindagi alag hoti hai. Chaliye aage badhein. 🙏"
                    if _lang(profile) != "english"
                    else "That's alright — every life is different. Let's move on. 🙏"
                )
                data["bot_response"] = [
                    {"type": "text", "text": warm},
                    topic_picker_buttons(lang=_lang(profile)),
                ]
                mark_beat_send(profile, BEAT_AWAITING_TOPIC, inbound_id)
                return data
            ack = ACK_RE_OFFER_TEXT_EN if _lang(profile) == "english" else ACK_RE_OFFER_TEXT_HI
            data["bot_response"] = [
                beat2b_confirm_buttons(ack, lang=_lang(profile))
            ]
            return data

        if beat == BEAT_2C_AWAITING_DETAIL:
            # Optional share after bare yes — reflect on real text; skip tokens → topics
            body = ""
            if messages.get("type") == "text":
                body = ((messages.get("text") or {}).get("body") or "").strip()
            if not body:
                # Button / empty → topic picker
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2C_AWAITING_DETAIL,),
                    next_beat=BEAT_AWAITING_TOPIC,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [{"type": "skip"}]
                    return data
                return self._send_topic_picker(data, profile)

            if is_beat2c_skip_token(body):
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2C_AWAITING_DETAIL,),
                    next_beat=BEAT_AWAITING_TOPIC,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [{"type": "skip"}]
                    return data
                return self._send_topic_picker(data, profile)

            # Real share — store + warm reflect + topic picker
            events = list(profile.get("confirmed_events") or [])
            if events and not (events[-1].get("user_description") or "").strip():
                events[-1]["user_description"] = body
                profile["confirmed_events"] = events
                emit_funnel_event(
                    "event_description_captured", phone_number=phone_number
                )
            return await self._send_beat2c(
                data,
                profile,
                phone_number,
                inbound_id,
                description=body,
                bare_haan=False,
            )

        if beat == BEAT_2_AWAITING_ADVANCE:
            if parse_beat2_advance(messages):
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_2_AWAITING_ADVANCE,),
                    next_beat=BEAT_AWAITING_TOPIC,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [topic_picker_buttons(lang=_lang(profile))]
                    return data
                return self._send_topic_picker(data, profile)
            ack = ACK_RE_OFFER_TEXT_EN if _lang(profile) == "english" else ACK_RE_OFFER_TEXT_HI
            data["bot_response"] = [
                beat2_next_button(ack, lang=_lang(profile))
            ]
            return data

        if beat == BEAT_AWAITING_TOPIC:
            topic = parse_topic_choice(messages)
            if topic:
                if needs_trust_recovery(profile):
                    profile["chosen_topic"] = topic
                    return self._enter_trust_recovery(data, profile, phone_number)
                # Another topic deep after free surface needs credits (no 2nd free LLM).
                if profile.get("free_deep_answer_used"):
                    if get_credit_balance(profile) <= 0:
                        if profile.get("gate_suppressed_session"):
                            profile["chosen_topic"] = topic
                            label = TOPIC_LABELS.get(topic, topic)
                            return await self._handle_followup_with_question(
                                data,
                                profile,
                                phone_number,
                                question=f"Deep reading on {label}.",
                            )
                        profile["chosen_topic"] = topic
                        return _emit_door_gate(
                            data, profile, phone_number, pending=f"topic:{topic}"
                        )
                    profile["chosen_topic"] = topic
                    label = TOPIC_LABELS.get(topic, topic)
                    return await self._handle_followup_with_question(
                        data,
                        profile,
                        phone_number,
                        question=f"Deep directive on {label} — what should I focus on now?",
                    )
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_AWAITING_TOPIC,),
                    next_beat=BEAT_POST_FREE_DEEP,
                    inbound_id=inbound_id,
                ):
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "Topic mil gaya — jawab aa raha hai. 🙏"
                            if _lang(profile) != "english"
                            else "Got your topic — answer on the way. 🙏",
                        }
                    ]
                    return data
                profile["chosen_topic"] = topic
                emit_funnel_event(
                    "topic_chosen",
                    phone_number=phone_number,
                    extra={"topic": topic},
                )
                return await self._send_beat4(data, profile, phone_number, topic)
            data["bot_response"] = [topic_picker_buttons(lang=_lang(profile))]
            return data

        # Returning users / post free-deep
        if _has_completed_free_path(profile) and beat not in ACTIVE_INTRO_BEATS:
            ret = parse_returning_choice(messages)
            if ret == "continue":
                return await self._resume_open_loop(data, profile, phone_number)
            if ret == "new":
                mark_beat_send(profile, BEAT_AWAITING_TOPIC, inbound_id)
                return self._send_topic_picker(data, profile)
            if ret == "muhurat":
                return await self._send_muhurat(data, profile, phone_number)

            text_body = ""
            if messages.get("type") == "text":
                text_body = ((messages.get("text") or {}).get("body") or "").strip()

            # Continuity menu on greetings; real questions go to follow-up
            if looks_like_greeting(text_body) or not text_body:
                mark_beat_send(profile, BEAT_RETURNING_MENU, inbound_id)
                lang = _lang(profile)
                data["bot_response"] = [
                    returning_menu_buttons(
                        lang=lang,
                        name=display_user_name(profile),
                        last_topic_label=topic_label_for(
                            topic_key=profile.get("chosen_topic"),
                            lang=lang,
                        )
                        or None,
                    )
                ]
                return data

            return await self._handle_followup(data, profile, phone_number)

        # Language set but beats not started (e.g. crash mid-way) → Beat 1
        if beat in (None, BEAT_AWAITING_LANGUAGE) and not _has_completed_free_path(
            profile
        ):
            return await self._send_beat1(data, profile, phone_number, inbound_id)

        return await self._handle_followup(data, profile, phone_number)

    # ── Beats ────────────────────────────────────────────────────────────────

    async def _llm(
        self,
        *,
        instruction: str,
        user_content: str,
        phone_number: str,
        agent_display_name: str,
        max_output_tokens: int,
        purpose: str = "beat1",
        use_sonnet: bool | None = None,
        profile: dict | None = None,
        archetype_prefer: str | None = None,
    ) -> str:
        import os

        from kisna_chatbot.ai.samara_models import samara_model_for
        from kisna_chatbot.utils.samara_variety import (
            choose_archetype,
            record_outbound_variety,
            variety_prompt_block,
        )
        from kisna_chatbot.utils.samara_focus import focus_prompt_block

        if use_sonnet is not None:
            purpose = "beat1" if use_sonnet else "muhurat"
        primary, fallback = samara_model_for(purpose)  # type: ignore[arg-type]

        reading_purposes = {
            "beat1",
            "beat2",
            "beat2a",
            "beat2b",
            "beat2c",
            "beat4",
            "paid_deep",
            "followup",
            "solicited",
        }
        temperature = None
        final_instruction = instruction
        chosen_arch = None
        if purpose in reading_purposes:
            try:
                temperature = float(os.getenv("SAMARA_CHAT_TEMPERATURE", "0.9"))
            except ValueError:
                temperature = 0.9
            if profile is not None:
                chosen_arch = choose_archetype(
                    profile, prefer=archetype_prefer  # type: ignore[arg-type]
                )
                final_instruction = (
                    instruction
                    + "\n\n"
                    + focus_prompt_block(profile)
                    + "\n\n"
                    + variety_prompt_block(profile, chosen_arch)
                )

        kwargs = {
            "agent": AgentName.GENERAL,
            "agent_display_name": agent_display_name,
            "instruction": final_instruction,
            "messages": [{"role": "user", "content": user_content}],
            "max_output_tokens": max_output_tokens,
            "phone_number": phone_number,
            "client_id": "samara",
            "model": primary,
            "temperature": temperature,
            "purpose": purpose,
        }
        if fallback:
            kwargs["model_fallback"] = fallback
        text = await complete_chat(**kwargs)
        clean, violated = sanitize_nasa_endorsement(text)
        if violated:
            logger.warning(
                "nasa endorsement scrubbed from LLM output",
                extra={
                    "phone_number": phone_number,
                    "agent": agent_display_name,
                },
            )
        clean = strip_llm_meta(clean)
        if profile is not None and chosen_arch is not None:
            record_outbound_variety(profile, clean, chosen_arch)
            from kisna_chatbot.utils.samara_focus import update_focus_after_bot

            update_focus_after_bot(profile, text=clean)
        return clean

    async def _after_language_chosen(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
    ) -> dict:
        if needs_conversational_name(profile):
            lang = _lang(profile)
            ask = NAME_ASK_TEXT_EN if lang == "english" else NAME_ASK_TEXT_HI
            mark_beat_send(profile, BEAT_AWAITING_NAME, inbound_id)
            data["bot_response"] = [{"type": "text", "text": ask}]
            return data
        return await self._send_beat1(data, profile, phone_number, inbound_id)

    async def _handle_name_reply(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        messages: dict,
    ) -> dict:
        text_body = ""
        if isinstance(messages, dict) and messages.get("type") == "text":
            text_body = ((messages.get("text") or {}).get("body") or "").strip()
        # Reject empty / language-button echoes; re-ask.
        if not text_body or len(text_body) > 40:
            lang = _lang(profile)
            ask = NAME_ASK_TEXT_EN if lang == "english" else NAME_ASK_TEXT_HI
            data["bot_response"] = [{"type": "text", "text": ask}]
            return data
        # Light clean — first token / short phrase only
        name = re.sub(r"[^A-Za-z\u0900-\u097F\s.'-]", "", text_body).strip()
        name = " ".join(name.split())[:30]
        if not name or name.lower() in ("dost", "hi", "hello", "namaste"):
            lang = _lang(profile)
            ask = NAME_ASK_TEXT_EN if lang == "english" else NAME_ASK_TEXT_HI
            data["bot_response"] = [{"type": "text", "text": ask}]
            return data
        profile["preferred_name"] = name
        return await self._send_beat1(data, profile, phone_number, inbound_id)

    def _enforce_daily_cap(self, data: dict, profile: dict, phone_number: str) -> bool:
        """Return True and set bot_response if daily cap hit. Distress always allowed."""
        if _check_daily_gen_cap(profile):
            emit_funnel_event("daily_cap_hit", phone_number=phone_number)
            cap_text = DAILY_CAP_TEXT_EN if _lang(profile) == "english" else DAILY_CAP_TEXT_HI
            data["bot_response"] = [{"type": "text", "text": cap_text}]
            return True
        return False

    async def _send_beat1(
        self, data: dict, profile: dict, phone_number: str, inbound_id: str
    ) -> dict:
        # Idempotent: already sent beat1 for this inbound
        if (
            inbound_id
            and profile.get("beat_last_inbound_id") == inbound_id
            and profile.get("conversation_beat") == BEAT_1_AWAITING_CONFIRM
        ):
            data["bot_response"] = [{"type": "skip"}]
            return data

        if self._enforce_daily_cap(data, profile, phone_number):
            return data

        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        soft_range = soft_past_range_from_chart(chart)
        instruction = SAMARA_BEAT1_IDENTITY_PROMPT.format(
            chart_json=json.dumps(slim_chart_for_beat(chart, "beat1"), ensure_ascii=False),
            user_name=display_user_name(profile),
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
            soft_past_range_json=json.dumps(soft_range, ensure_ascii=False),
            confirmed_events_json=_confirmed_events_json(profile),
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 1 identity now.",
                phone_number=phone_number,
                agent_display_name="SamaraBeat1",
                max_output_tokens=400,
                purpose="beat1",
                profile=profile,
            )
        except Exception:
            logger.exception("Beat1 LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        text, exact_hit = strip_exact_dates_from_beat1(text)
        if exact_hit:
            logger.warning(
                "Beat1 exact calendar day stripped",
                extra={"phone_number": phone_number},
            )

        chunks = text_responses(text)
        # Attach confirm buttons to the last text chunk
        if chunks:
            last = chunks[-1]["text"]
            chunks = chunks[:-1] + [
                beat1_confirm_buttons(last, lang=lang, profile=profile)
            ]
        else:
            chunks = [beat1_confirm_buttons(text, lang=lang, profile=profile)]

        mark_beat_send(profile, BEAT_1_AWAITING_CONFIRM, inbound_id)
        # Compat for dashboard "readings delivered"
        profile["free_reading_used"] = True
        profile["reading_delivered_at"] = int(datetime.now(timezone.utc).timestamp())
        emit_funnel_event("beat1_sent", phone_number=phone_number)
        data["bot_response"] = chunks
        return data

    async def _send_beat2_entry(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        *,
        confirm_signal: str,
    ) -> dict:
        chart = profile.get("chart_json")
        if dated_anchors_available(chart) and beat2a_quality_points(chart):
            return await self._send_beat2a(data, profile, phone_number, inbound_id)
        # Skip weak/fortune-cookie 2a — undated Beat 2 or topic if no dated material
        if dated_anchors_available(chart) and not beat2a_quality_points(chart):
            # Still have dated ladder via 2b if TPs exist without age quality
            if next_turning_point(profile, chart):
                return await self._send_beat2b(
                    data, profile, phone_number, inbound_id, alt=False
                )
        return await self._send_beat2(
            data, profile, phone_number, inbound_id, confirm_signal=confirm_signal
        )

    async def _send_beat2(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        *,
        confirm_signal: str,
    ) -> dict:
        """Undated Beat 2 fallback (no dated_anchors_available)."""
        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        relevant = relevant_dasha_slice(chart)
        instruction = SAMARA_BEAT2_PAST_PROMPT.format(
            chart_json=json.dumps(slim_chart_for_beat(chart, "beat2"), ensure_ascii=False),
            relevant_dasha_json=json.dumps(relevant, ensure_ascii=False),
            user_name=display_user_name(profile),
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
            confirm_signal=confirm_signal,
            confirmed_events_json=_confirmed_events_json(profile),
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 2 past proof now.",
                phone_number=phone_number,
                agent_display_name="SamaraBeat2",
                max_output_tokens=500,
                purpose="beat2",
                profile=profile,
            )
        except Exception:
            logger.exception("Beat2 LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        chunks = text_responses(text)
        if chunks:
            last = chunks[-1]["text"]
            chunks = chunks[:-1] + [beat2_next_button(last, lang=lang)]
        else:
            chunks = [beat2_next_button(text, lang=lang)]

        mark_beat_send(profile, BEAT_2_AWAITING_ADVANCE, inbound_id)
        emit_funnel_event("beat2_sent", phone_number=phone_number)
        data["bot_response"] = chunks
        return data

    async def _send_beat2a(
        self, data: dict, profile: dict, phone_number: str, inbound_id: str
    ) -> dict:
        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        themes = beat2a_quality_points(chart)
        if not themes:
            return await self._send_beat2(
                data, profile, phone_number, inbound_id, confirm_signal="soft"
            )
        instruction = SAMARA_BEAT2A_THEME_PROMPT.format(
            user_name=display_user_name(profile),
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
            themes_json=json.dumps(themes, ensure_ascii=False),
            confirmed_events_json=_confirmed_events_json(profile),
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 2a soft theme now (no dates).",
                phone_number=phone_number,
                agent_display_name="SamaraBeat2a",
                max_output_tokens=400,
                purpose="beat2a",
                profile=profile,
            )
        except Exception:
            logger.exception("Beat2a LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        chunks = text_responses(text)
        if chunks:
            last = chunks[-1]["text"]
            chunks = chunks[:-1] + [
                beat2a_confirm_buttons(last, lang=lang, profile=profile)
            ]
        else:
            chunks = [beat2a_confirm_buttons(text, lang=lang, profile=profile)]

        # Reset per-chart-session window counters for a fresh dated ladder
        profile["beat2_windows_offered"] = 0
        profile["beat2_offered_starts"] = []
        profile["beat2_pending_window"] = None
        mark_beat_send(profile, BEAT_2A_AWAITING_CONFIRM, inbound_id)
        emit_funnel_event("beat_2a_sent", phone_number=phone_number)
        data["bot_response"] = chunks
        return data

    async def _send_beat2b(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        *,
        alt: bool,
    ) -> dict:
        chart = profile.get("chart_json")
        lang = _lang(profile)
        window = next_turning_point(profile, chart)
        if not window:
            mark_beat_send(profile, BEAT_AWAITING_TOPIC, inbound_id)
            warm = (
                "Chaliye aage dekhte hain. 🙏"
                if lang != "english"
                else "Let's look ahead. 🙏"
            )
            data["bot_response"] = [
                {"type": "text", "text": warm},
                topic_picker_buttons(lang=lang),
            ]
            return data

        start = str(window.get("start") or "")
        offered_starts = list(profile.get("beat2_offered_starts") or [])
        if start and start not in offered_starts:
            offered_starts.append(start)
        profile["beat2_offered_starts"] = offered_starts
        profile["beat2_windows_offered"] = int(
            profile.get("beat2_windows_offered") or 0
        ) + 1
        profile["beat2_pending_window"] = window

        instruction = SAMARA_BEAT2B_DATE_ASK_PROMPT.format(
            user_name=display_user_name(profile),
            user_language=lang,
            window_label_month_en=(
                window.get("window_label_month_en")
                or window.get("window_label_en")
                or ""
            ),
            window_label_month_hi=(
                window.get("window_label_month_hi")
                or window.get("window_label_hi")
                or ""
            ),
            theme_en=window.get("theme_en") or "",
            theme_hi=window.get("theme_hi") or "",
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 2b dated ask now (ask only).",
                phone_number=phone_number,
                agent_display_name="SamaraBeat2b",
                max_output_tokens=400,
                purpose="beat2b",
                profile=profile,
                archetype_prefer="question",
            )
        except Exception:
            logger.exception("Beat2b LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        chunks = text_responses(text)
        if chunks:
            last = chunks[-1]["text"]
            chunks = chunks[:-1] + [beat2b_confirm_buttons(last, lang=lang)]
        else:
            chunks = [beat2b_confirm_buttons(text, lang=lang)]

        next_beat = BEAT_2B_ALT_AWAITING if alt else BEAT_2B_AWAITING_CONFIRM
        mark_beat_send(profile, next_beat, inbound_id)
        emit_funnel_event("beat_2b_date_offered", phone_number=phone_number)
        from kisna_chatbot.utils.samara_focus import update_focus_after_bot

        month_lab = (
            window.get("window_label_month_en") or window.get("window_label_en") or ""
        )
        update_focus_after_bot(
            profile,
            text=text,
            claim=f"turning point around {month_lab}".strip(),
            dates=[start] if start else None,
            awaiting="confirmation_of_dated_anchor",
        )
        data["bot_response"] = chunks
        return data

    async def _send_beat2c(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        *,
        description: str,
        bare_haan: bool,
    ) -> dict:
        lang = _lang(profile)
        pending = profile.get("beat2_pending_window") or {}
        if lang != "english":
            window_label = (
                pending.get("window_label_month_hi")
                or pending.get("window_label_hi")
                or ""
            )
        else:
            window_label = (
                pending.get("window_label_month_en")
                or pending.get("window_label_en")
                or ""
            )
        theme = (
            pending.get("theme_hi") if lang != "english" else pending.get("theme_en")
        ) or ""
        # Optional second month-level window from remaining turning points
        optional_month = ""
        chart = profile.get("chart_json") or {}
        pending_start = str(pending.get("start") or "")
        for tp in chart.get("turning_points") or []:
            if not isinstance(tp, dict):
                continue
            if str(tp.get("start") or "") == pending_start:
                continue
            optional_month = (
                tp.get("window_label_month_hi")
                if lang != "english"
                else tp.get("window_label_month_en")
            ) or ""
            if optional_month:
                break
        instruction = SAMARA_BEAT2C_REFLECT_PROMPT.format(
            user_name=display_user_name(profile),
            user_language=lang,
            window_label=window_label,
            theme=theme,
            user_description=description or "",
            optional_window_label=optional_month,
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 2c reflect now.",
                phone_number=phone_number,
                agent_display_name="SamaraBeat2c",
                max_output_tokens=400,
                purpose="beat2c",
                profile=profile,
            )
        except Exception:
            logger.exception("Beat2c LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        chunks = text_responses(text)
        if bare_haan:
            # Soft invite already in LLM text; keep pending window for follow-up reflect
            mark_beat_send(profile, BEAT_2C_AWAITING_DETAIL, inbound_id)
            data["bot_response"] = chunks
            return data

        profile["beat2_pending_window"] = None
        # Free-text already captured — advance to topic picker
        mark_beat_send(profile, BEAT_AWAITING_TOPIC, inbound_id)
        offer = self._maybe_test_me_offer(profile)
        data["bot_response"] = chunks
        if offer:
            data["bot_response"] = chunks + [{"type": "text", "text": offer}]
        data["bot_response"] = data["bot_response"] + [
            topic_picker_buttons(lang=lang)
        ]
        return data

    def _maybe_test_me_offer(self, profile: dict) -> str | None:
        """Once per session after a confirmed dated anchor."""
        if profile.get("test_me_offered") or profile.get("test_me_used"):
            return None
        if not (profile.get("confirmed_events") or profile.get("beat2_offered_starts")):
            return None
        profile["test_me_offered"] = True
        lang = _lang(profile)
        if lang == "english":
            return (
                "If you want, name another year — I'll tell you what was running "
                "in your chart then. (No guessing what happened.)"
            )
        return (
            "Koi aur saal poochiye — main bataungi us waqt kya chal raha tha. "
            "(Kya hua, woh main claim nahi karti.)"
        )

    def _send_topic_picker(self, data: dict, profile: dict) -> dict:
        mark_beat_send(profile, BEAT_AWAITING_TOPIC)
        data["bot_response"] = [topic_picker_buttons(lang=_lang(profile))]
        return data

    async def _send_beat4(
        self, data: dict, profile: dict, phone_number: str, topic: str
    ) -> dict:
        if self._enforce_daily_cap(data, profile, phone_number):
            return data

        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        history_snippet = format_prompt_history(profile) or "(no prior turns)"
        label = TOPIC_LABELS.get(topic, topic)
        instruction = SAMARA_BEAT4_DEEP_PROMPT.format(
            chart_json=json.dumps(slim_chart_for_beat(chart, "beat4"), ensure_ascii=False),
            user_name=display_user_name(profile),
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
            topic_key=topic,
            topic_label=label,
            chat_history_snippet=history_snippet,
            confirmed_events_json=_confirmed_events_json(profile),
            turning_points_json=json.dumps(
                (chart or {}).get("turning_points") or [], ensure_ascii=False
            ),
            upcoming_periods_json=json.dumps(
                (chart or {}).get("upcoming_periods") or [], ensure_ascii=False
            ),
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content=f"Write the free deep answer for topic: {label}",
                phone_number=phone_number,
                agent_display_name="SamaraBeat4",
                max_output_tokens=600,
                purpose="beat4",
                profile=profile,
            )
        except Exception:
            logger.exception("Beat4 LLM failed", extra={"phone_number": phone_number})
            # Roll beat back so they can re-pick topic
            profile["conversation_beat"] = BEAT_AWAITING_TOPIC
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        profile["free_deep_answer_used"] = True
        profile["free_reading_used"] = True
        profile["open_loop_summary"] = text[-400:] if text else ""
        profile["conversation_beat"] = BEAT_POST_FREE_DEEP
        emit_funnel_event("free_deep_answer_sent", phone_number=phone_number)
        lang = _lang(profile)
        hook = (
            "Want to go deeper on this, or pause here?"
            if lang == "english"
            else "Ispe aur depth chahiye, ya yahin rukna hai?"
        )
        # Keep gate from firing on the next soft reply
        profile["bot_asked_question"] = True
        profile["bot_question_context"] = hook[-400:]
        data["bot_response"] = text_responses(text) + [
            want_more_buttons(lang=lang, body=hook)
        ]
        return data

    async def _send_muhurat(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        instruction = SAMARA_MUHURAT_PROMPT.format(
            chart_json=json.dumps(slim_chart_for_beat(chart, "muhurat"), ensure_ascii=False),
            user_name=display_user_name(profile),
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write today's muhurat note.",
                phone_number=phone_number,
                agent_display_name="SamaraMuhurat",
                max_output_tokens=350,
                purpose="muhurat",
            )
        except Exception:
            logger.exception("Muhurat LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data
        profile["conversation_beat"] = BEAT_POST_FREE_DEEP
        data["bot_response"] = text_responses(text)
        return data

    async def _resume_open_loop(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        if _is_post_gate_locked(profile):
            return _emit_warm_paywall(
                data, profile, phone_number, pending="continue"
            )
        loop = (profile.get("open_loop_summary") or "").strip()
        topic = profile.get("chosen_topic")
        if loop and topic:
            # Continue the prior deep thread as a follow-up
            data_messages = data.get("messages") or {}
            if data_messages.get("type") != "text":
                data["messages"] = {
                    "type": "text",
                    "text": {
                        "body": f"Continue from the open question about {TOPIC_LABELS.get(topic, topic)}."
                    },
                }
            return await self._handle_followup(data, profile, phone_number)
        mark_beat_send(profile, BEAT_AWAITING_TOPIC)
        return self._send_topic_picker(data, profile)

    def _enter_pwyw_amount(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        from kisna_chatbot.utils.pwyw_amount import format_inr, min_payment_inr

        lang = _lang(profile)
        min_s = format_inr(min_payment_inr())
        profile["conversation_beat"] = BEAT_AWAITING_PWYW_AMOUNT
        profile.pop("pending_pwyw_amount", None)
        if lang == "english":
            body = (
                f"Pay what you want — minimum ₹{min_s}. "
                f"Type an amount (e.g. {min_s} or 99)."
            )
        else:
            body = (
                f"Jo dena chaho — minimum ₹{min_s}. "
                f"Amount type karo (jaise {min_s} ya 99)."
            )
        data["bot_response"] = [
            paywall_buttons(lang=lang, body=body, amount_inr=min_payment_inr())
        ]
        emit_funnel_event("pwyw_amount_asked", phone_number=phone_number)
        return data

    async def _handle_pwyw_beat(
        self, data: dict, profile: dict, phone_number: str, messages: dict
    ) -> dict:
        if parse_paywall_choice(messages) == "later":
            return self._handle_paywall_later(data, profile, phone_number)

        beat = profile.get("conversation_beat")
        if beat == BEAT_AWAITING_PWYW_CONFIRM:
            choice = parse_pwyw_confirm(messages)
            if choice == "yes":
                amount = float(profile.get("pending_pwyw_amount") or 0)
                if amount <= 0:
                    return self._enter_pwyw_amount(data, profile, phone_number)
                return await self._create_pwyw_payment_link(
                    data, profile, phone_number, amount
                )
            if choice == "no":
                return self._enter_pwyw_amount(data, profile, phone_number)
            # Unclear — re-show confirm
            amount = float(profile.get("pending_pwyw_amount") or 0)
            return self._ask_pwyw_large_confirm(data, profile, amount)

        from kisna_chatbot.utils.pwyw_amount import check_amount, format_inr, min_payment_inr

        raw = ""
        if messages.get("type") == "text":
            raw = ((messages.get("text") or {}).get("body") or "").strip()
        if not raw and isinstance(messages, dict):
            # Button title fallback (legacy pay labels)
            interactive = messages.get("interactive") or messages.get("button") or {}
            if isinstance(interactive, dict):
                raw = str(
                    interactive.get("title")
                    or interactive.get("text")
                    or (interactive.get("button_reply") or {}).get("title")
                    or ""
                ).strip()
            list_reply = (messages.get("interactive") or {}).get("list_reply") or {}
            if not raw and isinstance(list_reply, dict):
                raw = str(list_reply.get("title") or "").strip()

        checked = check_amount(raw)
        lang = _lang(profile)
        min_s = format_inr(min_payment_inr())

        if checked.verdict == "unparseable":
            body = (
                f"I didn't catch the amount — try something like {min_s} or ₹99."
                if lang == "english"
                else f"Amount samajh nahi aaya — jaise {min_s} ya ₹99 type karo."
            )
            data["bot_response"] = [{"type": "text", "text": body}]
            return data

        if checked.verdict == "under_min":
            body = (
                f"Minimum is ₹{min_s} — type that or a little more when you're ready."
                if lang == "english"
                else f"Minimum ₹{min_s} hai — utna ya thoda zyada type karo."
            )
            data["bot_response"] = [{"type": "text", "text": body}]
            return data

        amount = float(checked.amount_inr or 0)
        if checked.verdict == "needs_confirm":
            profile["pending_pwyw_amount"] = amount
            return self._ask_pwyw_large_confirm(data, profile, amount)

        return await self._create_pwyw_payment_link(
            data, profile, phone_number, amount
        )

    def _ask_pwyw_large_confirm(
        self, data: dict, profile: dict, amount: float
    ) -> dict:
        from kisna_chatbot.utils.pwyw_amount import credits_for_amount, format_inr

        lang = _lang(profile)
        amt = format_inr(amount)
        credits = credits_for_amount(amount)
        profile["conversation_beat"] = BEAT_AWAITING_PWYW_CONFIRM
        profile["pending_pwyw_amount"] = amount
        if lang == "english":
            body = f"₹{amt} — is that right? That unlocks about {credits} deep answers."
        else:
            body = f"₹{amt} — sahi hai? Isse lagbhag {credits} deep sawaal milenge."
        data["bot_response"] = [pwyw_confirm_buttons(lang=lang, body=body)]
        return data

    async def _create_pwyw_payment_link(
        self, data: dict, profile: dict, phone_number: str, amount: float
    ) -> dict:
        try:
            from kisna_chatbot.payments.razorpay_client import keys_configured
            from kisna_chatbot.payments.service import (
                create_and_store_payment_link,
                make_samara_order_id,
            )
            from kisna_chatbot.utils.pwyw_amount import credits_for_amount, format_inr

            if not keys_configured():
                raise RuntimeError(
                    "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET missing on this deployment"
                )

            credits = credits_for_amount(amount)
            order_id = make_samara_order_id(phone_number)
            customer_name = (
                profile.get("username") or profile.get("name") or "Samara user"
            )
            result = create_and_store_payment_link(
                order_id=order_id,
                amount_in_rupees=amount,
                currency="INR",
                customer={
                    "name": str(customer_name)[:100],
                    "contact": phone_number,
                },
                notes={
                    "client_id": "samara",
                    "phone_number": phone_number,
                    "source": "whatsapp_pwyw",
                    "expected_credits": str(credits),
                },
                phone_number=phone_number,
                client_id="samara",
                description=f"Samara credits — ₹{format_inr(amount)}",
            )
            profile["conversation_beat"] = BEAT_POST_FREE_DEEP
            profile.pop("pending_pwyw_amount", None)
            amount_display = format_inr(amount)
            emit_funnel_event("pay_link_created", phone_number=phone_number)
            data["bot_response"] = [
                {
                    "type": "cta_url",
                    "text": (
                        f"Click below to pay ₹{amount_display} — "
                        f"{credits} deep chart answers."
                        if _lang(profile) == "english"
                        else (
                            f"Neeche se ₹{amount_display} complete kariye — "
                            f"{credits} deep chart jawab."
                        )
                    ),
                    "display_text": "Pay Now",
                    "url": result["short_url"],
                }
            ]
        except Exception as exc:
            logger.exception(
                "PWYW payment link failed: %s: %s",
                type(exc).__name__,
                exc,
                extra={"phone_number": phone_number},
            )
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT_PAYMENT_LINK}
            ]
        return data

    async def _handle_pay_command(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        """Legacy entry — routes to PWYW amount ask."""
        return self._enter_pwyw_amount(data, profile, phone_number)

    async def _handle_birth_details(
        self, data: dict, profile: dict, phone_number: str, flow_data: dict
    ) -> dict:
        """Parse DOB/time/place, resolve candidates, ask confirmation — no chart yet."""
        ymd = _parse_birth_date(flow_data.get("birth_date"))
        raw_place = str(flow_data.get("birth_place") or "").strip()
        if not ymd or not raw_place:
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        year, month, day = ymd
        unknown_time = _unknown_time_selected(flow_data)
        hm = _parse_birth_time(flow_data)
        if hm is None and not unknown_time and flow_data.get("flow_kind") != "typed_text":
            unknown_time = True

        profile["pending_birth"] = {
            "year": year,
            "month": month,
            "day": day,
            "hour": hm[0] if hm else None,
            "minute": hm[1] if hm else None,
            "raw_place": raw_place.replace("_", " ").strip(),
        }
        profile["place_attempts"] = 0
        return await self._resolve_and_ask_place(
            data,
            profile,
            phone_number,
            "",
            profile["pending_birth"]["raw_place"],
            retype=False,
        )

    async def _resolve_and_ask_place(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        query: str,
        *,
        retype: bool,
    ) -> dict:
        if retype:
            profile["place_attempts"] = int(profile.get("place_attempts") or 0) + 1
            if profile.get("pending_birth"):
                profile["pending_birth"]["raw_place"] = query.strip()

        candidates = await asyncio.to_thread(
            resolve_place_candidates, query, phone_number=phone_number, limit=3
        )
        if not candidates:
            data["bot_response"] = [
                {"type": "text", "text": GEOCODE_FAIL_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            mark_beat_send(profile, BEAT_AWAITING_PLACE_CONFIRM, inbound_id)
            return data

        profile["place_candidates"] = candidates
        attempts = int(profile.get("place_attempts") or 0)
        force_list = attempts >= 3 and len(candidates) >= 1
        clear = is_clear_place_winner(candidates)

        if force_list:
            data["bot_response"] = [
                {"type": "text", "text": PLACE_MAX_ATTEMPTS_TEXT},
                place_confirm_ui(
                    display=candidates[0]["display"],
                    candidates=candidates,
                    force_list=True,
                ),
            ]
            profile["pending_place"] = None
        elif len(candidates) >= 2 and clear:
            profile["pending_place"] = candidates[0]
            data["bot_response"] = [
                place_confirm_ui(
                    display=candidates[0]["display"],
                    candidates=candidates,
                )
            ]
        elif len(candidates) >= 2:
            profile["pending_place"] = None
            data["bot_response"] = [
                place_confirm_ui(
                    display=candidates[0]["display"],
                    candidates=candidates,
                )
            ]
        else:
            profile["pending_place"] = candidates[0]
            data["bot_response"] = [
                place_confirm_ui(
                    display=candidates[0]["display"],
                    candidates=None,
                )
            ]

        mark_beat_send(profile, BEAT_AWAITING_PLACE_CONFIRM, inbound_id)
        return data

    async def _handle_place_confirm(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        messages: dict,
    ) -> dict:
        action, cand_i = parse_place_confirm(
            messages, candidates=list(profile.get("place_candidates") or [])
        )
        candidates = list(profile.get("place_candidates") or [])

        if action == "cand" and cand_i is not None and 0 <= cand_i < len(candidates):
            profile["pending_place"] = candidates[cand_i]
            return await self._compute_chart_from_pending(
                data, profile, phone_number
            )

        if action == "yes":
            place = profile.get("pending_place")
            if not place and len(candidates) >= 1 and is_clear_place_winner(candidates):
                place = candidates[0]
                profile["pending_place"] = place
            if not place and len(candidates) == 1:
                place = candidates[0]
                profile["pending_place"] = place
            if not place:
                # Ambiguous — open list instead of truncated buttons
                data["bot_response"] = [
                    place_confirm_ui(
                        display=(candidates[0]["display"] if candidates else "that place"),
                        candidates=candidates or None,
                        force_list=bool(candidates),
                    )
                ]
                return data
            return await self._compute_chart_from_pending(
                data, profile, phone_number
            )

        if action == "others":
            # Clear-winner declined → show full list (dropdown)
            if candidates:
                profile["pending_place"] = None
                data["bot_response"] = [
                    place_confirm_ui(
                        display=candidates[0]["display"],
                        candidates=candidates,
                        force_list=True,
                    )
                ]
                return data
            data["bot_response"] = [{"type": "text", "text": PLACE_RETYPE_TEXT}]
            return data

        if action == "no":
            profile["place_attempts"] = int(profile.get("place_attempts") or 0) + 1
            profile["pending_place"] = None
            if int(profile["place_attempts"]) >= 3 and candidates:
                data["bot_response"] = [
                    {"type": "text", "text": PLACE_MAX_ATTEMPTS_TEXT},
                    place_confirm_ui(
                        display=candidates[0]["display"],
                        candidates=candidates,
                        force_list=True,
                    ),
                ]
                return data
            data["bot_response"] = [{"type": "text", "text": PLACE_RETYPE_TEXT}]
            return data

        # Free-text retype of place name
        text_body = ""
        if isinstance(messages, dict) and messages.get("type") == "text":
            text_body = ((messages.get("text") or {}).get("body") or "").strip()
        if text_body:
            return await self._resolve_and_ask_place(
                data, profile, phone_number, inbound_id, text_body, retype=True
            )

        # Unrecognised — re-offer hybrid UI
        pending = profile.get("pending_place")
        if not pending and len(candidates) == 1:
            pending = candidates[0]
        if candidates or pending:
            disp = (
                (pending.get("display") if isinstance(pending, dict) else None)
                or (candidates[0]["display"] if candidates else None)
                or "that place"
            )
            data["bot_response"] = [
                place_confirm_ui(
                    display=disp,
                    candidates=candidates if len(candidates) >= 2 else None,
                    force_list=len(candidates) >= 2
                    and not is_clear_place_winner(candidates),
                )
            ]
        else:
            data["bot_response"] = [{"type": "text", "text": PLACE_RETYPE_TEXT}]
        return data

    async def _compute_chart_from_pending(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        """Compute chart only after place is confirmed."""
        pending = profile.get("pending_birth") or {}
        place = profile.get("pending_place") or {}
        if not pending or not place.get("lat") or not place.get("lon"):
            data["bot_response"] = [
                {"type": "text", "text": GEOCODE_FAIL_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        year = int(pending["year"])
        month = int(pending["month"])
        day = int(pending["day"])
        hm = None
        if pending.get("hour") is not None and pending.get("minute") is not None:
            hm = (int(pending["hour"]), int(pending["minute"]))
        lat = float(place["lat"])
        lon = float(place["lon"])
        place_name = str(place.get("display") or place.get("name") or "Unknown")

        tz_offset = await asyncio.to_thread(
            timezone_offset_for, lat, lon, year, month, day
        )

        try:
            BirthDetails, compute_chart = _kundli()
        except Exception as exc:
            logger.exception(
                "kundli_engine import failed: %s: %s",
                type(exc).__name__,
                exc,
                extra={"phone_number": phone_number},
            )
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        birth = BirthDetails(
            year=year,
            month=month,
            day=day,
            latitude=lat,
            longitude=lon,
            timezone_offset=tz_offset,
            hour=hm[0] if hm else None,
            minute=hm[1] if hm else None,
            place_name=place_name,
        )
        try:
            chart = await asyncio.to_thread(compute_chart, birth)
        except Exception as exc:
            logger.exception(
                "compute_chart failed: %s: %s",
                type(exc).__name__,
                exc,
                extra={
                    "phone_number": phone_number,
                    "place": place_name,
                    "lat": lat,
                    "lon": lon,
                    "dob": f"{year:04d}-{month:02d}-{day:02d}",
                    "tob": f"{hm[0]:02d}:{hm[1]:02d}" if hm else None,
                    "tz_offset": tz_offset,
                },
            )
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        profile["chart_json"] = chart
        profile["birth_details"] = {
            "date_of_birth": f"{year:04d}-{month:02d}-{day:02d}",
            "time_of_birth": f"{hm[0]:02d}:{hm[1]:02d}" if hm else None,
            "place_name": place_name,
            "latitude": lat,
            "longitude": lon,
            "timezone_offset": tz_offset,
            "country": place.get("country"),
            "admin1": place.get("admin1"),
            "inferred_country": place.get("cc"),
        }
        profile["user_language"] = None
        profile["conversation_beat"] = BEAT_AWAITING_LANGUAGE
        profile["free_deep_answer_used"] = False
        profile["free_reading_used"] = False
        profile["open_loop_summary"] = None
        profile["chosen_topic"] = None
        profile["beat_last_inbound_id"] = None
        profile["confirmed_events"] = []
        profile["rejected_windows"] = []
        profile["beat2_windows_offered"] = 0
        profile["beat2_offered_starts"] = []
        profile["beat2_pending_window"] = None
        # Clear place-confirm scratch
        for key in (
            "pending_birth",
            "pending_place",
            "place_candidates",
            "place_attempts",
        ):
            profile.pop(key, None)
        emit_funnel_event("birth_flow_completed", phone_number=phone_number)
        logger.info(
            "Samara chart computed",
            extra={
                "phone_number": phone_number,
                "chart_type": chart["meta"]["chart_type"],
                "place": place_name,
            },
        )
        data["bot_response"] = [_language_quickreply_response()]
        return data

    async def _handle_solicited_reply(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        reply_text: str,
    ) -> dict:
        """Answer a reply to Samara's own question — free, no debit, no gate."""
        ctx = (profile.get("bot_question_context") or "").strip()
        question = (
            f"The user is answering your previous question.\n"
            f"Your question context: {ctx}\n"
            f"Their reply: {reply_text}\n"
            f"Give a complete, chart-grounded answer. Do NOT ask another "
            f"withholding question. Do NOT mention credits or paywall."
        )
        clear_bot_asked_question(profile)
        # Never treat as consuming free deep / credits
        result = await deliver_paid_deep_answer(
            profile=profile,
            phone_number=phone_number,
            question=question,
            debit=False,
        )
        if not result:
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data
        text, _ = result
        responses = text_responses(text)
        # Mark only if THIS answer itself asks again (rare; RULE 6 discourages)
        joined = "\n".join(r.get("text", "") for r in responses if r.get("type") == "text")
        mark_bot_asked_question(profile, joined, context=joined)
        data["bot_response"] = responses
        return data

    def _enter_trust_recovery(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        """Honest miss — gate stays closed. Cap 2 attempts then suppress gate."""
        attempts = int(profile.get("trust_recovery_attempts") or 0)
        if attempts >= 2:
            profile["gate_suppressed_session"] = True
            profile["in_trust_recovery"] = False
            emit_funnel_event("trust_recovery_failed", phone_number=phone_number)
            mark_beat_send(profile, BEAT_AWAITING_TOPIC)
            lang = _lang(profile)
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": (
                        "Let's keep it simple — pick an area below and I'll "
                        "read what I can, no pressure."
                        if lang == "english"
                        else "Simple rakhte hain — neeche area choose kariye, "
                        "main jo padh sakti hoon bataungi, bina pressure."
                    ),
                },
                topic_picker_buttons(lang=lang),
            ]
            return data

        profile["trust_recovery_attempts"] = attempts + 1
        profile["in_trust_recovery"] = True
        profile["bot_asked_question"] = True
        profile["bot_question_context"] = "trust_recovery_what_matters"
        mark_beat_send(profile, BEAT_TRUST_RECOVERY)
        emit_funnel_event("trust_recovery_entered", phone_number=phone_number)
        lang = _lang(profile)
        prompt = (
            "I don't think I've read you properly yet. Let me try differently — "
            "what matters most to you right now?"
            if lang == "english"
            else "Lagta hai main aapko theek se nahi pakad payi. Ek baat batayein — "
            "abhi aapke liye sabse zaroori kya hai?"
        )
        data["bot_response"] = [{"type": "text", "text": prompt}]
        return data

    async def _handle_trust_recovery_reply(
        self, data: dict, profile: dict, phone_number: str, reply: str
    ) -> dict:
        clear_bot_asked_question(profile)
        chart = profile.get("chart_json") or {}
        tps = json.dumps(chart.get("turning_points") or [], ensure_ascii=False)
        question = (
            f"Trust recovery. User said what matters: {reply}\n"
            f"Give ONE specific chart-grounded response using strongest "
            f"turning_points / dasha material:\n{tps}\n"
            f"Be concrete. No paywall. No fear."
        )
        result = await deliver_paid_deep_answer(
            profile=profile,
            phone_number=phone_number,
            question=question,
            debit=False,
        )
        profile["in_trust_recovery"] = False
        if not result:
            emit_funnel_event("trust_recovery_failed", phone_number=phone_number)
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data
        text, _ = result
        bump_trust(profile, 2)
        emit_funnel_event("trust_recovery_succeeded", phone_number=phone_number)
        mark_beat_send(profile, BEAT_POST_FREE_DEEP)
        # Gate still closed while trust was low; free_deep may already be set
        data["bot_response"] = text_responses(text)
        return data

    async def _handle_followup(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        question = ""
        if messages := data.get("messages"):
            question = ((messages.get("text") or {}).get("body") or "").strip()
        return await self._handle_followup_with_question(
            data, profile, phone_number, question=question
        )

    async def _handle_followup_with_question(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        *,
        question: str,
    ) -> dict:
        if not question:
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": "Apna sawaal text message mein likhiye, main kundli dekh kar batati hoon. 🙏",
                }
            ]
            return data

        # Gate ON: only via single decide_gate_action (never on solicited).
        if profile.get("bot_asked_question"):
            return await self._handle_solicited_reply(
                data, profile, phone_number, question
            )

        from kisna_chatbot.utils.samara_focus import (
            focus_prompt_block,
            get_focus,
            update_focus_from_user,
        )
        from kisna_chatbot.utils.samara_intent import (
            classify_intent,
            is_free_intent,
        )

        update_focus_from_user(profile, text=question)
        focus = get_focus(profile)
        recent = format_prompt_history(profile) or ""

        async def _intent_llm(instruction: str, user_content: str) -> str:
            return await self._llm(
                instruction=instruction,
                user_content=user_content,
                phone_number=phone_number,
                agent_display_name="SamaraIntent",
                max_output_tokens=40,
                purpose="intent",
            )

        intent = await classify_intent(
            question,
            focus=focus,
            recent_turns=recent,
            classify_fn=_intent_llm,
        )

        if intent == "payment_intent":
            return self._enter_pwyw_amount(data, profile, phone_number)

        if intent == "correction":
            return self._offer_chart_recompute(data, profile, phone_number)

        if intent == "smalltalk":
            lang = _lang(profile)
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": (
                        "Namaste 🌙 I'm here — what would you like to look at in your chart?"
                        if lang == "english"
                        else "Namaste 🌙 Main yahin hoon — chart mein kya dekhna hai?"
                    ),
                }
            ]
            return data

        if intent == "offtopic":
            lang = _lang(profile)
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": (
                        "I'm best with your chart — career, love, timing. "
                        "What feels most pressing?"
                        if lang == "english"
                        else "Main chart mein best hoon — career, pyaar, timing. "
                        "Sabse zaroori kya hai abhi?"
                    ),
                }
            ]
            return data

        if intent in ("confirmation", "denial") and is_free_intent(intent):
            # Outside intro beats: short free ack, no debit
            lang = _lang(profile)
            if intent == "confirmation":
                body = (
                    "Achha — noted. Aur batao?"
                    if lang != "english"
                    else "Got it. What else is on your mind?"
                )
            else:
                from kisna_chatbot.utils.samara_gate import bump_trust

                bump_trust(profile, -1)
                body = (
                    "Theek hai — main adjust karti hoon. Kya clarify karun?"
                    if lang != "english"
                    else "Alright — I'll adjust. What should I clarify?"
                )
            data["bot_response"] = [{"type": "text", "text": body}]
            return data

        if is_free_intent(intent):
            # followup / clarification / meta / test_me — free, no gate, no debit
            if intent == "test_me" or (
                profile.get("test_me_offered")
                and not profile.get("test_me_used")
                and _extract_year_challenge(question)
            ):
                handled = self._handle_test_me_year(
                    data, profile, phone_number, question
                )
                if handled is not None:
                    return handled
            return await self._handle_free_intent_reply(
                data, profile, phone_number, question=question, intent=intent
            )

        # new_deep_question only past this point may gate / debit
        action = decide_gate_action(
            profile,
            amount_inr=_payment_amount_inr(),
        )
        if action.kind == "door":
            return _emit_door_gate(
                data, profile, phone_number, pending=question, body=action.body
            )

        async def _summary_llm(instruction: str, user_content: str) -> str:
            return await self._llm(
                instruction=instruction,
                user_content=user_content,
                phone_number=phone_number,
                agent_display_name="SamaraSummary",
                max_output_tokens=200,
                purpose="summary",
            )

        await maybe_refresh_conversation_summary(
            profile, classify_fn=_summary_llm
        )

        # Daily generation cap (distress already handled above)
        if self._enforce_daily_cap(data, profile, phone_number):
            return data

        # Timing intent: redirect to topic picker instead of spending credits
        if _looks_like_timing_intent(question):
            if not profile.get("free_deep_answer_used"):
                redirect = TIMING_REDIRECT_EN if _lang(profile) == "english" else TIMING_REDIRECT_HI
                mark_beat_send(profile, BEAT_AWAITING_TOPIC)
                data["bot_response"] = [
                    {"type": "text", "text": redirect},
                    topic_picker_buttons(lang=_lang(profile)),
                ]
                return data

        should_debit = (
            profile.get("free_deep_answer_used") is True
            and not profile.get("gate_suppressed_session")
            and not profile.get("in_trust_recovery")
        )
        result = await deliver_paid_deep_answer(
            profile=profile,
            phone_number=phone_number,
            question=question,
            debit=should_debit,
        )
        if not result:
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data
        text, _ = result
        responses = text_responses(text)
        mark_bot_asked_question(profile, text, context=text)

        # Single post-answer gate decision (never stack with meter copy)
        upsell_action = decide_gate_action(
            profile, amount_inr=_payment_amount_inr()
        )
        if should_debit and upsell_action.kind == "door":
            emit_funnel_event("top_up_offered", phone_number=phone_number)
            responses.append(
                paywall_buttons(
                    lang=_lang(profile),
                    body=upsell_action.body or door_gate_body(
                        profile, amount_inr=_payment_amount_inr()
                    ),
                    amount_inr=_payment_amount_inr(),
                )
            )
        elif should_debit:
            bal = get_credit_balance(profile)
            lang = _lang(profile)
            if bal == 2 and not profile.get("second_pack_offered_session"):
                profile["second_pack_offered_session"] = True
                emit_funnel_event("second_pack_offered", phone_number=phone_number)
                # Soft note only — not a second gate QR
                note = (
                    "You have 2 deep answers left in this pack."
                    if lang == "english"
                    else "Pack mein 2 deep answers bachi hain."
                )
                responses.append({"type": "text", "text": note})
            elif bal > 0:
                footer = (
                    f"✦ {bal} deep chart answer{'s' if bal != 1 else ''} left."
                    if lang == "english"
                    else f"✦ Pack mein {bal} deep chart answer bachi hain."
                )
                responses.append({"type": "text", "text": footer})

        assert count_gate_messages(responses) <= 1
        data["bot_response"] = responses
        return data

    def _offer_chart_recompute(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        """Birth-time / details correction — free; clear chart and resend flow."""
        lang = _lang(profile)
        profile["chart_json"] = None
        profile["conversation_beat"] = None
        profile.pop("pending_birth", None)
        profile.pop("pending_place", None)
        body = (
            "No problem — let's rebuild your kundli with the right details. "
            "Share date, time, and place in the form below."
            if lang == "english"
            else "Koi baat nahi — sahi details se kundli dobara banate hain. "
            "Neeche form mein date, time aur place share kariye."
        )
        data["bot_response"] = [
            {"type": "text", "text": body},
            {"type": "flow", "flow": "birth_details"},
        ]
        emit_funnel_event("chart_recompute_offered", phone_number=phone_number)
        return data

    def _handle_test_me_year(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        question: str,
    ) -> dict | None:
        """Once-per-session year challenge — engine period character only."""
        year = _extract_year_challenge(question)
        if year is None:
            return None
        if profile.get("test_me_used"):
            lang = _lang(profile)
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": (
                        "One challenge per session is enough — let's keep going with your question."
                        if lang == "english"
                        else "Ek session mein ek challenge kaafi hai — aage badhte hain."
                    ),
                }
            ]
            return data

        from kundli_engine.antardasha_labels import lookup_antardasha_covering_year

        chart = profile.get("chart_json") or {}
        row = lookup_antardasha_covering_year(
            chart.get("antardasha_timeline") or [], year
        )
        lang = _lang(profile)
        if not row:
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": (
                        f"I don't have a clear antardasha window for {year} in this chart."
                        if lang == "english"
                        else f"{year} ke liye chart mein clear antardasha window nahi dikha."
                    ),
                }
            ]
            return data

        profile["test_me_used"] = True
        month = (
            row.get("window_label_month_hi")
            if lang != "english"
            else row.get("window_label_month_en")
        ) or (
            row.get("window_label_hi")
            if lang != "english"
            else row.get("window_label_en")
        )
        maha = row.get("maha_planet_en") or ""
        antar = row.get("antar_planet_en") or ""
        from kundli_engine.antardasha_labels import ANTAR_THEMES

        theme_en, theme_hi = ANTAR_THEMES.get(antar, ("change", "badlav"))
        theme = theme_hi if lang != "english" else theme_en
        if lang == "english":
            body = (
                f"Around {month}, your chart was in a {maha}–{antar} chapter "
                f"with a texture of {theme}. I won't claim what happened — "
                f"does that period ring a bell?"
            )
        else:
            body = (
                f"{month} ke aas-paas chart mein {maha}–{antar} chapter chal raha tha — "
                f"texture: {theme}. Kya hua, woh main claim nahi karti — "
                f"kya yeh period pehchaan mein aata hai?"
            )
        emit_funnel_event("test_me_answered", phone_number=phone_number)
        data["bot_response"] = [{"type": "text", "text": body}]
        return data

    async def _handle_free_intent_reply(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        *,
        question: str,
        intent: str,
    ) -> dict:
        """followup / clarification / meta / test_me — never debit, never gate."""
        from kisna_chatbot.utils.samara_focus import focus_prompt_block

        focus_block = focus_prompt_block(profile)
        meta_hint = ""
        if intent == "meta":
            meta_hint = (
                "Answer plainly how Samara works (real kundli from birth details, "
                "planetary periods, pay-what-you-want for deeper answers). No sell-hard."
            )
        elif intent == "clarification":
            meta_hint = "Re-explain simply against the focus object. No new deep topic."
        elif intent == "test_me":
            meta_hint = (
                "If they named a year, use only engine antardasha covering that year "
                "(month-level labels). Never assert what happened. Free trust builder."
            )
        else:
            meta_hint = (
                "Answer as a FREE follow-up against CONVERSATION FOCUS. "
                "Resolve kab/why/aur against last_claim and dates_on_table."
            )
        wrapped = (
            f"{focus_block}\n\nIntent: {intent}\n{meta_hint}\n\n"
            f"User message: {question}\n"
            "Do NOT mention credits or paywall. Do NOT invent dates."
        )
        result = await deliver_paid_deep_answer(
            profile=profile,
            phone_number=phone_number,
            question=wrapped,
            debit=False,
        )
        if not result:
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data
        text, _ = result
        data["bot_response"] = text_responses(text)
        return data

    def _handle_data_deletion(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        """Purge PII, chart, chat. Keep anonymised ledger (amounts/types/payment_ids)."""
        lang = _lang(profile)
        anonymised_ledger = []
        for entry in (profile.get("credit_ledger") or []):
            if isinstance(entry, dict):
                anonymised_ledger.append({
                    "type": entry.get("type"),
                    "amount": entry.get("amount"),
                    "source": entry.get("source"),
                    "payment_id": entry.get("payment_id"),
                    "timestamp": entry.get("timestamp"),
                })
        for key in list(profile.keys()):
            if key in ("credits", "credit_ledger", "client_id", "phone_number", "_id"):
                continue
            profile.pop(key, None)
        profile["credit_ledger"] = anonymised_ledger
        profile["data_deleted_at"] = int(datetime.now(timezone.utc).timestamp())
        emit_funnel_event("data_deleted", phone_number=phone_number)
        confirm = DATA_DELETED_TEXT_EN if lang == "english" else DATA_DELETED_TEXT_HI
        data["bot_response"] = [{"type": "text", "text": confirm}]
        return data

    def _handle_paywall_later(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        profile["paywall_deferred"] = True
        profile["paywall_pitch_suppressed"] = True
        profile["nudge_scheduled_at"] = int(datetime.now(timezone.utc).timestamp()) + 86400
        profile["nudge_sent"] = False
        profile["pending_deep_question"] = profile.get("pending_deep_question")
        lang = _lang(profile)
        text = (
            "Bilkul theek hai 🙏 Jab ready ho, 'pay' ya 'unlock' likh dena — "
            "main yahin hoon, bina pressure ke."
            if lang != "english"
            else "Of course 🙏 When you're ready, just type pay or unlock — "
            "I'll be here, no pressure."
        )
        data["bot_response"] = [{"type": "text", "text": text}]
        return data


TOP_UP_TEXT_HI = (
    "Woh jawab poora hai 🌙 "
    "Agla clear window aur poori tasveer ke liye jab ready ho unlock kariye."
)
TOP_UP_TEXT_EN = (
    "That answer stands on its own 🌙 "
    "When you're ready, unlock for the next clear window and full picture."
)
SECOND_PACK_TEXT_HI = (
    "Pack mein 2 deep answers bachi hain 🌙 "
    "Thread jaari rakhna ho toh ready hone par unlock kariye — koi rush nahi."
)
SECOND_PACK_TEXT_EN = (
    "You have 2 deep answers left 🌙 "
    "Unlock when you want to keep this thread going — no rush."
)
TIMING_REDIRECT_HI = (
    "Yeh sawaal time-related lagta hai ✨ "
    "Neeche se koi ek topic choose kijiye — phir main us area mein dekhungi."
)
TIMING_REDIRECT_EN = (
    "This seems like a timing question ✨ "
    "Pick a topic below — I'll look into that area for you."
)

_TIMING_KEYWORDS = frozenset({
    "kab", "when", "which month", "kis month", "timing",
    "kab hoga", "kab milega", "kab tak", "when will",
})


def _looks_like_timing_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(k in t for k in _TIMING_KEYWORDS)


def _extract_year_challenge(text: str) -> int | None:
    """Pull a 4-digit year suitable for test-me (1950–2100)."""
    import re

    m = re.search(r"\b(19\d{2}|20\d{2})\b", text or "")
    if not m:
        return None
    year = int(m.group(1))
    if 1950 <= year <= 2100:
        return year
    return None


async def deliver_paid_deep_answer(
    *,
    profile: dict,
    phone_number: str,
    question: str,
    debit: bool = True,
) -> tuple[str, dict] | None:
    """Generate a deep/follow-up answer; debit one credit only after success.

    Used by follow-ups and by Razorpay resume. LLM never computes chart facts.
    """
    chart = profile.get("chart_json")
    now_ctx = _now_context(chart)
    lang = _lang(profile)
    history_snippet = format_prompt_history(profile) or "(no prior turns)"
    instruction = SAMARA_FOLLOWUP_SYSTEM_PROMPT.format(
        chart_json=json.dumps(
            slim_chart_for_beat(chart, "paid_deep" if debit else "followup"),
            ensure_ascii=False,
        ),
        user_name=display_user_name(profile),
        user_language=lang,
        current_date=now_ctx["current_date"],
        current_year=now_ctx["current_year"],
        current_age=now_ctx["current_age"],
        chat_history_snippet=history_snippet,
        confirmed_events_json=_confirmed_events_json(profile),
        upcoming_periods_json=json.dumps(
            (chart or {}).get("upcoming_periods") or [], ensure_ascii=False
        ),
    )
    from kisna_chatbot.ai.samara_models import samara_model_for

    purpose = "paid_deep" if debit else "muhurat"
    primary, fallback = samara_model_for(purpose)
    try:
        text = await complete_chat(
            agent=AgentName.GENERAL,
            agent_display_name="SamaraPaidDeep",
            instruction=instruction,
            messages=[{"role": "user", "content": question}],
            max_output_tokens=500,
            phone_number=phone_number,
            client_id="samara",
            model=primary,
            model_fallback=fallback,
        )
    except Exception:
        logger.exception(
            "deliver_paid_deep_answer LLM failed",
            extra={"phone_number": phone_number},
        )
        return None

    text, _ = sanitize_nasa_endorsement(text)

    # Debit only after successful generation (never on LLM failure).
    if debit and profile.get("free_deep_answer_used"):
        updated = debit_credit(
            phone_number=phone_number,
            client_id="samara",
            amount=1,
            source="deep_answer",
        )
        if updated:
            profile["credits"] = updated.get("credits")
            profile["credit_ledger"] = updated.get("credit_ledger")
        else:
            entries = list(profile.get("credit_ledger") or [])
            entries.append(
                {
                    "type": "debit",
                    "amount": 1,
                    "source": "deep_answer",
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                }
            )
            profile["credit_ledger"] = entries
            profile["credits"] = get_credit_balance(profile)

    profile["followup_questions_asked"] = (
        int(profile.get("followup_questions_asked") or 0) + 1
    )
    profile["conversation_beat"] = BEAT_POST_FREE_DEEP
    profile["open_loop_summary"] = (text or "")[-400:]
    return text, profile


def _post_debit_upsell(profile: dict, phone_number: str) -> list[dict] | None:
    """After successful paid answer: top-up or second-pack offer if appropriate."""
    balance = get_credit_balance(profile)
    lang = _lang(profile)
    if balance == 0:
        emit_funnel_event("top_up_offered", phone_number=phone_number)
        body = TOP_UP_TEXT_EN if lang == "english" else TOP_UP_TEXT_HI
        return [paywall_buttons(lang=lang, body=body)]
    if balance == 2 and not profile.get("second_pack_offered_session"):
        profile["second_pack_offered_session"] = True
        emit_funnel_event("second_pack_offered", phone_number=phone_number)
        body = SECOND_PACK_TEXT_EN if lang == "english" else SECOND_PACK_TEXT_HI
        return [paywall_buttons(lang=lang, body=body)]
    return None