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
    SAMARA_BEAT4_DEEP_PROMPT,
    SAMARA_FOLLOWUP_SYSTEM_PROMPT,
    SAMARA_MUHURAT_PROMPT,
)
from kisna_chatbot.utils.format_chathistory import format_recent_history_str
from kisna_chatbot.utils.funnel_events import emit_funnel_event
from kisna_chatbot.utils.geocode_in import geocode_place, timezone_offset_for
from kisna_chatbot.utils.logger_config import logger
from kisna_chatbot.utils.samara_beats import (
    ACTIVE_INTRO_BEATS,
    BEAT_1_AWAITING_CONFIRM,
    BEAT_2_AWAITING_ADVANCE,
    BEAT_AWAITING_LANGUAGE,
    BEAT_AWAITING_TOPIC,
    BEAT_POST_FREE_DEEP,
    BEAT_RETURNING_MENU,
    TOPIC_LABELS,
    beat1_confirm_buttons,
    beat2_next_button,
    claim_beat_transition,
    inbound_message_id,
    looks_like_greeting,
    mark_beat_send,
    parse_beat1_confirm,
    parse_beat2_advance,
    parse_returning_choice,
    parse_topic_choice,
    relevant_dasha_slice,
    returning_menu_buttons,
    text_responses,
    topic_picker_buttons,
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
    settings = get_ai_settings()
    return settings["anthropic_chat_model_sonnet"], settings["anthropic_chat_model"]


_TIME_RE = re.compile(r"^\s*([01]?\d|2[0-3])[:.\s]([0-5]\d)\s*$")
_TEXT_DATE_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")
_TEXT_DATE_ISO_RE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_TEXT_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")

GREETING_TEXT = (
    "Namaste 🙏 Main Samara hoon — aapki personal Vedic astrology guide, by Clara. ✨\n\n"
    "Aapki asli janam kundli banane ke liye mujhe bas aapki birth details chahiye — "
    "date, time aur place of birth. Neeche form khol kar share kar dijiye, "
    "phir main aapke liye ek warm, personal reading likhungi. 🌙"
)

NUDGE_TEXT = (
    "Bas ek chhota sa step baaki hai ✨ — neeche form se apni birth details "
    "(date, time, place) share kar dijiye, phir main aapki kundli padh kar reading dungi. 🙏"
)

# Dead until Phase 2 gate — kept only so grep can find paywall copy to replace.
PAYWALL_TEXT = (
    "Aapka free reading ho chuka hai 🌙 Aur sawaal poochne ke liye credits chahiye — "
    "₹49 mein 10 sawaal. 💫\n\n"
    "Payments jald hi live ho rahe hain (Razorpay coming soon). Tab tak thoda intezaar kijiye — "
    "main yahin hoon. 🙏"
)

GEOCODE_FAIL_TEXT = (
    "Hmm, mujhe woh jagah nahi mili 😔 Koi baat nahi — form dobara khol kar "
    "place of birth mein apne sheher ya paas ke bade sheher ka naam likhiye "
    "(jaise Jaipur, Lucknow, Mumbai). 🙏"
)

ERROR_TEXT = (
    "Maaf kijiye, kundli banate waqt kuch gadbad ho gayi 😔 "
    "Please form dobara bhar kar try kijiye. 🙏"
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


def _parse_birth_time(flow_data: dict) -> tuple[int, int] | None:
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


def _has_completed_free_path(profile: dict) -> bool:
    return bool(
        profile.get("free_deep_answer_used") or profile.get("free_reading_used")
    )


def _lang(profile: dict) -> str:
    return profile.get("user_language") or "hindi"


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
        messages = data.get("messages") or {}
        inbound_id = inbound_message_id(messages)

        # Exact "PAY" test trigger → Razorpay payment link + CTA URL button.
        if messages.get("type") == "text":
            text_body = ((messages.get("text") or {}).get("body") or "")
            if text_body.strip() == "PAY":
                return await self._handle_pay_command(data, profile, phone_number)

        # Idempotent: duplicate Gupshup delivery of an already-handled inbound
        # must not advance or regenerate beats.
        if inbound_id and profile.get("beat_last_inbound_id") == inbound_id:
            data["bot_response"] = [{"type": "skip"}]
            return data

        flow_data = _parse_birth_flow_reply(messages)
        if flow_data is not None:
            return await self._handle_birth_details(data, profile, phone_number, flow_data)

        if not profile.get("chart_json"):
            text_body = ""
            if messages.get("type") == "text":
                text_body = ((messages.get("text") or {}).get("body") or "").strip()
            typed = _parse_birth_text(text_body)
            if typed:
                return await self._handle_birth_details(
                    data, profile, phone_number, typed
                )
            is_new = not profile.get("chat_history")
            emit_funnel_event("birth_flow_opened", phone_number=phone_number)
            data["bot_response"] = [
                {"type": "text", "text": GREETING_TEXT if is_new else NUDGE_TEXT},
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
                return await self._send_beat1(data, profile, phone_number, inbound_id)
            mark_beat_send(profile, BEAT_AWAITING_LANGUAGE)
            data["bot_response"] = [_language_quickreply_response()]
            return data

        # Mid-intro beat handling
        if beat == BEAT_1_AWAITING_CONFIRM:
            conf = parse_beat1_confirm(messages)
            if conf:
                if not claim_beat_transition(
                    profile,
                    expected_beats=(BEAT_1_AWAITING_CONFIRM,),
                    next_beat=BEAT_2_AWAITING_ADVANCE,
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
                return await self._send_beat2(
                    data, profile, phone_number, inbound_id, confirm_signal=conf
                )
            # Re-prompt confirm buttons (without regenerating LLM)
            data["bot_response"] = [
                beat1_confirm_buttons(
                    "Yeh pehchaan theek lagti hai?"
                    if _lang(profile) != "english"
                    else "Does this feel like you?",
                    lang=_lang(profile),
                )
            ]
            return data

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
            data["bot_response"] = [
                beat2_next_button(
                    "Jab ready ho, aage badhein."
                    if _lang(profile) != "english"
                    else "When you're ready, continue.",
                    lang=_lang(profile),
                )
            ]
            return data

        if beat == BEAT_AWAITING_TOPIC:
            topic = parse_topic_choice(messages)
            if topic:
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
                data["bot_response"] = [
                    returning_menu_buttons(
                        lang=_lang(profile),
                        name=profile.get("username") or "dost",
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
        use_sonnet: bool,
    ) -> str:
        sonnet, haiku = _sonnet_models()
        kwargs = {
            "agent": AgentName.GENERAL,
            "agent_display_name": agent_display_name,
            "instruction": instruction,
            "messages": [{"role": "user", "content": user_content}],
            "max_output_tokens": max_output_tokens,
            "phone_number": phone_number,
            "client_id": "samara",
        }
        if use_sonnet:
            kwargs["model"] = sonnet
            kwargs["model_fallback"] = haiku
        else:
            kwargs["model"] = haiku
        return await complete_chat(**kwargs)

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

        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        instruction = SAMARA_BEAT1_IDENTITY_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            user_name=profile.get("username") or "dost",
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 1 identity now.",
                phone_number=phone_number,
                agent_display_name="SamaraBeat1",
                max_output_tokens=400,
                use_sonnet=True,
            )
        except Exception:
            logger.exception("Beat1 LLM failed", extra={"phone_number": phone_number})
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        chunks = text_responses(text)
        # Attach confirm buttons to the last text chunk
        if chunks:
            last = chunks[-1]["text"]
            chunks = chunks[:-1] + [beat1_confirm_buttons(last, lang=lang)]
        else:
            chunks = [beat1_confirm_buttons(text, lang=lang)]

        mark_beat_send(profile, BEAT_1_AWAITING_CONFIRM, inbound_id)
        # Compat for dashboard "readings delivered"
        profile["free_reading_used"] = True
        profile["reading_delivered_at"] = int(datetime.now(timezone.utc).timestamp())
        emit_funnel_event("beat1_sent", phone_number=phone_number)
        data["bot_response"] = chunks
        return data

    async def _send_beat2(
        self,
        data: dict,
        profile: dict,
        phone_number: str,
        inbound_id: str,
        *,
        confirm_signal: str,
    ) -> dict:
        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        relevant = relevant_dasha_slice(chart)
        instruction = SAMARA_BEAT2_PAST_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            relevant_dasha_json=json.dumps(relevant, ensure_ascii=False),
            user_name=profile.get("username") or "dost",
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
            confirm_signal=confirm_signal,
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content="Write Beat 2 past proof now.",
                phone_number=phone_number,
                agent_display_name="SamaraBeat2",
                max_output_tokens=500,
                use_sonnet=True,
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

    def _send_topic_picker(self, data: dict, profile: dict) -> dict:
        mark_beat_send(profile, BEAT_AWAITING_TOPIC)
        data["bot_response"] = [topic_picker_buttons(lang=_lang(profile))]
        return data

    async def _send_beat4(
        self, data: dict, profile: dict, phone_number: str, topic: str
    ) -> dict:
        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        history_snippet = format_recent_history_str(profile, n=8) or "(no prior turns)"
        label = TOPIC_LABELS.get(topic, topic)
        instruction = SAMARA_BEAT4_DEEP_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            user_name=profile.get("username") or "dost",
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_age=now_ctx["current_age"],
            topic_key=topic,
            topic_label=label,
            chat_history_snippet=history_snippet,
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content=f"Write the free deep answer for topic: {label}",
                phone_number=phone_number,
                agent_display_name="SamaraBeat4",
                max_output_tokens=600,
                use_sonnet=True,
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
        data["bot_response"] = text_responses(text)
        return data

    async def _send_muhurat(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        instruction = SAMARA_MUHURAT_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            user_name=profile.get("username") or "dost",
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
                use_sonnet=False,
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

    async def _handle_pay_command(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        try:
            from kisna_chatbot.payments.razorpay_client import keys_configured
            from kisna_chatbot.payments.service import (
                create_and_store_payment_link,
                make_samara_order_id,
                test_payment_amount_inr,
            )

            if not keys_configured():
                raise RuntimeError(
                    "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET missing on this deployment"
                )

            amount = test_payment_amount_inr()
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
                    "source": "whatsapp_PAY",
                },
                phone_number=phone_number,
                client_id="samara",
                description=f"Samara credits — ₹{amount:g}",
            )
            amount_display = (
                str(int(amount)) if float(amount).is_integer() else f"{amount:g}"
            )
            emit_funnel_event("pay_link_created", phone_number=phone_number)
            data["bot_response"] = [
                {
                    "type": "cta_url",
                    "text": (
                        f"Click below to complete your payment of ₹{amount_display} "
                        f"for Samara credits (10 questions)."
                    ),
                    "display_text": "Pay Now",
                    "url": result["short_url"],
                    "footer": "Samara by Clara",
                }
            ]
        except Exception as exc:
            logger.exception(
                "PAY command failed: %s: %s",
                type(exc).__name__,
                exc,
                extra={"phone_number": phone_number},
            )
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": (
                        "Maaf kijiye, payment link abhi nahi ban paya 😔 "
                        "Thodi der baad 'PAY' likh kar try kijiye. 🙏"
                    ),
                }
            ]
        return data

    async def _handle_birth_details(
        self, data: dict, profile: dict, phone_number: str, flow_data: dict
    ) -> dict:
        ymd = _parse_birth_date(flow_data.get("birth_date"))
        raw_place = str(flow_data.get("birth_place") or "").strip()
        if not ymd or not raw_place:
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        place = raw_place.replace("_", " ").title()
        coords = await asyncio.to_thread(geocode_place, place)
        if not coords:
            data["bot_response"] = [
                {"type": "text", "text": GEOCODE_FAIL_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        year, month, day = ymd
        lat, lon = coords
        hm = _parse_birth_time(flow_data)
        if hm is None and flow_data.get("flow_kind") != "typed_text":
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data
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
            place_name=place,
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
                    "place": place,
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
            "place_name": place,
            "latitude": lat,
            "longitude": lon,
            "timezone_offset": tz_offset,
        }
        profile["user_language"] = None
        profile["conversation_beat"] = BEAT_AWAITING_LANGUAGE
        profile["free_deep_answer_used"] = False
        profile["free_reading_used"] = False
        profile["open_loop_summary"] = None
        profile["chosen_topic"] = None
        profile["beat_last_inbound_id"] = None
        emit_funnel_event("birth_flow_completed", phone_number=phone_number)
        logger.info(
            "Samara chart computed",
            extra={
                "phone_number": phone_number,
                "chart_type": chart["meta"]["chart_type"],
                "place": place,
            },
        )
        data["bot_response"] = [_language_quickreply_response()]
        return data

    async def _handle_followup(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        # Payment blocker still OFF (Phase 2 turns gate on).
        question = ""
        if messages := data.get("messages"):
            question = ((messages.get("text") or {}).get("body") or "").strip()
        if not question:
            data["bot_response"] = [
                {
                    "type": "text",
                    "text": "Apna sawaal text message mein likhiye, main kundli dekh kar batati hoon. 🙏",
                }
            ]
            return data

        chart = profile.get("chart_json")
        now_ctx = _now_context(chart)
        lang = _lang(profile)
        history_snippet = format_recent_history_str(profile, n=10) or "(no prior turns)"
        instruction = SAMARA_FOLLOWUP_SYSTEM_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            user_name=profile.get("username") or "dost",
            user_language=lang,
            current_date=now_ctx["current_date"],
            current_year=now_ctx["current_year"],
            current_age=now_ctx["current_age"],
            chat_history_snippet=history_snippet,
        )
        try:
            text = await self._llm(
                instruction=instruction,
                user_content=question,
                phone_number=phone_number,
                agent_display_name="SamaraFollowupAgent",
                max_output_tokens=500,
                use_sonnet=False,
            )
        except Exception:
            logger.exception(
                "Samara follow-up LLM call failed",
                extra={"phone_number": phone_number},
            )
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        profile["followup_questions_asked"] = (
            int(profile.get("followup_questions_asked") or 0) + 1
        )
        profile["conversation_beat"] = BEAT_POST_FREE_DEEP
        data["bot_response"] = text_responses(text)
        return data
