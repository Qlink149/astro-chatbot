# Vercel deploy (Samara)

## Prerequisites

- MongoDB Atlas `MONGO_URI`
- Vercel account + CLI: `npx vercel login`

## Deploy backend

Root Directory = `backend`.

```bash
cd backend
npx vercel link
npx vercel deploy -y
```

Set env vars from `.env.example` in the Vercel project settings.

## Deploy dashboard

Second project, Root Directory = `frontend`.

```env
VITE_API_URL=https://YOUR-API.vercel.app
```

## Webhook

```text
https://YOUR-API.vercel.app/gupshup/message/samara
```

No `/api` prefix on this Vercel entrypoint (`api/index.py`).

Register with:

```bash
python scripts/setup_gupshup_webhook.py
```

## Verify

- `GET https://YOUR-API.vercel.app/ping` → `{"status":"ok"}`
- Dashboard login with `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD`
