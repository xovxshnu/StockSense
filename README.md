# StockSense

Transaction-driven inventory system. See `StockSense_Technical_Blueprint_v1.md`.

```
Browser -> React/Vite (frontend/) -> HTTPS REST -> FastAPI (backend/) -> PostgreSQL
```

The backend includes the master-data layer (auth, categories, products, warehouses, locations, contacts, reorder rules, reference sequences). Inventory Core and the operations are still to come.

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
| `SECRET_KEY` | backend (required) | JWT signing key, at least 32 characters. The app will not start without it |
| `ENVIRONMENT` | backend | `development`, `test` or `production` (default `production`) |
| `CORS_ORIGINS` | backend | Comma-separated exact frontend origins (no `*`) |
| `CORS_ORIGIN_REGEX` | backend (optional) | Regex for preview deployments, e.g. `https://.*\.vercel\.app` |

Copy `frontend/.env.example` and `backend/.env.example` to `.env` (git-ignored). Never commit real values.

## Local development

Backend (Python 3.12+):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set SECRET_KEY, DATABASE_URL (or the POSTGRES_* parts) and CORS_ORIGINS
alembic upgrade head        # create the schema (migrations 0001-0007)
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

Health endpoints: `GET /api/health` (liveness, no DB) and `GET /api/health/db` (checks the database, 503 if unreachable). The original `GET /health` is still served for compatibility.

Interactive API docs: `http://localhost:8000/docs`.

## Production build

```bash
cd frontend && npm ci && npm run build      # outputs frontend/dist
cd backend && docker build -t stocksense-api .
```

## Deployment

See `docs/deployment.md`.
