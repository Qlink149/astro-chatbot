# Go live — Samara on Vercel

## 1. Backend env essentials

```env
ENV_MODE=dev
DEFAULT_CLIENT_ID=samara
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=astro_chatbot

AI_PROVIDER=openai
AI_PROVIDER_CLASSIFIER=openai
AI_PROVIDER_GENERAL=openai
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

GUPSHUP_APP_ID=
GUPSHUP_TOKEN=
GUPSHUP_APP_NAME=
GUPSHUP_API_KEY=
GUPSHUP_SOURCE=919549549339

SAMARA_PHONE_NUMBER_ID=
SAMARA_BIRTH_FLOW_ID=

SUPER_ADMIN_USERNAME=
SUPER_ADMIN_PASSWORD=
JWT_SECRET_KEY=
SYSTEM_API_KEY=

WEBHOOK_URL=https://YOUR-API.vercel.app/api/gupshup/message/samara
GUPSHUP_WEBHOOK_MODES=MESSAGE,FLOWS_MESSAGE,SENT,DELIVERED,READ,DELETED,FAILED,OTHERS,ENQUEUED
```

## 2. Deploy backend

Vercel project Root Directory = `backend`.

Health: `GET https://YOUR-API.vercel.app/api/ping` → `{"status":"ok"}`

## 3. Register Gupshup webhook

```bash
cd backend
python scripts/setup_gupshup_webhook.py
```

Modes must include `FLOWS_MESSAGE` for birth Flow completions.

## 4. Birth Flow (if needed)

```bash
# Rebuild offline city index (GeoNames CC-BY) if missing/stale:
python scripts/build_geonames_index.py

# Upload + publish Flow JSON after birth_details.json changes:
python scripts/setup_gupshup_flow.py --flow-id $SAMARA_BIRTH_FLOW_ID --upload-only
python scripts/setup_gupshup_flow.py --flow-id $SAMARA_BIRTH_FLOW_ID --publish-only
```

Set printed id as `SAMARA_BIRTH_FLOW_ID` if creating a new flow.
Place of birth is free text; Samara confirms the resolved city before computing the chart.

## 5. Dashboard

Second Vercel project, Root Directory = `frontend`.

```env
VITE_API_URL=https://YOUR-API.vercel.app
```

(No `/api` prefix on Vercel Python deploy.)

Add the dashboard origin to `ALLOWED_ORIGINS` in `kisna_chatbot/main.py`.
