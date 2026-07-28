# Samara by Clara — WhatsApp Vedic Astrology Bot + Admin Dashboard

Phase 1 build. Extends the existing **kisna-chatbot** backend (`/app/backend`) with a new
`client_id="samara"` and re-skins the existing **kisna_chatbot_dashboard** frontend
(`/app/frontend`) for Samara. No framework/page code was rewritten — only extended.

**The golden rule (enforced in code):** the LLM never calculates the chart.
`kundli_engine.compute_chart()` (at `/app/backend/kundli_engine/engine.py`) produces every
number (Lagna, Rashi, Nakshatra, planets, Vimshottari Dasha timeline). The
`SamaraReadingAgent` processor injects that JSON into the (placeholder) system prompt and
the LLM writes ONLY the warm reading.

---

## 1. Environment variables

### Backend (`/app/backend/.env`)

| Variable | Purpose |
|---|---|
| `MONGO_URI` / `MONGO_DB_NAME` | MongoDB (same DB the kisna framework uses; samara data isolated by `client_id`) |
| `OPENAI_API_KEY` | LLM for the reading (interpretation only) |
| `AI_PROVIDER`, `AI_PROVIDER_GENERAL`, `AI_PROVIDER_CLASSIFIER` | set to `openai` (or `groq` + `GROQ_API_KEY`) |
| `GUPSHUP_APP_NAME`, `GUPSHUP_APP_ID`, `GUPSHUP_TOKEN`, `GUPSHUP_API_KEY` | Gupshup WhatsApp BSP |
| `GUPSHUP_SOURCE` / `GUPSHUP_PHONE_NUMBER` | Samara WhatsApp sender number (E.164, no `+`) |
| `SAMARA_PHONE_NUMBER_ID` | Meta `phone_number_id` from webhook metadata → routes to `client_id=samara` |
| `DEFAULT_CLIENT_ID=samara` | Fallback client when `phone_number_id` isn't in the map yet |
| `SAMARA_BIRTH_FLOW_ID` | WhatsApp Flow ID of the published `birth_details` Flow (see §2) |
| `SUPER_ADMIN_USERNAME`, `SUPER_ADMIN_PASSWORD` | Dashboard login |
| `JWT_SECRET_KEY`, `SYSTEM_API_KEY` | Dashboard auth / system routes |
| `GUPSHUP_WEBHOOK_SECRET` | Optional in dev; required when `ENV_MODE=prod` |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | **Reserved for Phase 2** — leave empty now |

### Frontend (`/app/frontend/.env`)

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend base URL. On Vercel Python: `https://<api>.vercel.app` (no `/api`). On Emergent gateway: `https://<host>/api` |

---

## 2. Publishing the `birth_details` Flow in Meta

> ✅ **Already done for the Qliink app**: Flow `samara_birth_details` was created and
> published via the Gupshup Partner API (`scripts/setup_gupshup_flow.py`) —
> `SAMARA_BIRTH_FLOW_ID=1018626800813268` is set in the backend env.
> If a user types birth details as plain text instead of using the form
> (e.g. `15-05-1990, 07:25, Udaipur`), the bot parses that too.

The Flow JSON lives at `/app/backend/json/birth_details.json` (static Flow, version 7.0 —
no data-exchange endpoint required). To re-publish elsewhere:

1. Open **Meta Business Manager → WhatsApp Manager → Account tools → Flows → Create Flow**
   (for the WABA behind the Samara/Qliink Gupshup app). Alternatively use the Gupshup
   Partner API script pattern in `scripts/setup_gupshup_flow.py`.
2. Name it `samara_birth_details`, category `OTHER`, and paste the contents of
   `json/birth_details.json`.
3. Preview it (date picker + optional time + "I don't know my birth time" + place), then
   **Publish**.
4. Copy the Flow ID and set it in backend env: `SAMARA_BIRTH_FLOW_ID=<flow_id>`.
5. Restart the backend. Until this ID is set, the bot falls back to asking for birth
   details as plain text instructions (it will not crash).

## 3. Pointing the Samara number's webhook at the backend

> ✅ **Already done for the Qliink app**: the existing Gupshup subscription (which pointed
> at the old `kisna-chatbot.vercel.app`) was updated to
> `https://clara-astro.preview.emergentagent.com/api/gupshup/message/samara`
> with modes `MESSAGE + FLOWS_MESSAGE + statuses` (⚠️ `FLOWS_MESSAGE` is REQUIRED —
> without it Gupshup does not forward Flow completions/nfm_reply for subscriptions
> created after Feb 2025). `SAMARA_PHONE_NUMBER_ID=451074671429987` (real Meta id).
> Re-run the script with a new `WEBHOOK_URL` and
> `GUPSHUP_WEBHOOK_MODES="MESSAGE,FLOW_MESSAGE,SENT,DELIVERED,READ,DELETED,FAILED,OTHERS,ENQUEUED"`
> when you move to a production host.

1. Deploy the backend and note its public base URL, e.g. `https://<host>`.
2. Webhook URL: `https://<host>/api/gupshup/message/samara`
3. Set it in the Gupshup dashboard (app **Qliink** → Webhooks), or run the bundled script:
   `WEBHOOK_URL=https://<host>/api/gupshup/message/samara python scripts/setup_gupshup_webhook.py`
   with the `GUPSHUP_PARTNER_*` vars set.
4. Send a first message to the Samara number, check the backend logs for the
   `phone_number_id` in the webhook metadata, and set `SAMARA_PHONE_NUMBER_ID` to that
   value (until then `DEFAULT_CLIENT_ID=samara` routes messages correctly on a
   single-tenant deployment).
5. In production set `ENV_MODE=prod` and `GUPSHUP_WEBHOOK_SECRET` (signature verification).

## 4. Running / deploying the dashboard

```bash
cd frontend
yarn install
yarn dev            # local (proxy /system → VITE_API_URL)
yarn build          # production build → dist/ (deploy to Vercel/any static host)
```
Set `VITE_API_URL=https://<backend-host>/api` in the deploy environment, and add the
dashboard origin to `ALLOWED_ORIGINS` in `kisna_chatbot/main.py`.

Login with `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD`.

## 5. Phase 1 conversation flow

1. First inbound message → `UserRegistration` creates a samara profile.
2. Bot greets warmly and sends the `birth_details` Flow.
3. Flow completion → geocode (bundled Indian-city table → Nominatim fallback) →
   `compute_chart()` → chart JSON stored once on the profile (`chart_json`).
4. `SamaraReadingAgent` sends the FREE reading (LLM interprets the chart JSON only);
   `free_reading_used=True`.
5. Follow-ups: `credits > 0` → answer from `chart_json` and decrement; otherwise a
   placeholder paywall message (₹49 = 10 questions — Razorpay in Phase 2).

---

## 6. Assumptions made (please correct me)

1. **LLM**: OpenAI `gpt-4o-mini` via the existing `ai/` factory (`AI_PROVIDER=openai`),
   using the key you provided. Groq env names remain reserved.
2. **System prompt**: Phase-1 placeholder lives in
   `kisna_chatbot/prompts/samara_reading.py`, clearly marked
   `# TODO: replace with final Samara system prompt`. Both the free-reading and follow-up
   prompts are placeholders.
3. **Time picker**: Meta Flows have no native time picker, so the Flow uses a free-text
   `HH:MM` (24-hr) input **plus** an explicit "I don't know my birth time" opt-in. Any
   unparseable time is treated as unknown (the engine then returns a `surya_kundli` —
   the time is never guessed).
4. **DatePicker value**: parsed as epoch-milliseconds (Meta's format) with a
   `YYYY-MM-DD` fallback.
5. **Geocoding**: a bundled table of ~230 major Indian cities/towns (with common alias
   spellings) is tried first; misses fall back to geopy/Nominatim with ", India" appended
   first. If both fail, the bot honestly asks the user to re-submit with a nearby big city.
6. **Timezone**: computed from lat/lon + birth date via timezonefinder+pytz (handles
   non-Indian birthplaces); falls back to IST 5.5 on failure.
7. **Client routing**: `DEFAULT_CLIENT_ID=samara` is set so this deployment treats unknown
   `phone_number_id`s as samara (it's effectively single-tenant). On a shared deployment
   you'd unset it and rely purely on `SAMARA_PHONE_NUMBER_ID`. I could not know Meta's
   numeric `phone_number_id` in advance, so I seeded it with the phone number itself —
   replace after the first real webhook.
8. **`SAMARA_PHONE_NUMBER_ID` naming**: the master prompt listed it; the existing map in
   `config/gupshup.py` was extended following the `KISNA_PHONE_NUMBER_ID` pattern.
9. **Kisna welcome template**: the 24-hr-window welcome template send in
   `ResponseManager` is now gated to `client_id == "kisna"` so Samara users never get the
   Kisna jewellery template. Samara has no re-open template yet (Phase 2 retention work).
10. **Credits**: stored as plain ints on the user profile (`credits`,
    `free_reading_used`, `followup_questions_asked`). No ledger collection yet — Phase 2
    (Razorpay) will add proper transactions.
11. **Dashboard metrics**: "Readings Delivered" = users with `free_reading_used=true`;
    "Follow-up Questions" = sum of `followup_questions_asked`. Kisna-specific cards
    (store visits, complaints, store-visit growth) are hidden, not deleted; the
    Complaints/Callbacks pages still exist but are removed from the nav.
12. **Language**: bot copy (greeting, paywall, errors) is warm Hinglish per the product
    description; the reading itself is written by the LLM per the placeholder prompt.
13. **Non-text messages** (images/audio/location) get a gentle Samara-specific "text only
    please" reply instead of Kisna's jewellery copy.
14. **Chart storage**: `chart_json` is computed once per user and reused. Re-submitting
    the Flow recomputes and overwrites it (useful for corrections).
15. **Credentials shared in chat** are treated as compromised — rotate the OpenAI key,
    Gupshup tokens and admin password before production deploy.
