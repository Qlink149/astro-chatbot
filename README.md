# Samara by Clara — WhatsApp Vedic Astrology Bot + Admin Dashboard

Live product: **Samara by Clara**, a Vedic astrology WhatsApp chatbot on **Gupshup**
(not WATI), tenant `client_id=samara`.

Extends the existing **kisna-chatbot** backend (`backend/`) and admin dashboard
(`frontend/`). No framework rewrite — only extended.

**The golden rule (enforced in code + tests):** the LLM never calculates the chart.
`kundli_engine.compute_chart()` ([`backend/kundli_engine/engine.py`](backend/kundli_engine/engine.py))
produces every number (Lagna, Rashi, Nakshatra, planets, Vimshottari Dasha timeline
with `age_start` / `age_end` / `starts_before_birth` / `is_relevant`, plus
`meta.birth_year` / `meta.current_age`). The `SamaraReadingAgent` injects that JSON
into the system prompt; the LLM writes **only** the warm interpretation.

Regression: `backend/tests/test_chart_golden_rule.py` asserts a reading invents no
sign / nakshatra / planet claim absent from a fixed `chart_json`.

---

## 1. Environment variables

### Backend (`backend/.env`)

| Variable | Purpose |
|---|---|
| `MONGO_URI` / `MONGO_DB_NAME` | MongoDB (samara data isolated by `client_id`) |
| `ANTHROPIC_API_KEY` | Claude for Samara readings (preferred when set) |
| `ANTHROPIC_CHAT_MODEL` | Haiku model id for functional messages (default `claude-haiku-4-5`) |
| `ANTHROPIC_CHAT_MODEL_SONNET` | Sonnet model id for Beats 1 / 2 / 4 (default `claude-sonnet-4-5`) |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | Fallback providers / other agents |
| `AI_PROVIDER`, `AI_PROVIDER_GENERAL`, `AI_PROVIDER_CLASSIFIER` | Non-Samara / fallback routing |
| `GUPSHUP_APP_NAME`, `GUPSHUP_APP_ID`, `GUPSHUP_TOKEN`, `GUPSHUP_API_KEY` | Gupshup WhatsApp BSP |
| `GUPSHUP_SOURCE` / `GUPSHUP_PHONE_NUMBER` | Samara WhatsApp sender (E.164, no `+`) |
| `SAMARA_PHONE_NUMBER_ID` | Meta `phone_number_id` → routes to `client_id=samara` |
| `DEFAULT_CLIENT_ID=samara` | Fallback client when `phone_number_id` isn't mapped |
| `SAMARA_BIRTH_FLOW_ID` | Published `birth_details` Flow id |
| `SUPER_ADMIN_USERNAME`, `SUPER_ADMIN_PASSWORD` | Dashboard login |
| `JWT_SECRET_KEY`, `SYSTEM_API_KEY` | Dashboard auth / system routes |
| `GUPSHUP_WEBHOOK_SECRET` | Optional in dev; required when `ENV_MODE=prod` |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Live payment-link + webhook |
| `SAMARA_TEST_PAYMENT_AMOUNT_INR` | Payment link amount (default 49; use `1` for test) |

### Frontend (`frontend/.env`)

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend base URL |

---

## 2. Publishing the `birth_details` Flow

Flow JSON: [`backend/json/birth_details.json`](backend/json/birth_details.json).
Publish via Meta / Gupshup Partner API (`scripts/setup_gupshup_flow.py`), set
`SAMARA_BIRTH_FLOW_ID`.

- Flow path requires birth **time** (hour / minute / AM-PM).
- Typed text fallback (`DD-MM-YYYY, HH:MM, City`) may omit time → engine returns
  `surya_kundli` with `lagna: null` and an honesty note (time is never guessed).

---

## 3. Webhooks

| Endpoint | Role |
|---|---|
| `POST /gupshup/message/samara` | Inbound WhatsApp (Gupshup) |
| `POST /razorpay/webhook` | Payment link paid → grant credits |

Modes must include `MESSAGE` + `FLOWS_MESSAGE` (or Partner equivalent) so Flow
`nfm_reply` completions are forwarded.

---

## 4. Running / deploying the dashboard

```bash
cd frontend
yarn install
yarn dev
yarn build
```

Login with `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD`.

---

## 5. Current conversation flow (paywall OFF)

1. First inbound → greeting + `birth_details` Flow.
2. Flow completion → offline place resolve (GeoNames) → **place confirm** →
   `compute_chart()` → language buttons.
3. Language chosen → **Beat 1** identity (Sonnet) + confirm buttons.
4. Confirm → **Beat 2** past proof from `is_relevant` dashas only + continue button.
5. Continue → **Beat 3** topic picker (5 buttons).
6. Topic → **Beat 4** one free deep answer + open loop; `free_deep_answer_used=true`.
7. Returning users with a chart skip birth/Beat 1; continuity menu
   (`Wahi baat aage` / `Naya sawaal` / `Aaj ka muhurat`).
8. Follow-ups after the free deep answer require credits (paywall ON). Exact
   `PAY` / `unlock` / Pay Now button create a Razorpay CTA; `[Baad mein]` exits
   gracefully. Credits live on an append-only ledger.
9. Funnel event counts appear on the admin Overview.

---

## 6. Chart engine notes

- Ayanamsa: Lahiri. Swiss Ephemeris via bundled `kundli_engine/ephe/`.
- Each dasha period includes `age_start`, `age_end`, `starts_before_birth`,
  `is_relevant` (recent adult window), `phase`, `lived_from_age`.
- `meta.birth_year` and `meta.current_age` are always set.
- No birth time → no Lagna, **no houses key**, honesty note in `meta.note_if_no_time`.
- With birth time → whole-sign `houses` table (`bhavas` + `planet_houses`) from Lagna.

---

## 7. Nudge template — Meta approval steps

Samara sends a one-shot nudge 24 hours after a user taps "Baad mein" (later).
Outside the WhatsApp 24-hour session window, only **approved templates** are
delivered. To get the nudge working:

1. **Create the template** in Gupshup Partner → Templates → New Template.
   - Category: **UTILITY** (post-purchase follow-up).
   - Language: **Hindi (hi)** — the template body should match `NUDGE_TEXT_HI`
     in `samara_jobs.py` (or a cleaned version of it).
   - Example body:
     ```
     Namaste 🙏 Samara, by Clara. Aapki kundli wali baat abhi bhi yahin hai —
     jab ready ho, 'pay' ya 'unlock' likh dena. Bilkul koi rush nahi. 🌙
     ```
   - No parameters needed (no `{{1}}`).
2. **Submit for Meta review.** Approval typically takes 1–24 hours.
3. Once approved, set the env var:
   ```
   SAMARA_NUDGE_TEMPLATE=<approved_element_name>
   ```
4. The cron job `POST /system/samara/send-deferred-nudges` (with
   `SYSTEM_API_KEY`) will try the template first; if it fails or is unset, it
   falls back to a session text (which may silently fail outside 24h).

---

## 8. Data retention & deletion (DPDP)

- User can type **"delete my data"** or **"mera data delete karo"** at any time.
  PII, birth details, chart, chat history, confirmed events are purged immediately.
  Anonymised credit ledger entries (amounts, types, payment IDs) are retained for
  accounting integrity — phone numbers are stripped from content.
- Inactive accounts (no inbound message for **24 months**) are eligible for
  automated purge. Implementation: a scheduled job should scan for
  `last_message_at < now - 24 months` and apply the same anonymised-ledger
  purge as the in-chat deletion flow.
- Samara's greeting includes a consent one-liner and disclaimer:
  reflection/enjoyment purpose only, not medical/legal/financial advice, data
  deletable on request.

---

## 9. Assumptions / known drift

1. **LLM**: Samara `GENERAL` prefers Anthropic Haiku (`ANTHROPIC_CHAT_MODEL`) when
   the key is set; otherwise falls back to `AI_PROVIDER_GENERAL` (OpenAI/Groq).
2. **Paywall**: ON after `free_deep_answer_used` when ledger balance is 0.
   Honest copy + Pay Now / Baad mein. No “coming soon” in paywall text.
3. **Credits**: append-only `credit_ledger` on the user; cached `credits` mirror.
4. **BSP**: Gupshup only — no WATI.
5. **Geocoding**: bundled Indian cities first; Nominatim fallback; IST 5.5 on TZ failure.
6. **Dashboard**: readings = `free_reading_used`; follow-ups = sum of
   `followup_questions_asked`.
