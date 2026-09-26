# StockSense

Transaction-driven inventory system. See `StockSense_Technical_Blueprint_v1.md`.

```
Browser -> React/Vite (frontend/) -> HTTPS REST -> FastAPI (backend/) -> PostgreSQL
```

This is the shared scaffold only. Feature work lives on feature branches.

## Layout

| Path | Purpose |
|---|---|
| `frontend/` | React 19 + Vite + React Router (JavaScript) |
| `backend/` | FastAPI + SQLAlchemy 2 + Alembic + psycopg 3 |
| `docs/` | Documentation (see `docs/deployment.md`) |

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | frontend (build time) | Backend base URL, e.g. `https://api.example.com` |
| `DATABASE_URL` | backend | Managed Postgres URL. `postgres://` / `postgresql://` are normalized to `postgresql+psycopg://` |
| `CORS_ORIGINS` | backend | Comma-separated allowed frontend origins |
| `CORS_ORIGIN_REGEX` | backend (optional) | Regex for preview deployments, e.g. `https://.*\.vercel\.app` |

Copy `frontend/.env.example` and `backend/.env.example` to `.env` (git-ignored). Never commit real values.

## Local development

Backend (Python 3.12+):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set DATABASE_URL (e.g. a Neon/Supabase dev DB) and CORS_ORIGINS
uvicorn app.main:app --reload --port 8000
pytest
```

Frontend (Node 20+):
```bash
cd frontend
npm install
cp .env.example .env        # set VITE_API_BASE_URL
npm run dev                 # http://localhost:5173
```
For `npm run dev` only, if `VITE_API_BASE_URL` is unset the client falls back to `http://localhost:8000`. Production builds never use that fallback. For local dev add `http://localhost:5173` to `CORS_ORIGINS`.

Health endpoints: `GET /api/health` (liveness, no DB) and `GET /api/health/db` (checks the database, 503 if unreachable).

## Production build

```bash
cd frontend && npm ci && npm run build      # outputs frontend/dist
cd backend && docker build -t stocksense-api .
```

## Deployment

See `docs/deployment.md`.
