"""Samara jyotishi reading processor.

THE GOLDEN RULE: the LLM never calculates the chart. kundli_engine.compute_chart()
produces every number; the LLM only writes the warm interpretation on top.
"""

import asyncio
import json
import re
from datetime import datetime, timezone

from kisna_chatbot.ai import complete_chat
from kisna_chatbot.ai.types import AgentName
from kisna_chatbot.processors.abstract_processor import Processor
from kisna_chatbot.prompts.samara_reading import (
    SAMARA_FOLLOWUP_SYSTEM_PROMPT,
    SAMARA_READING_SYSTEM_PROMPT,
)
from kisna_chatbot.utils.format_chathistory import format_recent_history_str
from kisna_chatbot.utils.geocode_in import geocode_place, timezone_offset_for
from kisna_chatbot.utils.logger_config import logger

def _kundli():
    """Lazy import — keeps Vercel cold start from crashing if chart deps fail early."""
    from kundli_engine import BirthDetails, compute_chart

    return BirthDetails, compute_chart


def _now_context(chart: dict | None) -> dict:
    """Today's date + user's current age (birth-anchored). LLM never guesses these."""
    now = datetime.now(timezone.utc)
    birth_year = ((chart or {}).get("meta") or {}).get("birth_year")
    current_age = (now.year - int(birth_year)) if birth_year else None
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_year": now.year,
        "current_age": current_age if current_age is not None else "unknown",
    }

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

# Language ask — shown right after the chart is computed, before the reading.
LANG_ASK_TEXT = (
    "🌸 Aapki kundli ready ho gayi hai.\n\n"
    "Reading kis bhasha mein chahiye? Please pick one below.\n"
    "In which language would you like your reading?"
)
LANG_ASK_CAPTION = "Choose one to continue"
LANG_BTN_ENGLISH = "samara_lang_en"
LANG_BTN_HINDI = "samara_lang_hi"


def _language_quickreply_response() -> dict:
    """Gupshup quick_reply payload with English / Hindi buttons."""
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
    """Return 'english' / 'hindi' if this message picks a language, else None.

    Accepts:
    - a button_reply/interactive quick-reply carrying the LANG_BTN_* id or a
      postbackText matching those,
    - a plain text like "english" / "hindi" / "en" / "hi".
    """
    if not isinstance(messages, dict):
        return None
    mtype = messages.get("type")
    # Quick-reply / button reply
    if mtype == "interactive":
        inter = messages.get("interactive") or {}
        br = inter.get("button_reply") or {}
        raw_id = str(br.get("id") or "")
        title = str(br.get("title") or "").strip().lower()
        # id may be plain or JSON-encoded {"msgid":"..."} — try both.
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
    # Gupshup sometimes surfaces quick-reply choices under a "button" payload.
    if mtype == "button":
        payload = ((messages.get("button") or {}).get("payload") or "").strip()
        text = ((messages.get("button") or {}).get("text") or "").strip().lower()
        if payload == LANG_BTN_ENGLISH or text == "english":
            return "english"
        if payload == LANG_BTN_HINDI or text == "hindi":
            return "hindi"
    # Plain text fallback
    if mtype == "text":
        body = ((messages.get("text") or {}).get("body") or "").strip().lower()
        if body in ("english", "en", "eng", "angrezi"):
            return "english"
        if body in ("hindi", "hi", "हिंदी", "hindi/hinglish", "hinglish"):
            return "hindi"
    return None


def _parse_birth_flow_reply(messages: dict) -> dict | None:
    """Return the birth_details Flow payload if this message is its nfm_reply."""
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
    """Meta DatePicker returns epoch-ms string or YYYY-MM-DD."""
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
    """Parse birth time from the strict Flow payload.

    The Flow now REQUIRES `birth_hour_input`, `birth_minute_input`, and
    `birth_ampm`. Returns the 24-hour (hour, minute) tuple when all three are
    valid, else None (which the caller treats as an invalid submission and
    re-prompts the Flow — the reading is never generated on missing time).

    Legacy payload shapes (`birth_hour`/`birth_minute` 24-hour Dropdowns and
    single `birth_time` HH:MM) are still accepted so historical/typed-text
    fallbacks keep working, but the Flow itself no longer emits them.
    """
    # Preferred: manual hour+minute TextInputs + AM/PM.
    raw_h_in = str(flow_data.get("birth_hour_input") or "").strip()
    raw_m_in = str(flow_data.get("birth_minute_input") or "").strip()
    raw_ampm = str(flow_data.get("birth_ampm") or "").strip().upper()
    if raw_h_in.isdigit() and raw_m_in.isdigit() and raw_ampm in ("AM", "PM"):
        h12, m = int(raw_h_in), int(raw_m_in)
        if 1 <= h12 <= 12 and 0 <= m <= 59:
            # Convert 12-hour clock to 24-hour.
            if raw_ampm == "AM":
                h24 = 0 if h12 == 12 else h12
            else:  # PM
                h24 = 12 if h12 == 12 else h12 + 12
            return (h24, m)

    # Legacy: hour+minute Dropdowns (24-hour hour).
    raw_hour = str(flow_data.get("birth_hour") or "").strip()
    raw_minute = str(flow_data.get("birth_minute") or "").strip()
    if raw_hour.isdigit() and raw_minute.isdigit():
        h, m = int(raw_hour), int(raw_minute)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    # Legacy: single birth_time string ("07:25" typed text).
    raw_time = str(flow_data.get("birth_time") or "").strip().lower()
    match = _TIME_RE.match(raw_time) if raw_time else None
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return None


def _parse_birth_text(text: str) -> dict | None:
    """Fallback: parse typed birth details like '15-05-1990, 07:25, Udaipur'."""
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

    remainder = text[: date_span[0]] + " " + text[date_span[1]:]
    time_match = _TEXT_TIME_RE.search(remainder)
    time_str = ""
    if time_match:
        time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        remainder = (
            remainder[: time_match.span()[0]] + " " + remainder[time_match.span()[1]:]
        )

    place = re.sub(r"[^A-Za-z\s]", " ", remainder)
    place = " ".join(
        w for w in place.split() if w.lower() not in ("dob", "time", "place", "at", "in", "born")
    ).strip()
    if len(place) < 3:
        return None
    return {
        "flow_kind": "typed_text",
        "birth_date": date_str,
        "birth_time": time_str,
        "birth_place": place,
    }


def _birth_summary(bd: dict) -> str:
    tob = bd.get("time_of_birth") or "unknown"
    return f"DOB {bd.get('date_of_birth')}, time {tob}, place {bd.get('place_name')}"


class SamaraReadingAgent(Processor):
    """Free-reading + credit-gated follow-ups for the samara client."""

    def should_run(self, data: dict) -> bool:
        return "bot_response" not in data and data.get("client_id") == "samara"

    async def process(self, data: dict) -> dict:
        if not self.should_run(data):
            return data

        phone_number = data["phone_number"]
        profile = data["user_profile"]
        profile.setdefault("credits", 0)
        profile.setdefault("free_reading_used", False)
        messages = data.get("messages") or {}

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
            data["bot_response"] = [
                {"type": "text", "text": GREETING_TEXT if is_new else NUDGE_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        # Chart is ready. Before the first reading, ask for language via buttons.
        if not profile.get("free_reading_used"):
            if not profile.get("user_language"):
                lang = _parse_language_choice(messages)
                if lang:
                    profile["user_language"] = lang
                    return await self._send_free_reading(data, profile, phone_number)
                # Still waiting for a language pick — (re)send the buttons.
                data["bot_response"] = [_language_quickreply_response()]
                return data
            return await self._send_free_reading(data, profile, phone_number)

        return await self._handle_followup(data, profile, phone_number)

    # ── Flow completion → geocode → compute_chart ────────────────────────────

    async def _handle_birth_details(
        self, data: dict, profile: dict, phone_number: str, flow_data: dict
    ) -> dict:
        ymd = _parse_birth_date(flow_data.get("birth_date"))
        raw_place = str(flow_data.get("birth_place") or "").strip()
        # Server-side hard-requirement: date + city are mandatory. If either
        # is missing (bad legacy payload), re-prompt the Flow — never proceed
        # on partial data. Chart must be computed BEFORE any reading.
        if not ymd or not raw_place:
            data["bot_response"] = [
                {"type": "text", "text": ERROR_TEXT},
                {"type": "flow", "flow": "birth_details"},
            ]
            return data

        # City comes back as the Dropdown's id (lowercase). Title-case for
        # storage/display; the geocoder normalizes internally anyway.
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
        # Time is now MANDATORY. If the payload didn't carry a valid
        # hour+minute+AM-PM (e.g. an old cached Flow client), re-prompt the
        # Flow instead of falling back to a sun-level chart. The typed-text
        # fallback path is exempt because it explicitly signals an intent to
        # skip time by leaving `birth_time` blank.
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
        except Exception:
            logger.exception(
                "compute_chart failed",
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
        # Ensure any stale language is cleared for this fresh chart cycle.
        profile["user_language"] = None
        logger.info(
            "Samara chart computed",
            extra={
                "phone_number": phone_number,
                "chart_type": chart["meta"]["chart_type"],
                "place": place,
            },
        )
        # Language buttons come BEFORE the reading. The reading is generated
        # only after the user picks English or Hindi on their next reply.
        data["bot_response"] = [_language_quickreply_response()]
        return data

    # ── Readings (LLM interprets ONLY — chart JSON is injected, never computed) ──

    async def _send_free_reading(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        chart = profile.get("chart_json")
        user_name = profile.get("username") or "dost"
        user_language = profile.get("user_language") or "hindi"
        now_ctx = _now_context(chart)
        instruction = SAMARA_READING_SYSTEM_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            user_name=user_name,
            user_language=user_language,
            current_date=now_ctx["current_date"],
            current_year=now_ctx["current_year"],
            current_age=now_ctx["current_age"],
        )
        try:
            text = await complete_chat(
                agent=AgentName.GENERAL,
                agent_display_name="SamaraReadingAgent",
                instruction=instruction,
                messages=[
                    {
                        "role": "user",
                        "content": "Please write my first Vedic reading now.",
                    }
                ],
                max_output_tokens=1400,
                phone_number=phone_number,
                client_id="samara",
            )
        except Exception:
            logger.exception(
                "Samara free reading LLM call failed",
                extra={"phone_number": phone_number},
            )
            data["bot_response"] = [{"type": "text", "text": ERROR_TEXT}]
            return data

        profile["free_reading_used"] = True
        profile["reading_delivered_at"] = int(datetime.now(timezone.utc).timestamp())
        data["bot_response"] = [{"type": "text", "text": text}]
        return data

    async def _handle_followup(
        self, data: dict, profile: dict, phone_number: str
    ) -> dict:
        # Payment blocker is OFF (testing mode). Every follow-up gets a real
        # answer; we still count questions for analytics but never gate on credits.
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
        user_name = profile.get("username") or "dost"
        user_language = profile.get("user_language") or "hindi"
        now_ctx = _now_context(chart)
        # Give Samara real conversational memory — the last ~10 turns of this
        # user's chat so she stays in the same thread, not a fresh voice each time.
        history_snippet = format_recent_history_str(profile, n=10) or "(no prior turns)"
        instruction = SAMARA_FOLLOWUP_SYSTEM_PROMPT.format(
            chart_json=json.dumps(chart, ensure_ascii=False),
            user_name=user_name,
            user_language=user_language,
            current_date=now_ctx["current_date"],
            current_year=now_ctx["current_year"],
            current_age=now_ctx["current_age"],
            chat_history_snippet=history_snippet,
        )
        try:
            text = await complete_chat(
                agent=AgentName.GENERAL,
                agent_display_name="SamaraFollowupAgent",
                instruction=instruction,
                messages=[{"role": "user", "content": question}],
                max_output_tokens=800,
                phone_number=phone_number,
                client_id="samara",
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
        data["bot_response"] = [{"type": "text", "text": text}]
        return data
