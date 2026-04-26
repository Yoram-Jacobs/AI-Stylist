# DressApp

Your AI fashion editor: photograph any garment, get weather + calendar-aware outfits, scan EU DPP QR tags, and resell from a polished marketplace — all in your pocket.

**Live demos**

- 🟢 Production · <https://dressapp.co> (Hetzner VPS, custom domain)
- 🚀 Contest deployment · <https://ai-stylist-api.emergent.host> (Emergent native)

---

## What it does

DressApp turns a closet of physical clothes into a structured, queryable wardrobe and uses that wardrobe to drive everyday styling decisions.

### Core flows

| Flow | What it does |
| --- | --- |
| **Capture** | Snap or upload photos. The vision pipeline crops each garment, removes the background, and auto-fills 20+ attributes (category, fabric, fit, season, dress-code, colours, condition, repair advice…). |
| **Auto-fill** | Falls back to local SegFormer + rembg + a Gemini stylist for descriptions. Bulk uploads (>5 items) auto-process in the background and land in the closet for review. |
| **DPP QR scan** | Scans EU Digital Product Passport QR codes (JSON-LD or inline JSON), imports brand, fibre composition, supply-chain trace and care info — even without a photo. |
| **AI Stylist** | Conversational chat (text or voice) that pulls weather, your calendar, your closet, and your cultural context to suggest complete outfits. Speaks 12 languages. |
| **Marketplace** | Sell, swap or donate pieces. Region-matched feed, Live PayPal checkout, transparent platform fee (7% after processing). |
| **Experts directory** | Find vetted stylists, tailors and designers. Self-serve promotion campaigns drive a region-aware ticker on the home screen. |
| **Trend Scout** | Daily background scheduler curates four trend buckets — runway, street, sustainability, influencers. Translated into the user's language at read time. |

---

## Tech stack

**Backend** — FastAPI (Python 3.11) · Motor async MongoDB driver · Pydantic v2

**Frontend** — React 19 · React Router · Tailwind · Shadcn/UI · `react-i18next` (12 locales) · Sonner toasts · Lucide icons

**Vision pipeline (in-pod, no external API)** — `rembg` (U2-Net) for matting · HuggingFace SegFormer-b3 fine-tuned for clothes · Fashion-CLIP for embeddings

**Voice** — Deepgram (STT + TTS, multi-voice)

**LLM** — Emergent universal key (OpenAI / Gemini / Claude). Default stylist model: Gemini Flash 2.x

**External APIs** — OpenWeather · PayPal Live · Google OAuth + Google Calendar

**Hosting** — Docker Compose · Caddy 2 (auto Let's Encrypt) · MongoDB Atlas

---

## Architecture at a glance

```
                  ┌──────────── HTTPS ────────────┐
                  │                                │
        ┌─────────▼────────┐              ┌────────▼─────────┐
        │  Caddy (TLS)     │              │ Browser (PWA)    │
        │  /api/* → backend│              └──────────────────┘
        │  /*    → frontend│
        └────┬────────┬────┘
             │        │
   ┌─────────▼┐    ┌──▼─────────────────┐
   │ FastAPI  │    │ Nginx (static SPA) │
   │  :8001   │    │  React build       │
   └────┬─────┘    └────────────────────┘
        │
        ├─ MongoDB Atlas (users, closet, listings, trends, …)
        ├─ Local SegFormer + rembg (CPU inference, ~1.4 GB RAM)
        ├─ Deepgram (STT/TTS over HTTPS)
        ├─ OpenWeather, PayPal Live, Google OAuth/Calendar
        └─ Emergent LLM key → OpenAI / Gemini / Anthropic
```

A more detailed write-up lives in [`/app/docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the database shape in [`/app/docs/MONGODB_SCHEMA.md`](docs/MONGODB_SCHEMA.md).

---

## Repository layout

```
.
├── backend/                # FastAPI service
│   ├── server.py           # App entry, ASGI bindings, CORS
│   ├── app/
│   │   ├── api/v1/         # Versioned routers (closet, listings, stylist, …)
│   │   ├── services/       # Business logic + ML services
│   │   ├── models/         # Pydantic schemas
│   │   ├── db/             # Mongo bootstrap + index creation
│   │   └── core/           # Settings, security, deps
│   ├── scripts/
│   │   └── seed_demo.py    # Idempotent demo-data seeder
│   └── requirements.txt
│
├── frontend/               # React SPA (Create-React-App + craco)
│   ├── src/
│   │   ├── pages/          # Top-level routes
│   │   ├── components/     # Shared UI (DppScanner, AdTicker, …)
│   │   ├── components/ui/  # Shadcn primitives
│   │   ├── lib/            # api client, i18n, helpers
│   │   └── locales/        # 12 translation files
│   └── package.json
│
├── deploy/                 # Production deploy kit
│   ├── docker-compose.yml
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── Caddyfile
│   ├── nginx-frontend.conf
│   └── DEPLOY.md           # Step-by-step VPS guide
│
└── docs/                   # Architecture + schema docs
```

---

## Getting started — local dev

The whole project ships ready to run inside the Emergent platform. Backend, frontend and MongoDB are already wired up by `supervisord`.

### Backend

```bash
cd backend
# Hot-reload is on in supervisor; you only need to restart on dep changes:
sudo supervisorctl restart backend
# Required env (already populated in /app/backend/.env):
#   MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY
#   GOOGLE_OAUTH_CLIENT_ID/SECRET, DEEPGRAM_API_KEY, OPENWEATHER_API_KEY,
#   GROQ_API_KEY, HF_TOKEN, PAYPAL_LIVE_CLIENT_ID/SECRET, PAYPAL_ENV
```

### Frontend

```bash
cd frontend
yarn install
sudo supervisorctl restart frontend
# REACT_APP_BACKEND_URL is preconfigured in frontend/.env
```

### Seed demo data (optional)

For a fresh database, populate listings, professionals, trend cards and a demo user:

```bash
cd backend
python -m scripts.seed_demo   # idempotent — re-running upserts
```

---

## Production deployment

DressApp is designed to run as a 3-container Docker Compose stack on any 4 GB+ VPS:

- `backend` — FastAPI + ML models (~1.5 GB RAM at idle)
- `frontend` — Nginx serving the built SPA
- `caddy` — TLS termination, automatic Let's Encrypt, HTTP→HTTPS redirect

Step-by-step instructions: [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

```bash
# After cloning on the VPS:
cd deploy
cp .env.example .env   # then edit
docker compose up -d --build
```

Routine update:

```bash
git pull origin main
docker compose up -d --build
```

---

## Contributing

1. Fork → branch off `main`
2. Run lint before pushing:
   - Python — `ruff check backend/`
   - JS/TS — `cd frontend && yarn lint`
3. Open a PR. CI runs the full test suite (FastAPI tests + Playwright smokes).

---

## License

© 2025–2026 DressApp. All rights reserved. The trademarks, product designs, and content displayed in the app are the property of their respective owners.
