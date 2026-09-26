# Deployment

Nothing here needs a local machine at runtime.

## 1. Database (Neon / Supabase / any managed PostgreSQL)
Create a database and copy its connection string (use SSL, e.g. `?sslmode=require`).

## 2. Backend (Render / Railway / Fly / any Docker or process host)
- Root directory: `backend`
- Docker: uses `backend/Dockerfile` (listens on `$PORT`). `render.yaml` at the repo root is an optional Render blueprint.
- Non-Docker: build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Env vars: `DATABASE_URL`, `CORS_ORIGINS` (your frontend origin, no trailing slash), `SECRET_KEY` (**required**, >= 32 random characters; the app and Alembic refuse to start without it). `ENVIRONMENT` defaults to `production`; leave it that way in hosted deployments. `CORS_ORIGINS` must be exact `http(s)://` origins (`*` is rejected); credentialed CORS is intentionally disabled because auth uses a Bearer header.
- Health check path: `/api/health`
- Migrations: run `alembic upgrade head` from `backend/` as a release/pre-deploy command (it needs the same `DATABASE_URL` and `SECRET_KEY` env vars). Migrations `0001`-`0007` create the users, category, product, warehouse, location, contact, reorder-rule and document-sequence tables.

## 3. Frontend (Vercel / Netlify)
- Root directory: `frontend`; build `npm run build`; output `dist`
- Env var: `VITE_API_BASE_URL` = backend public HTTPS URL. It is inlined at build time, so redeploy after changing it.
- SPA fallback is preconfigured (`vercel.json`, `netlify.toml`).

## 4. Order
DB -> backend (needs frontend origin for `CORS_ORIGINS`; set it after the frontend URL is known, then redeploy/restart) -> frontend.

## Assumptions
- Managed PostgreSQL only; no SQLite or local-file storage.
- Backend runs as a stateless container/process.
- Auth and JWT signing (`SECRET_KEY`) come from env vars only; never commit real values.

## Verification status
- Verified: frontend build with an external `VITE_API_BASE_URL`, backend pytest, CORS allow/deny, `DATABASE_URL` normalization, `$PORT` start command, clean 503 from `/api/health/db` when the database is unreachable.
- **Pending:** live connection test against a real managed PostgreSQL (Neon/Supabase). No such database was available during scaffolding. Run `GET /api/health/db` against the first real deployment and expect `{"status":"ok","database":"ok"}`.
- Pending: `docker build` was not run (Docker not installed on the scaffolding machine); the `CMD` was verified by running the same command directly.
