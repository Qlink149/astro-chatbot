# Vercel deploy (Samara)

## Prerequisites

- MongoDB Atlas `MONGO_URI`
- Vercel account

## Deploy backend

Root Directory = `backend`.

Uses modern `functions` + `rewrites` in `vercel.json` (not legacy `builds`).
Python `3.12` via `.python-version`. Runtime deps are in slim `requirements.txt`
(full Emergent dump kept as `requirements.full.txt` for reference only).

After env vars are set, redeploy and check:

`GET https://YOUR-API.vercel.app/api/ping` → `{"status":"ok"}`

## Deploy dashboard

Second project, Root Directory = `frontend`.

```env
VITE_API_URL=https://YOUR-API.vercel.app
```

## Webhook

```text
https://YOUR-API.vercel.app/api/gupshup/message/samara
```

`/api` prefix on this Vercel entrypoint (`api/index.py` strips it before FastAPI routing).
